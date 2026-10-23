package com.hogy.cockpit.config;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 데스크톱 런처: 같은 포트에 Cockpit 이 이미 실행 중일 때의 처리.
 * <ul>
 *   <li>같은 버전 → 새로 띄우지 않고 브라우저만 열기(중복 실행 방지)</li>
 *   <li>다른 버전(업데이트) → 이전 버전 종료 후 새 버전 기동
 *     <ol>
 *       <li>v0.3.1+ : instance.properties 의 토큰으로 정상 종료 요청</li>
 *       <li>v0.3.0 이하(종료 기능 없음): 사용자 확인 후 해당 포트를 쓰는 프로세스만 종료(Windows)</li>
 *     </ol>
 *   </li>
 * </ul>
 */
public final class DesktopLauncher {

    /** 실행 계속 여부. */
    public enum Decision { START, EXIT }

    private static final Pattern VERSION = Pattern.compile("\"version\"\\s*:\\s*\"([^\"]+)\"");

    private DesktopLauncher() {
    }

    public static Decision prepare(int port, Path dataDir) {
        String base = "http://localhost:" + port + "/";
        if (!respondsWithCockpit(base + "login")) {
            return Decision.START;                         // 실행 중인 것 없음
        }
        String running = runningVersion(base + "api/instance");   // 구버전은 엔드포인트 없음 → null
        String mine = AppVersion.current();
        if (mine.equals(running)) {
            DesktopBrowser.open(base);
            return Decision.EXIT;
        }
        System.out.printf("실행 중 버전(%s) ≠ 새 버전(%s) → 교체%n", running == null ? "v0.3.0 이하" : running, mine);

        boolean asked = stopByToken(base, InstanceRegistry.instanceFile(dataDir));
        if (!asked) {
            // 토큰 종료 불가(구버전): 사용자 동의 후 포트 점유 프로세스 종료
            if (!confirm("이전 버전 Cockpit 이 실행 중입니다.\n이전 버전을 종료하고 새 버전(" + mine + ")으로 실행할까요?")) {
                DesktopBrowser.open(base);
                return Decision.EXIT;
            }
            asked = killPortOwner(port);
        }
        if (asked && waitUntilFree(base + "login", 20_000)) {
            return Decision.START;
        }
        message("이전 버전을 종료하지 못했습니다.\n작업 관리자에서 Cockpit 을 종료한 뒤 다시 실행하세요.");
        DesktopBrowser.open(base);
        return Decision.EXIT;
    }

    // ------------------------------------------------------------------

    static boolean respondsWithCockpit(String url) {
        try {
            HttpURLConnection c = open(url, "GET");
            if (c.getResponseCode() != 200) {
                return false;
            }
            return read(c).contains("Cockpit");
        } catch (IOException e) {
            return false;
        }
    }

    static String runningVersion(String url) {
        try {
            HttpURLConnection c = open(url, "GET");
            c.setInstanceFollowRedirects(false);              // 구버전: 로그인 페이지로 리다이렉트 → 버전 없음
            if (c.getResponseCode() != 200 || c.getContentType() == null || !c.getContentType().contains("json")) {
                return null;
            }
            Matcher m = VERSION.matcher(read(c));
            return m.find() ? m.group(1) : null;
        } catch (IOException e) {
            return null;
        }
    }

    static boolean stopByToken(String base, Path instanceFile) {
        if (!Files.exists(instanceFile)) {
            return false;
        }
        try {
            Properties p = InstanceRegistry.read(instanceFile);
            HttpURLConnection c = open(base + "api/instance/shutdown", "POST");
            c.setRequestProperty("X-Cockpit-Token", p.getProperty("token", ""));
            c.setDoOutput(true);
            c.getOutputStream().close();
            return c.getResponseCode() == 200;
        } catch (IOException e) {
            return false;
        }
    }

    /** Windows: netstat 로 포트 LISTENING PID 를 찾아 종료. 자기 자신은 제외. */
    static boolean killPortOwner(int port) {
        if (!System.getProperty("os.name", "").toLowerCase().contains("win")) {
            return false;
        }
        try {
            Process p = new ProcessBuilder("netstat", "-ano", "-p", "tcp").redirectErrorStream(true).start();
            String pid = null;
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
                String line;
                while ((line = r.readLine()) != null) {
                    String[] f = line.trim().split("\\s+");
                    if (f.length >= 5 && f[1].endsWith(":" + port) && "LISTENING".equalsIgnoreCase(f[3])) {
                        pid = f[4];
                        break;
                    }
                }
            }
            if (pid == null || pid.equals(String.valueOf(ProcessHandle.current().pid()))) {
                return false;
            }
            return new ProcessBuilder("taskkill", "/PID", pid, "/F").start().waitFor() == 0;
        } catch (IOException e) {
            return false;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    static boolean waitUntilFree(String url, long timeoutMs) {
        long end = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < end) {
            if (!respondsWithCockpit(url)) {
                try {
                    Thread.sleep(800);                       // 포트 해제 여유
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return true;
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    private static boolean confirm(String text) {
        // 무인 환경(CI 등): 확인 창 없이 교체
        if ("1".equals(System.getenv("COCKPIT_AUTO_REPLACE"))) {
            return true;
        }
        try {
            return javax.swing.JOptionPane.showConfirmDialog(null, text, "Cockpit 업데이트",
                    javax.swing.JOptionPane.YES_NO_OPTION) == javax.swing.JOptionPane.YES_OPTION;
        } catch (java.awt.HeadlessException | java.awt.AWTError e) {
            return true;   // 대화상자를 띄울 수 없는 환경: 업데이트 진행
        }
    }

    private static void message(String text) {
        try {
            javax.swing.JOptionPane.showMessageDialog(null, text, "Cockpit", javax.swing.JOptionPane.WARNING_MESSAGE);
        } catch (java.awt.HeadlessException | java.awt.AWTError e) {
            System.err.println(text);
        }
    }

    private static HttpURLConnection open(String url, String method) throws IOException {
        HttpURLConnection c = (HttpURLConnection) URI.create(url).toURL().openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(800);
        c.setReadTimeout(1500);
        return c;
    }

    private static String read(HttpURLConnection c) throws IOException {
        try (var in = c.getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
