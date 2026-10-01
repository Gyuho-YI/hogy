package com.hogy.cockpit.plan;

import java.util.Comparator;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 하루치 스크리닝 결과 묶음.
 *
 * @param loadError 파일이 없거나 파싱 실패 시 사유(정상이면 null)
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PlanSnapshot(String market, String generatedAt, Double account,
                           List<PlanItem> items, String loadError) {

    public static PlanSnapshot empty(String market, String reason) {
        return new PlanSnapshot(market.toUpperCase(), null, null, List.of(), reason);
    }

    /** 실행 가능 순 → 손익비 높은 순 정렬 사본. */
    public List<PlanItem> sortedItems() {
        if (items == null) {
            return List.of();
        }
        return items.stream()
                .sorted(Comparator.comparingInt(PlanItem::actionOrder)
                        .thenComparing(PlanItem::rewardRisk, Comparator.nullsLast(Comparator.reverseOrder())))
                .toList();
    }

    public PlanItem find(String code) {
        return items == null ? null
                : items.stream().filter(i -> i.code().equals(code)).findFirst().orElse(null);
    }
}
