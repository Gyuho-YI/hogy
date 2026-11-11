package com.hogy.cockpit.plan;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hogy.cockpit.config.AppProperties;

/**
 * plans_{market}.json 파일 로더(수정 시각 기반 캐시: {@link JsonFileCache}).
 */
@Component
public class PlanRepository {

    private static final Logger log = LoggerFactory.getLogger(PlanRepository.class);
    public static final Set<String> MARKETS = Set.of("kr", "us");

    private final Path dataDir;
    private final JsonFileCache<PlanSnapshot> files;

    public PlanRepository(AppProperties props, ObjectMapper objectMapper) {
        this.dataDir = Path.of(props.dataDir()).toAbsolutePath().normalize();
        this.files = new JsonFileCache<>(objectMapper, PlanSnapshot.class);
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
        try {
            PlanSnapshot snap = files.read(file);
            return snap != null ? snap
                    : PlanSnapshot.empty(m, "아직 스크리닝 결과가 없습니다: " + file.getFileName());
        } catch (IOException e) {
            log.error("계획 파일 파싱 실패: {}", file, e);
            return PlanSnapshot.empty(m, "계획 파일을 읽지 못했습니다: " + e.getMessage());
        }
    }

    /** 같은 출력 폴더의 다른 파일(sectors_*.json 등) 경로. */
    public Path dataFile(String name) {
        return dataDir.resolve(name);
    }
}
