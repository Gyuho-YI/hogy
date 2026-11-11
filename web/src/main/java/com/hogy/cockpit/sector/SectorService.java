package com.hogy.cockpit.sector;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hogy.cockpit.plan.JsonFileCache;
import com.hogy.cockpit.plan.PlanRepository;

/** sectors_{market}.json 로드 + 요약 KPI 계산. */
@Service
public class SectorService {

    private static final Logger log = LoggerFactory.getLogger(SectorService.class);

    private final PlanRepository plans;
    private final JsonFileCache<SectorSnapshot> files;

    public SectorService(PlanRepository plans, ObjectMapper objectMapper) {
        this.plans = plans;
        this.files = new JsonFileCache<>(objectMapper, SectorSnapshot.class);
    }

    public SectorSnapshot load(String market) {
        String m = PlanRepository.normalize(market);
        Path file = plans.dataFile("sectors_" + m + ".json");
        try {
            SectorSnapshot s = files.read(file);
            return s != null ? s : SectorSnapshot.empty(m, "아직 섹터 분석 결과가 없습니다. [설정]에서 스크리닝을 실행하세요.");
        } catch (IOException e) {
            log.error("섹터 파일 파싱 실패: {}", file, e);
            return SectorSnapshot.empty(m, "섹터 파일을 읽지 못했습니다: " + e.getMessage());
        }
    }

    public static SectorSummary summarize(SectorSnapshot s) {
        List<SectorRow> rows = s.safeSectors();
        // '자금 1위' = 점수 1위가 아니라 쏠림 배수 최대(돈이 가장 많이 몰린 곳)
        SectorRow top = rows.stream().filter(r -> r.ratio() != null)
                .max(Comparator.comparingDouble(SectorRow::ratio)).orElse(null);
        int inflow = (int) rows.stream().filter(r -> r.flag() != null && r.flag().contains("유입")).count();
        int hot = (int) rows.stream().filter(r -> "과열".equals(r.flag())).count();
        int out = (int) rows.stream().filter(r -> "이탈".equals(r.flag())).count();

        String topTheme;
        if (!s.safeThemes().isEmpty()) {
            topTheme = s.safeThemes().get(0).theme();
        } else {
            // 해외: 1개월 상대강도 1위 ETF
            topTheme = rows.stream().filter(r -> r.rs1m() != null)
                    .max(Comparator.comparingDouble(SectorRow::rs1m)).map(SectorRow::sector).orElse(null);
        }

        // 확산도: 국내는 거래대금 가중 상승 비율, 해외는 50일선 위 ETF 비율 (분모 0 이면 null)
        double wSum = 0;
        double bSum = 0;
        for (SectorRow r : rows) {
            if (r.breadth() == null) {
                continue;
            }
            double w = "US".equalsIgnoreCase(s.market()) ? 1.0 : Objects.requireNonNullElse(r.value(), 0.0);
            wSum += w;
            bSum += w * r.breadth();
        }
        Double breadth = wSum > 0 ? bSum / wSum : null;
        return new SectorSummary(top == null ? null : top.sector(), top == null ? null : top.ratio(),
                inflow, hot, out, topTheme, breadth);
    }
}
