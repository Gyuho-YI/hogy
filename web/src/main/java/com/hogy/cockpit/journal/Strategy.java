package com.hogy.cockpit.journal;

/**
 * 매매 전략 구분. label 은 Python entry_backtest.py 의 strategy 컬럼명과 동일하게 맞춰
 * 일지 CSV 를 plan_screener.py --stats 에 그대로 넣을 수 있게 합니다.
 */
public enum Strategy {
    PRE("A.선진입"),
    IGNITION("B.점화진입"),
    PULLBACK("C.눌림매수"),
    US_BREAKOUT("US.VCP돌파");

    private final String label;

    Strategy(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    /** 계획의 단계(stage) → 기본 전략 추정. */
    public static Strategy fromStage(String stage, String market) {
        if ("us".equalsIgnoreCase(market)) {
            return US_BREAKOUT;
        }
        if (stage != null && stage.startsWith("매집")) {
            return PRE;
        }
        return IGNITION;
    }
}
