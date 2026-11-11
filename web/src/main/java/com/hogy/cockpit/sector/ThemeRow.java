package com.hogy.cockpit.sector;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 뉴스 헤드라인으로 분류된 테마(국내). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ThemeRow(
        String theme, Integer stocks, Double value,
        @JsonProperty("avg_ratio") Double avgRatio,
        @JsonProperty("avg_change") Double avgChange,
        Double score, List<Member> members) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Member(String code, String name, Double change,
                         @JsonProperty("value_ratio") Double valueRatio, String headline) {
    }
}
