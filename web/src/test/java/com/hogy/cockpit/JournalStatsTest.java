package com.hogy.cockpit;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.hogy.cockpit.journal.JournalStats;

class JournalStatsTest {

    @Test
    void 표본_30건_미만이면_켈리_미적용() {
        JournalStats s = JournalStats.from(List.of(0.2, -0.05, 0.1));
        assertThat(s.halfKelly()).isNull();
        assertThat(s.note()).contains("켈리 미적용");
    }

    @Test
    void 손실이_없으면_손익비_계산불가() {
        List<Double> r = new ArrayList<>();
        for (int i = 0; i < 40; i++) r.add(0.05);
        JournalStats s = JournalStats.from(r);
        assertThat(s.payoff()).isNull();
        assertThat(s.halfKelly()).isNull();
    }

    @Test
    void 충분한_표본이면_wilson_하한으로_하프켈리_계산() {
        List<Double> r = new ArrayList<>();
        for (int i = 0; i < 45; i++) r.add(0.18);
        for (int i = 0; i < 55; i++) r.add(-0.05);
        JournalStats s = JournalStats.from(r);
        assertThat(s.winRateLower()).isLessThan(s.winRate());
        assertThat(s.payoff()).isEqualTo(3.6, org.assertj.core.data.Offset.offset(1e-9));
        assertThat(s.halfKelly()).isPositive();
        assertThat(s.halfKelly()).isEqualTo(s.kelly() / 2);
    }

    @Test
    void 기대값_음수면_매수중단_경고() {
        List<Double> r = new ArrayList<>();
        for (int i = 0; i < 30; i++) r.add(0.03);
        for (int i = 0; i < 70; i++) r.add(-0.05);
        assertThat(JournalStats.from(r).note()).contains("매수 중단");
    }
}
