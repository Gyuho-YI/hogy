package com.hogy.cockpit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * 개인용 트레이딩 콕핏.
 * <ul>
 *   <li>Python 스크리너가 만든 output/plans_{kr,us}.json 을 읽어 매매 계획 대시보드로 표시</li>
 *   <li>실제 매매를 일지(H2 파일 DB)에 기록 → 실전 승률·손익비·하프켈리를 계산해 스크리너에 다시 공급</li>
 * </ul>
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class CockpitApplication {
    public static void main(String[] args) {
        SpringApplication.run(CockpitApplication.class, args);
    }
}
