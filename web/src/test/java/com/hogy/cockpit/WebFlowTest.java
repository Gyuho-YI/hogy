package com.hogy.cockpit;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** 샘플 계획 JSON(src/test/resources/testdata)으로 로그인 → 대시보드 → 일지 흐름 검증. */
@SpringBootTest(properties = {
        "app.data-dir=src/test/resources/testdata",
        "app.password=test-pass",
        "spring.datasource.url=jdbc:h2:mem:cockpit-test;DB_CLOSE_DELAY=-1"})
@AutoConfigureMockMvc
class WebFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void 비로그인_접근은_로그인_페이지로() throws Exception {
        mvc.perform(get("/dashboard/kr")).andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void 지원하지_않는_시장은_404() throws Exception {
        mvc.perform(get("/dashboard/jp").with(user("owner"))).andExpect(status().isNotFound());
    }

    @Test
    void 대시보드에_KPI와_계획표_표시() throws Exception {
        mvc.perform(get("/dashboard/kr").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("오늘 주문 대상")))
           .andExpect(content().string(containsString("SK하이닉스")))
           .andExpect(content().string(containsString("매수 가능")));
        mvc.perform(get("/dashboard/us").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("돌파 대기")));
    }

    @Test
    void API는_손익비를_포함한_JSON() throws Exception {
        mvc.perform(get("/api/plans/kr").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.items[0].rewardRisk").isNumber())
           .andExpect(jsonPath("$.items[0].history").isArray());
    }

    @Test
    void 일지_기록_청산_내보내기() throws Exception {
        mvc.perform(get("/journal/kr").param("code", "000660").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("value=\"000660\"")));

        mvc.perform(post("/journal/kr").with(user("owner")).with(csrf())
                .param("code", "000660").param("name", "SK하이닉스").param("strategy", "IGNITION")
                .param("entryDate", "2026-09-01").param("entryPrice", "200000").param("quantity", "10")
                .param("stopPrice", "190000"))
           .andExpect(redirectedUrl("/journal/kr"));

        mvc.perform(post("/journal/kr/1/close").with(user("owner")).with(csrf())
                .param("exitDate", "2026-09-20").param("exitPrice", "230000"))
           .andExpect(redirectedUrl("/journal/kr"));

        mvc.perform(get("/journal/export.csv").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("B.점화진입,0.150000,KR,000660")));

        mvc.perform(get("/api/journal/kr/monthly").with(user("owner")))
           .andExpect(jsonPath("$[0].month").value("2026-09"))
           .andExpect(jsonPath("$[0].momLabel").value("계산불가"));
    }

    @Test
    void 필수값_누락시_폼_재표시() throws Exception {
        mvc.perform(post("/journal/kr").with(user("owner")).with(csrf()).param("code", "X"))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("필수 항목")));
    }
}
