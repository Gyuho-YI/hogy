package com.hogy.cockpit.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * application.yml 의 app.* 설정. 비밀값은 반드시 환경변수로 주입합니다.
 *
 * @param dataDir       Python 스크리너 출력 폴더(plans_kr.json, plans_us.json 위치)
 * @param username      로그인 ID (1인 전용)
 * @param password      로그인 비밀번호. 비어 있으면 기동 시 임시 비밀번호를 생성해 로그에 출력
 * @param rememberMeKey 자동 로그인 쿠키 서명 키
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(String dataDir, String username, String password, String rememberMeKey) {
}
