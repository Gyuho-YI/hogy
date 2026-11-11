package com.hogy.cockpit;

import java.util.Arrays;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

import com.hogy.cockpit.config.DesktopLauncher;

/**
 * 개인용 트레이딩 콕핏.
 * <ul>
 *   <li>Python 스크리너가 만든 plans_{kr,us}.json 을 읽어 매매 계획 대시보드로 표시</li>
 *   <li>실제 매매를 일지(H2 파일 DB)에 기록 → 실전 승률·손익비·하프켈리를 스크리너에 다시 공급</li>
 *   <li>데스크톱 모드(--desktop 또는 -Dcockpit.desktop=true): 브라우저 자동 실행, 배치 내장, 중복 실행 방지</li>
 * </ul>
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class CockpitApplication {

    /** 데스크톱 모드 고정 포트(개발용 8080 과 충돌 방지). */
    public static final int DESKTOP_PORT = 18080;

    public static void main(String[] args) {
        boolean desktop = Boolean.getBoolean("cockpit.desktop") || Arrays.asList(args).contains("--desktop");
        SpringApplication app = new SpringApplication(CockpitApplication.class);
        if (desktop) {
            // 이미 실행 중: 같은 버전이면 브라우저만, 다른 버전이면 이전 버전 종료 후 교체
            java.nio.file.Path dataDir = java.nio.file.Path.of(System.getProperty("user.home"), "Cockpit", "output");
            if (DesktopLauncher.prepare(DESKTOP_PORT, dataDir) == DesktopLauncher.Decision.EXIT) {
                return;
            }
            app.setHeadless(false);              // 브라우저 열기·확인 창(java.awt)에 필요
            app.setAdditionalProfiles("desktop");
        }
        app.run(args);
    }
}
