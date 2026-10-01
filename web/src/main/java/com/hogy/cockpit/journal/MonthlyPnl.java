package com.hogy.cockpit.journal;

/** 월별 실현손익과 전월 대비 증감(SafeMath.growth 규칙). */
public record MonthlyPnl(String month, double pnl, int trades, Double momRate, String momLabel) {
}
