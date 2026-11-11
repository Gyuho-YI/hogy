package com.hogy.cockpit.plan;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 일봉 시뮬레이션 결과(screener/simulate.py SimResult.to_record).
 *
 * @param pTarget     1차 목표(2R) 선도달 확률(0~1)
 * @param pStop       손절 선도달 확률
 * @param pOpen       60영업일 내 미결
 * @param expR        평균 R(+1R = 위험 금액만큼 이익)
 * @param histN       같은 손절·목표폭으로 과거 매일 진입한 재현 표본 수
 * @param fan         일자별 종가 분위수(p10~p90), 진입가 = 1.0
 * @param rHist       R 분포 [{r, share}]
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SimSummary(Integer n, Double pTarget, Double pStop, Double pOpen, Double expR, Double medianR,
                         Double avgDays, Double targetR, Integer histN, Double histPTarget, Double histPStop,
                         Double histExpR, Map<String, List<Double>> fan, List<Map<String, Double>> rHist) {
}
