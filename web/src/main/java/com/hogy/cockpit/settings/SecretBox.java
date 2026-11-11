package com.hogy.cockpit.settings;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

import org.springframework.security.crypto.encrypt.Encryptors;
import org.springframework.security.crypto.encrypt.TextEncryptor;
import org.springframework.security.crypto.keygen.KeyGenerators;
import org.springframework.stereotype.Component;

import com.hogy.cockpit.config.AppProperties;

/**
 * 외부 서비스 비밀번호(KRX 등)를 되돌릴 수 있게 암호화 저장(AES-256-GCM).
 * - 로그인 비밀번호와 달리 KRX 에 실제로 전달해야 하므로 해시가 아닌 암호화를 사용
 * - 키는 설치별 임의값으로 DB 와 분리된 파일(data/secret.key)에 보관 → DB 파일만 유출돼도 복호화 불가
 */
@Component
public class SecretBox {

    private final Path keyFile;
    private volatile TextEncryptor encryptor;

    public SecretBox(AppProperties props) {
        this.keyFile = Path.of(props.dataDir()).toAbsolutePath().normalize().resolveSibling("data").resolve("secret.key");
    }

    public String encrypt(String plain) {
        return encryptor().encrypt(plain);
    }

    public String decrypt(String cipher) {
        return encryptor().decrypt(cipher);
    }

    private TextEncryptor encryptor() {
        if (encryptor == null) {
            synchronized (this) {
                if (encryptor == null) {
                    String[] parts = loadOrCreateKey().split(":");
                    encryptor = Encryptors.delux(parts[0], parts[1]);
                }
            }
        }
        return encryptor;
    }

    /** "비밀번호(hex):솔트(hex)" 형식. 없으면 생성하고 가능하면 소유자 전용 권한 부여. */
    private String loadOrCreateKey() {
        try {
            if (Files.exists(keyFile)) {
                return Files.readString(keyFile, StandardCharsets.UTF_8).trim();
            }
            Files.createDirectories(keyFile.getParent());
            String key = KeyGenerators.string().generateKey() + KeyGenerators.string().generateKey()
                    + ":" + KeyGenerators.string().generateKey();
            Files.writeString(keyFile, key, StandardCharsets.UTF_8);
            try {
                Files.setPosixFilePermissions(keyFile, PosixFilePermissions.fromString("rw-------"));
            } catch (UnsupportedOperationException | IOException ignored) {
                // Windows: 사용자 폴더 기본 권한(본인 전용)에 의존
            }
            return key;
        } catch (IOException e) {
            throw new UncheckedIOException("암호화 키 파일 처리 실패: " + keyFile, e);
        }
    }
}
