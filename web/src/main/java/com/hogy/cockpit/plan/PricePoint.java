package com.hogy.cockpit.plan;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 일봉 1개. d = yyyy-MM-dd, o/h/l/c = 시가·고가·저가·종가, v = 거래량.
 * 이전 버전 스크리너 출력은 종가(c)만 있으므로 o/h/l/v 는 null 일 수 있습니다(화면은 선 차트로 대체).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PricePoint(String d, Double o, Double h, Double l, Double c, Double v) {

    public PricePoint(String d, Double c) {
        this(d, null, null, null, c, null);
    }

    public boolean hasOhlc() {
        return o != null && h != null && l != null && c != null;
    }
}
