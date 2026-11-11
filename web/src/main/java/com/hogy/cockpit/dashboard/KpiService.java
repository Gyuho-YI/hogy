package com.hogy.cockpit.dashboard;

import java.util.List;
import java.util.Objects;

import org.springframework.stereotype.Service;

import com.hogy.cockpit.journal.JournalService;
import com.hogy.cockpit.journal.JournalStats;
import com.hogy.cockpit.plan.PlanItem;
import com.hogy.cockpit.plan.PlanSnapshot;
import com.hogy.cockpit.util.SafeMath;

@Service
public class KpiService {

    /** 총 위험 경고 기준: 6% 초과 경고, 10% 초과 위험(국내 테마 동반 급락 대비). */
    static final double HEAT_WARN = 0.06;
    static final double HEAT_CRITICAL = 0.10;

    private final JournalService journal;

    public KpiService(JournalService journal) {
        this.journal = journal;
    }

    public Kpi compute(PlanSnapshot snap, String market) {
        JournalStats stats = journal.stats(market);
        return compute(snap, journal.openRisk(market), journal.openExposure(market), stats);
    }

    /** 순수 계산부(테스트 용이성을 위해 분리). */
    static Kpi compute(PlanSnapshot snap, double openRisk, double openExposure, JournalStats stats) {
        List<PlanItem> items = snap.items() == null ? List.of() : snap.items();
        List<PlanItem> act = items.stream().filter(PlanItem::actionable).toList();
        Double account = snap.account();

        double plannedRisk = act.stream().mapToDouble(PlanItem::plannedRiskAmount).sum();
        double plannedAmount = act.stream().mapToDouble(PlanItem::plannedAmount).sum();

        // 계좌 금액이 없거나 0 이면 비율 계산 불가(null) → 화면에 '-' 표시
        Double heat = SafeMath.ratio(openRisk + plannedRisk, account);
        Double invested = SafeMath.ratio(openExposure + plannedAmount, account);
        Double cash = invested == null ? null : 1 - invested;   // 음수면 계좌 초과 주문(화면에서 경고)

        Double avgRr = act.stream().map(PlanItem::rewardRisk).filter(Objects::nonNull)
                .mapToDouble(Double::doubleValue).average().stream().boxed().findFirst().orElse(null);

        String status = heat == null ? "unknown"
                : heat > HEAT_CRITICAL ? "critical"
                : heat > HEAT_WARN ? "warning" : "good";

        return new Kpi(act.size(), items.size(), heat, status, avgRr, cash,
                stats.expectancy(), stats.samples());
    }
}
