package com.hogy.cockpit.plan;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hogy.cockpit.config.AppProperties;

/**
 * plans_{market}.json 파일 로더.
 * 파일 수정 시각이 바뀔 때만 다시 읽습니다(배치가 새 파일을 쓰면 재기동 없이 자동 반영).
 */
@Component
public class PlanRepository {

    private static final Logger log = LoggerFactory.getLogger(PlanRepository.class);
    public static final Set<String> MARKETS = Set.of("kr", "us");

    private final Path dataDir;
    private final ObjectMapper objectMapper;
    private final Map<String, Cached> cache = new ConcurrentHashMap<>();

    private record Cached(FileTime modified, PlanSnapshot snapshot) {
    }

    public PlanRepository(AppProperties props, ObjectMapper objectMapper) {
        this.dataDir = Path.of(props.dataDir()).toAbsolutePath().normalize();
        this.objectMapper = objectMapper;
        log.info("스크리너 데이터 폴더: {}", dataDir);
    }

    /** 시장 코드 검증(kr/us 외에는 404). 경로 조작 방지 목적도 겸함. */
    public static String normalize(String market) {
        String m = market == null ? "" : market.toLowerCase(Locale.ROOT);
        if (!MARKETS.contains(m)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "지원하지 않는 시장: " + market);
        }
        return m;
    }

    public PlanSnapshot load(String market) {
        String m = normalize(market);
        Path file = dataDir.resolve("plans_" + m + ".json");
        if (!Files.exists(file)) {
            return PlanSnapshot.empty(m, "아직 스크리닝 결과가 없습니다: " + file.getFileName());
        }
        try {
            FileTime modified = Files.getLastModifiedTime(file);
            Cached cached = cache.get(m);
            if (cached != null && cached.modified().equals(modified)) {
                return cached.snapshot();
            }
            PlanSnapshot snap = objectMapper.readValue(file.toFile(), PlanSnapshot.class);
            cache.put(m, new Cached(modified, snap));
            return snap;
        } catch (IOException e) {
            log.error("계획 파일 파싱 실패: {}", file, e);
            return PlanSnapshot.empty(m, "계획 파일을 읽지 못했습니다: " + e.getMessage());
        }
    }
}
