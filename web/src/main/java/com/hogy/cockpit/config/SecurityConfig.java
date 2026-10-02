package com.hogy.cockpit.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

import com.hogy.cockpit.settings.SettingsService;

/**
 * 1인 전용 보안 설정.
 * <ul>
 *   <li>서버 모드: APP_PASSWORD 환경변수 비밀번호</li>
 *   <li>데스크톱 모드: 최초 실행 시 /setup 화면에서 비밀번호 설정 → BCrypt 해시로 DB 저장</li>
 *   <li>폼 로그인 + 30일 자동 로그인, CSRF 보호 유지</li>
 * </ul>
 */
@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AppProperties props, SettingsService settings, PasswordEncoder encoder) {
        // 환경변수 비밀번호는 기동 시 1회만 해시
        String envHash = props.hasEnvPassword() ? encoder.encode(props.password()) : null;
        return username -> {
            if (!props.username().equals(username)) {
                throw new UsernameNotFoundException(username);
            }
            String hash = envHash != null ? envHash : settings.get().getPasswordHash();
            if (hash == null) {
                throw new UsernameNotFoundException("비밀번호 미설정");
            }
            return User.withUsername(username).password(hash).roles("OWNER").build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, SettingsService settings,
                                            UserDetailsService uds) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/setup", "/css/**", "/js/**", "/favicon.ico").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard/kr", true)
                .permitAll())
            .rememberMe(rm -> rm
                .key(settings.rememberKey())
                .userDetailsService(uds)
                .tokenValiditySeconds(30 * 24 * 3600))
            .logout(lo -> lo.logoutSuccessUrl("/login?logout"));
        return http.build();
    }
}
