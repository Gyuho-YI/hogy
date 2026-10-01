package com.hogy.cockpit.config;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

/**
 * 1인 전용 보안 설정.
 * - 계정은 메모리에 1개만 존재(회원가입 없음)
 * - 폼 로그인 + 30일 자동 로그인(모바일에서 매번 로그인하지 않도록)
 * - CSRF 보호 유지(Thymeleaf 폼에 토큰 자동 삽입)
 */
@Configuration
public class SecurityConfig {

    private static final Logger log = LoggerFactory.getLogger(SecurityConfig.class);

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AppProperties props, PasswordEncoder encoder) {
        String raw = props.password();
        if (raw == null || raw.isBlank()) {
            // 비밀번호 미설정 상태로 외부에 노출되는 사고 방지: 매 기동마다 임시 비밀번호 생성
            raw = UUID.randomUUID().toString().substring(0, 12);
            log.warn("APP_PASSWORD 미설정 → 임시 비밀번호: {} (환경변수로 고정하세요)", raw);
        }
        return new InMemoryUserDetailsManager(
                User.withUsername(props.username()).password(encoder.encode(raw)).roles("OWNER").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, AppProperties props,
                                            UserDetailsService uds) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**", "/js/**", "/favicon.ico", "/actuator/health").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard/kr", true)
                .permitAll())
            .rememberMe(rm -> rm
                .key(props.rememberMeKey())
                .userDetailsService(uds)
                .tokenValiditySeconds(30 * 24 * 3600))
            .logout(lo -> lo.logoutSuccessUrl("/login?logout"));
        return http.build();
    }
}
