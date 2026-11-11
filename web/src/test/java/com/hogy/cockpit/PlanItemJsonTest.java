package com.hogy.cockpit;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hogy.cockpit.plan.PlanItem;
import com.hogy.cockpit.plan.PlanSnapshot;

/** 스크리너 신규 필드(시뮬레이션·진입 보류·일봉 OHLC·실수형 통계) 역직렬화와 화면 라벨. */
class PlanItemJsonTest {

    private final ObjectMapper om = new ObjectMapper();

    @Test
    void 신규_필드_역직렬화() throws Exception {
        String json = """
            {"market":"US","generatedAt":"2026-11-10T07:10:00","account":20000,
             "stats":{"scanned":1550,"setup":3,"gated":1,"heatUsed":0.052},
             "items":[{"code":"NVDA","name":"NVDA","stage":"점화","action":"관망","sharesNow":0,"sharesAdd":0,
               "blocks":["earnings"],"rrResistance":2.4,"score":93.1,"sector":"Technology",
               "earningsDate":"2026-11-19","earningsDays":3,
               "fundamentals":{"epsYoy":136.0,"epsAccel":true},
               "sim":{"n":10000,"pTarget":0.39,"pStop":0.16,"expR":1.03,"histN":301,
                      "fan":{"p50":[1.0,1.01]},"rHist":[{"r":-1.0,"share":0.2}]},
               "history":[{"d":"2026-11-10","o":190,"h":195,"l":189,"c":192.9,"v":1000000}]}]}
            """;
        PlanSnapshot s = om.readValue(json, PlanSnapshot.class);
        assertThat(s.safeStats().get("heatUsed").doubleValue()).isEqualTo(0.052);
        assertThat(s.safeStats().get("gated").intValue()).isEqualTo(1);
        PlanItem it = s.items().get(0);
        assertThat(it.sim().pTarget()).isEqualTo(0.39);
        assertThat(it.sim().fan().get("p50")).hasSize(2);
        assertThat(it.history().get(0).hasOhlc()).isTrue();
        assertThat(it.blockLabels()).containsExactly("실적 발표");
        assertThat(it.actionLabel()).isEqualTo("보류");
        assertThat(it.actionKey()).isEqualTo("held");
    }

    @Test
    void 이전_버전_JSON_호환() throws Exception {
        String json = """
            {"code":"005930","name":"삼성전자","stage":"관찰(추세 통과)","action":"관망","sharesNow":0,"sharesAdd":0,
             "history":[{"d":"2026-10-01","c":69000}]}
            """;
        PlanItem it = om.readValue(json, PlanItem.class);
        assertThat(it.sim()).isNull();
        assertThat(it.blockLabels()).isEmpty();
        assertThat(it.history().get(0).hasOhlc()).isFalse();
        assertThat(it.actionLabel()).isEqualTo("관찰");
    }
}
