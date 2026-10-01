package com.hogy.cockpit.plan;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.hogy.cockpit.util.SafeMath;

/**
 * 종목별 매매 계획 (Python screener/export.py plan_record() 와 1:1 대응).
 * 값이 계산 불가였던 필드는 null 로 들어옵니다.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PlanItem(
        String code, String name, String stage, String action,
        Double close, Double buyLow, Double buyHigh, Double stop, Double riskPct,
        Double t1, Double t2, Double addTrigger, Double weightPct,
        int sharesNow, int sharesAdd, String edgeSource,
        List<String> notes, List<PricePoint> history) {

    /** 화면 정렬 순서: 실행 가능한 것부터. */
    private static final Map<String, Integer> ORDER = Map.of(
            "지금 매수 가능", 0, "돌파 대기(Buy Stop)", 1, "지정가 대기", 2, "관망", 3);

    public int actionOrder() {
        return ORDER.getOrDefault(action, 9);
    }

    /** 주문을 낼 대상인가(관망 제외). */
    public boolean actionable() {
        return action != null && !"관망".equals(action) && sharesNow > 0;
    }

    /** 2차 목표 기준 손익비 = (T2 - 매수상단) / (매수상단 - 손절). 분모 0 이하면 null. */
    @JsonProperty("rewardRisk")
    public Double rewardRisk() {
        if (t2 == null || buyHigh == null || stop == null) {
            return null;
        }
        return SafeMath.ratio(t2 - buyHigh, buyHigh - stop);
    }

    /** 이번 주문이 손절될 때 잃는 금액(매수상단 체결 가정). */
    public double plannedRiskAmount() {
        if (buyHigh == null || stop == null || buyHigh <= stop) {
            return 0.0;
        }
        return sharesNow * (buyHigh - stop);
    }

    /** 이번 주문 투입 금액. */
    public double plannedAmount() {
        return buyHigh == null ? 0.0 : sharesNow * buyHigh;
    }
}
