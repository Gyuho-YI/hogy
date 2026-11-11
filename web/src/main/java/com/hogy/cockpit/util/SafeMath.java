package com.hogy.cockpit.util;

/**
 * 0 나누기·음수 분모를 안전하게 처리하는 계산 유틸 (Python screener/common.py 의 safe_yoy 와 동일 규칙).
 */
public final class SafeMath {

    private SafeMath() {
    }

    /** 성장률 결과. rate 가 null 이면 계산 불가. */
    public record Growth(Double rate, String label) {
    }

    /**
     * 전기 대비 증감률.
     * <ul>
     *   <li>분모(prev)가 null/0 → 계산불가</li>
     *   <li>prev &gt; 0 → (curr - prev) / prev (curr &lt; 0 이면 '적자전환')</li>
     *   <li>prev &lt; 0 (전기 손실) → |prev| 로 나눠 부호 왜곡 방지 + 흑자전환/적자축소/적자확대 라벨</li>
     *   <li>결과가 마이너스여도 그대로 반환(역성장 판단은 화면에서 색·아이콘으로 표시)</li>
     * </ul>
     */
    public static Growth growth(Double curr, Double prev) {
        if (curr == null || prev == null || curr.isNaN() || prev.isNaN() || prev == 0.0) {
            return new Growth(null, "계산불가");
        }
        double rate = (curr - prev) / Math.abs(prev);
        if (prev > 0) {
            return new Growth(rate, curr < 0 ? "적자전환" : "정상");
        }
        if (curr >= 0) {
            return new Growth(rate, "흑자전환");
        }
        if (curr > prev) {
            return new Growth(rate, "적자축소");
        }
        return new Growth(rate, curr.equals(prev) ? "적자지속" : "적자확대");
    }

    /** a / b. 분모가 0 이하이거나 값이 없으면 null. */
    public static Double ratio(Double a, Double b) {
        if (a == null || b == null || b <= 0.0 || a.isNaN() || b.isNaN()) {
            return null;
        }
        return a / b;
    }
}
