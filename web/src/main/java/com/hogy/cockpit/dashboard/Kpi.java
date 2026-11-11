package com.hogy.cockpit.dashboard;

/**
 * 대시보드 최상단 5대 KPI (5초 안에 '오늘 무엇을 할지' 판단).
 *
 * @param actionable     오늘 주문 대상 종목 수(관망 제외)
 * @param candidates     전체 후보 수
 * @param heatPct        포트폴리오 총 위험 = (보유 손절위험 + 신규 주문 손절위험) / 계좌. 6% 이하 권장
 * @param heatStatus     good / warning / critical
 * @param avgRewardRisk  주문 대상 평균 손익비(2차 목표 기준)
 * @param cashPct        신규 주문 체결 후 예상 현금 비중
 * @param expectancyPct  실전 매매일지 기대값(거래당 평균 수익률)
 * @param samples        실전 청산 건수
 */
public record Kpi(int actionable, int candidates, Double heatPct, String heatStatus,
                  Double avgRewardRisk, Double cashPct, Double expectancyPct, int samples) {
}
