package com.hogy.cockpit.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * application.yml 의 app.* 설정.
 *
 * @param dataDir         Python 스크리너 출력 폴더(plans_kr.json, plans_us.json 위치)
 * @param username        로그인 ID (1인 전용)
 * @param password        서버 모드 비밀번호(환경변수). 비어 있으면 최초 실행 시 화면에서 설정(DB 저장)
 * @param rememberMeKey   자동 로그인 쿠키 서명 키. 비어 있으면 설치별 임의 키를 DB 에 생성
 * @param desktop         데스크톱 프로그램 모드(종료 버튼 등 표시)
 * @param openBrowser     기동 완료 시 기본 브라우저 자동 열기
 * @param batchEnabled    웹앱이 스크리닝 배치를 직접 실행/예약할지 여부
 * @param screenerCommand 스크리너 실행 명령(쉼표 구분). 비우면 screener.exe → python cli.py 순으로 자동 탐색
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(String dataDir, String username, String password, String rememberMeKey,
                            boolean desktop, boolean openBrowser, boolean batchEnabled, String screenerCommand) {

    public boolean hasEnvPassword() {
        return password != null && !password.isBlank();
    }
}
