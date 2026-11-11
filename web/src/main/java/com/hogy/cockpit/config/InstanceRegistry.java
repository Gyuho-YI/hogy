package com.hogy.cockpit.config;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.UUID;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * 데스크톱 모드 실행 정보 파일(data/instance.properties): 버전·PID·종료 토큰.
 * 새 버전 런처가 이 토큰으로 이전 버전에 '정상 종료'를 요청 → 업데이트 시 구버전 화면이 계속 뜨는 문제 방지.
 * 토큰은 사용자 폴더 파일로만 공유되므로 같은 PC 의 다른 사용자/웹페이지가 종료를 요청할 수 없음.
 */
@Component
@ConditionalOnProperty(prefix = "app", name = "desktop", havingValue = "true")
public class InstanceRegistry {

    private static final Logger log = LoggerFactory.getLogger(InstanceRegistry.class);

    private final Path file;
    private final String token = UUID.randomUUID().toString();

    public InstanceRegistry(AppProperties props) {
        this.file = instanceFile(Path.of(props.dataDir()));
    }

    /** 출력 폴더(.../Cockpit/output) 옆 data 폴더의 instance.properties. */
    public static Path instanceFile(Path dataDir) {
        return dataDir.toAbsolutePath().normalize().resolveSibling("data").resolve("instance.properties");
    }

    public String token() {
        return token;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void register() {
        Properties p = new Properties();
        p.setProperty("version", AppVersion.current());
        p.setProperty("pid", String.valueOf(ProcessHandle.current().pid()));
        p.setProperty("token", token);
        try {
            Files.createDirectories(file.getParent());
            try (OutputStream out = Files.newOutputStream(file)) {
                p.store(out, "Cockpit running instance");
            }
        } catch (IOException e) {
            log.warn("실행 정보 파일 기록 실패: {}", e.getMessage());
        }
    }

    @PreDestroy
    public void unregister() {
        try {
            // 다른 인스턴스가 덮어쓴 파일은 지우지 않음
            if (Files.exists(file) && token.equals(read(file).getProperty("token"))) {
                Files.delete(file);
            }
        } catch (IOException ignored) {
            // 종료 중 정리 실패는 무시(다음 실행 시 덮어씀)
        }
    }

    public static Properties read(Path f) throws IOException {
        Properties p = new Properties();
        try (InputStream in = Files.newInputStream(f)) {
            p.load(in);
        }
        return p;
    }
}
