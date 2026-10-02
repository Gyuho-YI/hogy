package com.hogy.cockpit.batch;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 배치 실행 상태(화면 표시용 스냅샷).
 *
 * @param exitCode null = 실행 중이거나 실행 이력 없음, 0 = 성공
 */
public record BatchStatus(String market, boolean running, LocalDateTime startedAt, LocalDateTime finishedAt,
                          Integer exitCode, String message, List<String> tail) {

    public static BatchStatus idle(String market) {
        return new BatchStatus(market, false, null, null, null, "실행 이력 없음", List.of());
    }

    public boolean success() {
        return exitCode != null && exitCode == 0;
    }

    /** 실행 로그(줄바꿈 연결). */
    public String logText() {
        return tail == null ? "" : String.join("\n", tail);
    }

    /** 화면 표시: 아이콘 + 라벨(색만으로 상태를 전달하지 않음). */
    public String label() {
        if (running) {
            return "⏳ 실행 중…";
        }
        if (finishedAt == null) {
            return "– " + message;
        }
        return (success() ? "✓ " : "⛔ ") + message;
    }
}
