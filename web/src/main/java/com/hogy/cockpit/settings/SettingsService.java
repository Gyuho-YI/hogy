package com.hogy.cockpit.settings;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.hogy.cockpit.config.AppProperties;

/** 단일 행 설정 관리. 행이 없으면 첫 조회 시 생성합니다. */
@Service
public class SettingsService {

    public static final int MIN_PASSWORD = 8;

    private final OwnerSettingsRepository repo;
    private final PasswordEncoder encoder;
    private final AppProperties props;

    public SettingsService(OwnerSettingsRepository repo, PasswordEncoder encoder, AppProperties props) {
        this.repo = repo;
        this.encoder = encoder;
        this.props = props;
    }

    @Transactional
    public OwnerSettings get() {
        return repo.findById(OwnerSettings.ID)
                .orElseGet(() -> repo.save(new OwnerSettings(UUID.randomUUID().toString())));
    }

    /** 로그인 가능한 비밀번호가 있는가(환경변수 또는 DB). */
    public boolean isPasswordReady() {
        return props.hasEnvPassword() || get().getPasswordHash() != null;
    }

    /** 최초 1회 비밀번호 설정. 이미 설정돼 있으면 거부(덮어쓰기 공격 방지). */
    @Transactional
    public void setupPassword(String raw, String confirm) {
        if (isPasswordReady()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 비밀번호가 설정되어 있습니다");
        }
        validate(raw, confirm);
        get().setPasswordHash(encoder.encode(raw));
    }

    /** 로그인 상태에서 비밀번호 변경(현재 비밀번호 확인). 환경변수 모드에서는 불가. */
    @Transactional
    public void changePassword(String current, String raw, String confirm) {
        OwnerSettings s = get();
        if (props.hasEnvPassword() || s.getPasswordHash() == null || !encoder.matches(current, s.getPasswordHash())) {
            throw new IllegalArgumentException("현재 비밀번호가 올바르지 않습니다");
        }
        validate(raw, confirm);
        s.setPasswordHash(encoder.encode(raw));
    }

    @Transactional
    public void updateTrading(Double accountKr, Double accountUs, boolean autoBatch) {
        OwnerSettings s = get();
        s.setAccountKr(positiveOrNull(accountKr));
        s.setAccountUs(positiveOrNull(accountUs));
        s.setAutoBatch(autoBatch);
    }

    /** 자동 로그인 키: 환경변수 값이 있으면 우선, 없으면 설치별 임의 키. */
    public String rememberKey() {
        String k = props.rememberMeKey();
        return (k == null || k.isBlank()) ? get().getRememberKey() : k;
    }

    private static void validate(String raw, String confirm) {
        if (raw == null || raw.length() < MIN_PASSWORD) {
            throw new IllegalArgumentException("비밀번호는 " + MIN_PASSWORD + "자 이상이어야 합니다");
        }
        if (!raw.equals(confirm)) {
            throw new IllegalArgumentException("비밀번호 확인이 일치하지 않습니다");
        }
    }

    private static Double positiveOrNull(Double v) {
        return (v == null || v <= 0 || v.isNaN()) ? null : v;
    }
}
