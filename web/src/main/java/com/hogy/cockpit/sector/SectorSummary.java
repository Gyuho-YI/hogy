package com.hogy.cockpit.sector;

/**
 * [섹터] 화면 최상단 5대 KPI.
 *
 * @param topSector     쏠림 배수 최대 섹터명(자금 1위)
 * @param topRatio      1위 섹터 쏠림 배수
 * @param inflow        유입·신규 유입 섹터 수
 * @param overheated    과열 섹터 수(추격 주의)
 * @param outflow       이탈 섹터 수
 * @param topTheme      1위 테마(국내) / 상대강도 1위(해외)
 * @param breadthPct    국내: 전체 섹터 거래대금 가중 상승 비율 / 해외: 50일선 위 ETF 비율
 */
public record SectorSummary(String topSector, Double topRatio, int inflow, int overheated, int outflow,
                            String topTheme, Double breadthPct) {
}
