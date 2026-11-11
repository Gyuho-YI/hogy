package com.hogy.cockpit.web;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import com.hogy.cockpit.config.AppVersion;
import com.hogy.cockpit.config.InstanceRegistry;

/** 런처 전용: 실행 중 버전 확인 / 토큰 기반 종료(업데이트 시 구버전 교체). */
@RestController
public class InstanceController {

    private final ObjectProvider<InstanceRegistry> registry;
    private final ApplicationContext context;

    public InstanceController(ObjectProvider<InstanceRegistry> registry, ApplicationContext context) {
        this.registry = registry;
        this.context = context;
    }

    @GetMapping("/api/instance")
    public Map<String, String> info() {
        return Map.of("app", "cockpit", "version", AppVersion.current());
    }

    @PostMapping("/api/instance/shutdown")
    public ResponseEntity<Map<String, String>> shutdown(@RequestHeader(value = "X-Cockpit-Token", required = false) String token,
                                                        HttpServletRequest req) {
        InstanceRegistry r = registry.getIfAvailable();
        if (r == null || token == null || !token.equals(r.token()) || !isLoopback(req.getRemoteAddr())) {
            return ResponseEntity.status(403).body(Map.of("message", "forbidden"));
        }
        Thread t = new Thread(() -> {
            try {
                Thread.sleep(300);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            System.exit(SpringApplication.exit(context, () -> 0));
        }, "cockpit-replace-shutdown");
        t.start();
        return ResponseEntity.ok(Map.of("message", "bye"));
    }

    private static boolean isLoopback(String addr) {
        try {
            return InetAddress.getByName(addr).isLoopbackAddress();
        } catch (UnknownHostException e) {
            return false;
        }
    }
}
