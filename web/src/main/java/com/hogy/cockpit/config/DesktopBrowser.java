package com.hogy.cockpit.config;

import java.awt.Desktop;
import java.net.URI;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** 기동 완료 시 기본 브라우저로 대시보드 열기(app.open-browser=true). */
@Component
@ConditionalOnProperty(prefix = "app", name = "open-browser", havingValue = "true")
public class DesktopBrowser {

    private static final Logger log = LoggerFactory.getLogger(DesktopBrowser.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        int port = ((WebServerApplicationContext) event.getApplicationContext()).getWebServer().getPort();
        open("http://localhost:" + port + "/");
    }

    /**
     * 브라우저 열기. 실패해도 프로그램은 계속 실행되어야 하므로 예외를 밖으로 던지지 않습니다.
     * (화면 없는 환경에서는 java.awt.AWTError(Error 계열)가 발생 → 별도로 잡아야 함)
     */
    public static void open(String url) {
        try {
            if (Desktop.isDesktopSupported() && Desktop.getDesktop().isSupported(Desktop.Action.BROWSE)) {
                Desktop.getDesktop().browse(URI.create(url));
                return;
            }
        } catch (Exception | java.awt.AWTError e) {
            log.debug("java.awt.Desktop 사용 불가: {}", e.getMessage());
        }
        try {
            String os = System.getProperty("os.name", "").toLowerCase();
            if (os.contains("win")) {
                new ProcessBuilder("rundll32", "url.dll,FileProtocolHandler", url).start();
            } else if (os.contains("mac")) {
                new ProcessBuilder("open", url).start();
            } else {
                new ProcessBuilder("xdg-open", url).start();
            }
        } catch (Exception e) {
            log.warn("브라우저 자동 열기 실패 → 직접 접속하세요: {} ({})", url, e.getMessage());
        }
    }
}
