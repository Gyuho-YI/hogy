package com.hogy.cockpit.sector;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * sectors_{market}.json 전체.
 *
 * @param hotCodes  종목코드 → '주도 섹터: …' / '주도 테마: …' (매매 계획표 배지용)
 * @param loadError 파일 없음/파싱 실패 사유(정상이면 null)
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SectorSnapshot(String market, String generatedAt, List<SectorRow> sectors,
                             List<ThemeRow> themes, Map<String, String> hotCodes, String loadError) {

    public static SectorSnapshot empty(String market, String reason) {
        return new SectorSnapshot(market.toUpperCase(), null, List.of(), List.of(), Map.of(), reason);
    }

    public List<SectorRow> safeSectors() {
        return sectors == null ? List.of() : sectors;
    }

    public List<ThemeRow> safeThemes() {
        return themes == null ? List.of() : themes;
    }

    public Map<String, String> safeHotCodes() {
        return hotCodes == null ? Map.of() : hotCodes;
    }
}
