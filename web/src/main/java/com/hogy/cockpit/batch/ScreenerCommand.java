package com.hogy.cockpit.batch;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * 스크리너 실행 명령 탐색.
 * <ol>
 *   <li>설정값 app.screener-command (쉼표 구분)</li>
 *   <li>패키지 설치본: 프로그램 폴더/screener/screener.exe (Windows 배포 ZIP)</li>
 *   <li>개발 환경: 저장소의 .venv 파이썬 + screener/cli.py</li>
 * </ol>
 */
final class ScreenerCommand {

    private ScreenerCommand() {
    }

    static List<String> resolve(String configured) {
        if (configured != null && !configured.isBlank()) {
            return Arrays.stream(configured.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList();
        }
        Path home = appHome();
        for (String exe : List.of("screener/screener.exe", "screener/screener")) {
            Path p = home.resolve(exe);
            if (Files.isRegularFile(p) && !p.toString().endsWith("cli.py")) {
                return List.of(p.toString());
            }
        }
        // 개발 환경: web/ 에서 실행했다면 저장소 루트는 상위 폴더
        Path repo = Files.isDirectory(home.resolve("screener")) ? home : home.getParent();
        Path cli = repo.resolve("screener").resolve("cli.py");
        List<String> cmd = new ArrayList<>();
        cmd.add(python(repo));
        cmd.add(cli.toString());
        return cmd;
    }

    /** jpackage 런처는 jpackage.app-path 에 exe 경로를 넣어줌 → 그 폴더가 프로그램 폴더. */
    static Path appHome() {
        String launcher = System.getProperty("jpackage.app-path");
        if (launcher != null && !launcher.isBlank()) {
            return Path.of(launcher).toAbsolutePath().getParent();
        }
        return Path.of("").toAbsolutePath();
    }

    private static String python(Path repo) {
        for (String p : List.of(".venv/Scripts/python.exe", ".venv/bin/python")) {
            if (Files.isRegularFile(repo.resolve(p))) {
                return repo.resolve(p).toString();
            }
        }
        return System.getProperty("os.name", "").toLowerCase().contains("win") ? "python" : "python3";
    }
}
