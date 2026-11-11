package com.hogy.cockpit.journal;

import java.util.List;

/**
 * 실전 매매 통계 + 하프 켈리.
 * Python trade_plan.py 와 같은 규칙: Wilson 하한 승률, 표본 30건 미만이면 켈리 미적용.
 */
public record JournalStats(int samples, Double winRate, Double winRateLower, Double avgWin, Double avgLoss,
                           Double payoff, Double expectancy, Double kelly, Double halfKelly, String note) {

    public static final int MIN_SAMPLES = 30;

    public static JournalStats from(List<Double> returns) {
        List<Double> r = returns.stream().filter(x -> x != null && !x.isNaN()).toList();
        int n = r.size();
        if (n == 0) {
            return new JournalStats(0, null, null, null, null, null, null, null, null, "청산된 매매가 없습니다");
        }
        List<Double> wins = r.stream().filter(x -> x > 0).toList();
        List<Double> losses = r.stream().filter(x -> x <= 0).toList();
        double p = (double) wins.size() / n;
        Double avgWin = wins.isEmpty() ? null : wins.stream().mapToDouble(Double::doubleValue).average().orElse(0);
        Double avgLoss = losses.isEmpty() ? null : losses.stream().mapToDouble(Double::doubleValue).average().orElse(0);
        double expectancy = r.stream().mapToDouble(Double::doubleValue).average().orElse(0);

        // 손익비: 평균손실이 0(본전 청산만 있음)이거나 없으면 계산 불가
        Double payoff = (avgWin != null && avgLoss != null && avgLoss < 0) ? avgWin / Math.abs(avgLoss) : null;
        double pLower = wilsonLower(p, n, 1.0);

        if (n < MIN_SAMPLES || payoff == null) {
            String why = n < MIN_SAMPLES ? "표본 " + n + "건 < " + MIN_SAMPLES : "손익 분포 불충분";
            return new JournalStats(n, p, pLower, avgWin, avgLoss, payoff, expectancy, null, null,
                    why + " → 켈리 미적용(고정 위험 1%)");
        }
        double kelly = pLower - (1 - pLower) / payoff;
        double half = kelly / 2;
        String note = half <= 0 ? "기대값 ≤ 0 → 신규 매수 중단 검토" : "하프켈리 위험 비율(상한 2% 적용 권장)";
        return new JournalStats(n, p, pLower, avgWin, avgLoss, payoff, expectancy, kelly, half, note);
    }

    /** 승률 Wilson 하한(z=1.0). 표본이 적을수록 보수적으로 낮아짐. */
    static double wilsonLower(double p, int n, double z) {
        if (n == 0) {
            return 0;
        }
        double d = 1 + z * z / n;
        double c = p + z * z / (2.0 * n);
        double m = z * Math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n));
        return (c - m) / d;
    }
}
