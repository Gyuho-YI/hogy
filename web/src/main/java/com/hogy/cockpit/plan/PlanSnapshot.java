package com.hogy.cockpit.plan;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 하루치 스크리닝 결과 묶음.
 *
 * @param stats     단계별 통과 수(해외: scanned/received/trend/fundamental/setup, 국내: scanned/candidates/setup)
 * @param loadError 파일이 없거나 파싱 실패 시 사유(정상이면 null)
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PlanSnapshot(String market, String generatedAt, Double account,
                           Map<String, Integer> stats, List<PlanItem> items, String loadError) {

    public static PlanSnapshot empty(String market, String reason) {
        return new PlanSnapshot(market.toUpperCase(), null, null, Map.of(), List.of(), reason);
    }

    /** 단계별 통과 수(없으면 빈 맵). 결과 0건이어도 '정상 완료'인지 보여주는 근거. */
    public Map<String, Integer> safeStats() {
        return stats == null ? Map.of() : stats;
    }

    /** 실행 가능(관망 제외) 종목 수. */
    public long actionableCount() {
        return items == null ? 0 : items.stream().filter(PlanItem::actionable).count();
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
