package com.hogy.cockpit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import com.hogy.cockpit.batch.BatchService;
import com.hogy.cockpit.batch.BatchStatus;

/**
 * 데스크톱 모드 흐름: 최초 비밀번호 설정 → 로그인 → 계좌 설정 → 스크리닝 실행.
 * 스크리너 대신 echo 로 전달 인자를 검증합니다(Windows 는 echo 가 실행 파일이 아니므로 제외).
 */
@SpringBootTest(properties = {
        "app.data-dir=target/desktop-test/output",
        "app.password=",
        "app.batch-enabled=true",
        "app.screener-command=echo",
        "spring.datasource.url=jdbc:h2:mem:cockpit-desktop;DB_CLOSE_DELAY=-1"})
@AutoConfigureMockMvc
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@DisabledOnOs(OS.WINDOWS)
class DesktopFlowTest {

    @Autowired
    MockMvc mvc;
    @Autowired
    BatchService batch;

    @Test
    @Order(1)
    void 비밀번호_미설정이면_설정화면으로() throws Exception {
        mvc.perform(get("/login")).andExpect(redirectedUrl("/setup"));
        mvc.perform(get("/setup")).andExpect(status().isOk()).andExpect(content().string(containsString("처음 설정")));
    }

    @Test
    @Order(2)
    void 비밀번호_검증_후_저장_재설정은_차단() throws Exception {
        mvc.perform(post("/setup").with(csrf()).param("password", "short").param("confirm", "short"))
           .andExpect(content().string(containsString("8자 이상")));
        mvc.perform(post("/setup").with(csrf()).param("password", "longpassword").param("confirm", "different1"))
           .andExpect(content().string(containsString("일치하지 않습니다")));
        mvc.perform(post("/setup").with(csrf()).param("password", "longpassword").param("confirm", "longpassword"))
           .andExpect(redirectedUrl("/login?setup"));
        // 이미 설정됨 → 덮어쓰기 불가
        mvc.perform(post("/setup").with(csrf()).param("password", "hijacked123").param("confirm", "hijacked123"))
           .andExpect(redirectedUrl("/login"));
        mvc.perform(formLogin().user("owner").password("hijacked123")).andExpect(unauthenticated());
        mvc.perform(formLogin().user("owner").password("longpassword")).andExpect(authenticated());
    }

    @Test
    @Order(3)
    void 계좌_미설정이면_실행_거절() throws Exception {
        mvc.perform(post("/settings/batch/kr").with(user("owner")).with(csrf()))
           .andExpect(flash().attribute("error", containsString("계좌 금액")));
    }

    @Test
    @Order(4)
    void 계좌_설정_후_스크리너에_인자_전달() throws Exception {
        mvc.perform(post("/settings/trading").with(user("owner")).with(csrf())
                .param("accountKr", "30000000").param("accountUs", "20000").param("autoBatch", "true"))
           .andExpect(redirectedUrl("/settings"));
        mvc.perform(post("/settings/batch/kr").with(user("owner")).with(csrf()))
           .andExpect(flash().attribute("ok", containsString("시작")));

        BatchStatus s = batch.status("kr");
        for (int i = 0; i < 50 && s.running(); i++) {
            Thread.sleep(100);
            s = batch.status("kr");
        }
        assertThat(s.success()).isTrue();
        assertThat(String.join("\n", s.tail())).contains("kr --account 30000000 --out").contains("desktop-test");

        mvc.perform(get("/settings").with(user("owner")))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("✓ 완료")));
    }

    @Test
    @Order(5)
    void 서버모드에서는_종료_불가() throws Exception {
        mvc.perform(post("/settings/shutdown").with(user("owner")).with(csrf()))
           .andExpect(status().isBadRequest());
    }
}
