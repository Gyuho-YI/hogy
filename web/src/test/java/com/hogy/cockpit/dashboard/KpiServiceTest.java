package com.hogy.cockpit.dashboard;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.util.List;

import org.junit.jupiter.api.Test;

import com.hogy.cockpit.journal.JournalStats;
import com.hogy.cockpit.plan.PlanItem;
import com.hogy.cockpit.plan.PlanSnapshot;

class KpiServiceTest {

    private static PlanItem item(String action, double buyHigh, double stop, double t2, int shares) {
        return new PlanItem("000001", "테스트", "점화", action, buyHigh, buyHigh * 0.98, buyHigh, stop,
                (buyHigh - stop) / buyHigh, buyHigh * 1.2, t2, null, 25.0, shares, 0, "", List.of(), List.of());
    }

    @Test
    void 관망_제외_총위험과_현금비중_계산() {
        PlanSnapshot snap = new PlanSnapshot("KR", "2026-10-01", 10_000_000.0, List.of(
                item("지금 매수 가능", 10_000, 9_400, 11_800, 100),   // 위험 60,000 / 투입 1,000,000 / 손익비 3.0
                item("관망", 10_000, 9_000, 13_000, 0)), null);
        Kpi k = KpiService.compute(snap, 140_000, 2_000_000, JournalStats.from(List.of()));

        assertThat(k.actionable()).isEqualTo(1);
        assertThat(k.candidates()).isEqualTo(2);
        assertThat(k.heatPct()).isCloseTo(0.02, within(1e-9));        // (140,000 + 60,000) / 10,000,000
        assertThat(k.cashPct()).isCloseTo(0.70, within(1e-9));        // 1 - 3,000,000 / 10,000,000
        assertThat(k.avgRewardRisk()).isCloseTo(3.0, within(1e-9));
        assertThat(k.heatStatus()).isEqualTo("good");
    }

    @Test
    void 계좌정보가_없으면_비율은_null() {
        PlanSnapshot snap = new PlanSnapshot("KR", null, null, List.of(item("지금 매수 가능", 10_000, 9_400, 11_800, 10)), null);
        Kpi k = KpiService.compute(snap, 0, 0, JournalStats.from(List.of()));
        assertThat(k.heatPct()).isNull();
        assertThat(k.cashPct()).isNull();
        assertThat(k.heatStatus()).isEqualTo("unknown");
    }

    @Test
    void 총위험_10퍼센트_초과는_critical() {
        PlanSnapshot snap = new PlanSnapshot("KR", null, 1_000_000.0, List.of(item("지금 매수 가능", 10_000, 9_000, 13_000, 110)), null);
        assertThat(KpiService.compute(snap, 0, 0, JournalStats.from(List.of())).heatStatus()).isEqualTo("critical");
    }
}
