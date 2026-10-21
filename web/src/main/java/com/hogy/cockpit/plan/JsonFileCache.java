package com.hogy.cockpit.plan;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 배치가 쓰는 JSON 파일을 읽어 객체로 캐시. 파일 수정 시각이 바뀔 때만 다시 읽습니다
 * (배치가 새 파일을 쓰면 재기동 없이 자동 반영).
 */
public final class JsonFileCache<T> {

    private record Entry<T>(FileTime modified, T value) {
    }

    private final ObjectMapper objectMapper;
    private final Class<T> type;
    private final Map<Path, Entry<T>> cache = new ConcurrentHashMap<>();

    public JsonFileCache(ObjectMapper objectMapper, Class<T> type) {
        this.objectMapper = objectMapper;
        this.type = type;
    }

    /** 파일이 없으면 null. 파싱 실패는 IOException 으로 호출부에 전달. */
    public T read(Path file) throws IOException {
        if (!Files.exists(file)) {
            return null;
        }
        FileTime modified = Files.getLastModifiedTime(file);
        Entry<T> cached = cache.get(file);
        if (cached != null && cached.modified().equals(modified)) {
            return cached.value();
        }
        T value = objectMapper.readValue(file.toFile(), type);
        cache.put(file, new Entry<>(modified, value));
        return value;
    }
}
