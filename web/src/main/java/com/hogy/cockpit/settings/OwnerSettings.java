package com.hogy.cockpit.settings;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** 1인 전용 설정(단일 행, id = 1). 데스크톱 모드의 비밀번호·계좌 금액·자동 배치 여부. */
@Entity
@Table(name = "owner_settings")
public class OwnerSettings {

    public static final long ID = 1L;

    @Id
    private Long id = ID;

    /** BCrypt 해시(평문 저장 안 함). null 이면 최초 설정 필요. */
    @Column(length = 100)
    private String passwordHash;

    /** 자동 로그인 쿠키 서명 키(설치별 임의값). */
    @Column(length = 64, nullable = false)
    private String rememberKey;

    private Double accountKr;
    private Double accountUs;

    @Column(nullable = false)
    private boolean autoBatch = true;

    /** KRX 정보데이터시스템 회원 ID / 암호화된 비밀번호(국내 시세 조회에 필요, 2025년 말부터 로그인 필수). */
    @Column(length = 60)
    private String krxId;

    @Column(length = 400)
    private String krxPwEnc;

    protected OwnerSettings() {
    }

    public OwnerSettings(String rememberKey) {
        this.rememberKey = rememberKey;
    }

    public Long getId() { return id; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }
    public String getRememberKey() { return rememberKey; }
    public Double getAccountKr() { return accountKr; }
    public void setAccountKr(Double accountKr) { this.accountKr = accountKr; }
    public Double getAccountUs() { return accountUs; }
    public void setAccountUs(Double accountUs) { this.accountUs = accountUs; }
    public boolean isAutoBatch() { return autoBatch; }
    public void setAutoBatch(boolean autoBatch) { this.autoBatch = autoBatch; }
    public String getKrxId() { return krxId; }
    public void setKrxId(String krxId) { this.krxId = krxId; }
    public String getKrxPwEnc() { return krxPwEnc; }
    public void setKrxPwEnc(String krxPwEnc) { this.krxPwEnc = krxPwEnc; }

    public boolean hasKrxAccount() {
        return krxId != null && !krxId.isBlank() && krxPwEnc != null;
    }
}
