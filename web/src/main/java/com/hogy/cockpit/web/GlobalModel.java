package com.hogy.cockpit.web;

import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ModelAttribute;

import com.hogy.cockpit.config.AppVersion;

/** 모든 화면 공통 값: 실행 중 버전(내비게이션에 표시 → 업데이트 반영 여부 확인용). */
@ControllerAdvice
public class GlobalModel {

    @ModelAttribute("appVersion")
    public String appVersion() {
        return AppVersion.current();
    }
}
