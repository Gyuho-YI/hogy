package com.hogy.cockpit.batch;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.hogy.cockpit.config.AppProperties;
import com.hogy.cockpit.journal.JournalService;
import com.hogy.cockpit.plan.PlanRepository;
import com.hogy.cockpit.settings.OwnerSettings;
import com.hogy.cockpit.settings.SettingsService;

/**
 * 스크리너(Python) 프로세스를 실행하고 상태·로그를 보관합니다.
 * - 시장별 동시 실행 1개, 최대 30분 후 강제 종료
 * - 성공 시 plans_{market}.json 이 갱신되고 PlanRepository 가 자동 반영
 * - 국내 실행 전 매매일지를 CSV 로 내보내 실전 승률 기반 하프켈리에 사용
 */
@Service
public class BatchService {

    private static final Logger log = LoggerFactory.getLogger(BatchService.class);
    private static final int TAIL_LINES = 200;
    private static final long TIMEOUT_MINUTES = 30;

    private final AppProperties props;
    private final SettingsService settings;
    private final JournalService journal;
    private final Path dataDir;
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final Map<String, BatchStatus> status = new ConcurrentHashMap<>();

    public BatchService(AppProperties props, SettingsService settings, JournalService journal) {
        this.props = props;
        this.settings = settings;
        this.journal = journal;
        this.dataDir = Path.of(props.dataDir()).toAbsolutePath().normalize();
    }

    public BatchStatus status(String market) {
        String m = PlanRepository.normalize(market);
        return status.getOrDefault(m, BatchStatus.idle(m));
    }

    /**
     * 비동기 실행 요청.
     *
     * @return 거절 사유(실행 시작 시 null)
     */
    public synchronized String start(String market) {
        String m = PlanRepository.normalize(market);
        if (!props.batchEnabled()) {
            return "이 모드에서는 배치 실행이 비활성화되어 있습니다";
        }
        if (status(m).running()) {
            return "이미 실행 중입니다";
        }
        OwnerSettings s = settings.get();
        Double account = "kr".equals(m) ? s.getAccountKr() : s.getAccountUs();
        if (account == null) {
            return "설정에서 " + ("kr".equals(m) ? "국내" : "해외") + " 계좌 금액을 먼저 입력하세요";
        }
        List<String> cmd = buildCommand(m, account);
        status.put(m, new BatchStatus(m, true, LocalDateTime.now(), null, null, "실행 중", List.of()));
        executor.submit(() -> execute(m, cmd));
        return null;
    }

    List<String> buildCommand(String market, double account) {
        List<String> cmd = new ArrayList<>(ScreenerCommand.resolve(props.screenerCommand()));
        cmd.add(market);
        cmd.add("--account");
        // 삼항 연산자는 long/double 을 double 로 승격해 '3.0E7' 이 되므로 BigDecimal 로 일반 표기
        cmd.add(java.math.BigDecimal.valueOf(account).stripTrailingZeros().toPlainString());
        cmd.add("--out");
        cmd.add(dataDir.toString());
        if ("kr".equals(market)) {
            Path stats = exportJournal();
            if (stats != null) {
                cmd.add("--stats");
                cmd.add(stats.toString());
            }
        }
        return cmd;
    }

    /** 청산 기록이 있으면 journal_stats.csv 로 저장(스크리너가 30건 이상일 때만 켈리 적용). */
    private Path exportJournal() {
        String csv = journal.exportCsv();
        if (csv.lines().count() <= 1) {
            return null;
        }
        try {
            Files.createDirectories(dataDir);
            Path p = dataDir.resolve("journal_stats.csv");
            Files.writeString(p, csv, StandardCharsets.UTF_8);
            return p;
        } catch (IOException e) {
            log.warn("일지 CSV 저장 실패: {}", e.getMessage());
            return null;
        }
    }

    private void execute(String market, List<String> cmd) {
        LocalDateTime started = status(market).startedAt();
        Deque<String> tail = new ArrayDeque<>();
        Integer exit = null;
        String message;
        Path logFile = dataDir.resolveSibling("logs").resolve("batch-" + market + ".log");
        try {
            Files.createDirectories(logFile.getParent());
            ProcessBuilder pb = new ProcessBuilder(cmd).redirectErrorStream(true);
            pb.environment().put("PYTHONIOENCODING", "utf-8");
            pb.environment().put("PYTHONUTF8", "1");
            log.info("배치 시작 [{}]: {}", market, String.join(" ", cmd));
            Process proc = pb.start();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8));
                 Writer w = Files.newBufferedWriter(logFile, StandardCharsets.UTF_8,
                         StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
                w.write("\n===== " + started + " " + market + " =====\n");
                String line;
                while ((line = r.readLine()) != null) {
                    w.write(line);
                    w.write('\n');
                    synchronized (tail) {
                        tail.addLast(line);
                        if (tail.size() > TAIL_LINES) {
                            tail.removeFirst();
                        }
                    }
                    // 진행 중에도 화면에서 로그가 보이도록 갱신
                    status.put(market, new BatchStatus(market, true, started, null, null, "실행 중", List.copyOf(tail)));
                }
            }
            if (!proc.waitFor(TIMEOUT_MINUTES, TimeUnit.MINUTES)) {
                proc.destroyForcibly();
                message = "시간 초과(" + TIMEOUT_MINUTES + "분)로 중단";
            } else {
                exit = proc.exitValue();
                message = exit == 0 ? "완료" : "실패(종료 코드 " + exit + ") — 아래 로그 확인";
            }
        } catch (IOException e) {
            message = "실행 파일을 찾지 못했습니다: " + e.getMessage();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            message = "중단됨";
        }
        status.put(market, new BatchStatus(market, false, started, LocalDateTime.now(), exit, message, List.copyOf(tail)));
        log.info("배치 종료 [{}]: {}", market, message);
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
    }
}
