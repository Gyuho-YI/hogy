package com.hogy.cockpit.sector;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 섹터(국내 KRX 업종 / 해외 ETF) 1행. Python sector_radar 의 snake_case 키와 매핑.
 *
 * @param share    국내: 오늘 시장 거래대금 내 비중(0~1) / 해외: null
 * @param shift    국내: 비중 증가폭(오늘 비중 − 20일 평균 비중)
 * @param ratio    쏠림 배수(국내: 비중 ÷ 20일 평균 비중, 해외: 거래대금 ÷ 20일 평균). 계산 불가면 null
 * @param change   등락률(%, 국내는 거래대금 가중)
 * @param breadth  국내: 상승 종목 비율 / 해외: 50일선 위(1) 아래(0)
 * @param flag     과열 / 신규 유입 / 유입 / 보통 / 이탈
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SectorRow(
        String sector, String ticker, Double share,
        @JsonProperty("avg_share") Double avgShare, Double shift, Double ratio,
        @JsonProperty("share_trend") Boolean shareTrend,
        Double change, Double breadth, Integer stocks, Double value,
        Double r1w, Double r1m, @JsonProperty("rs_1m") Double rs1m,
        Double score, String flag, List<Leader> leaders) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Leader(String code, String name, Double change, Double value) {
    }

    /** 자금이 들어오는 중인가(화면 강조용). */
    public boolean inflow() {
        return flag != null && (flag.contains("유입") || "과열".equals(flag));
    }
}
