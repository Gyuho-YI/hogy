package com.hogy.cockpit.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.hogy.cockpit.settings.SettingsService;

/**
 * 자동 스크리닝 예약(한국 시간 기준). 프로그램이 켜져 있을 때만 동작합니다.
 * - 국내: 평일 18:35 (투자자별 수급 확정 이후)
 * - 해외: 화~토 07:10 (미국 장 마감 이후)
 */
@Component
@EnableScheduling
@ConditionalOnProperty(prefix = "app", name = "batch-enabled", havingValue = "true")
public class BatchScheduler {

    private static final Logger log = LoggerFactory.getLogger(BatchScheduler.class);

    private final BatchService batch;
    private final SettingsService settings;

    public BatchScheduler(BatchService batch, SettingsService settings) {
        this.batch = batch;
        this.settings = settings;
    }

    @Scheduled(cron = "${app.cron-kr:0 35 18 * * MON-FRI}", zone = "Asia/Seoul")
    void kr() {
        run("kr");
    }

    @Scheduled(cron = "${app.cron-us:0 10 7 * * TUE-SAT}", zone = "Asia/Seoul")
    void us() {
        run("us");
    }

    private void run(String market) {
        if (!settings.get().isAutoBatch()) {
            return;
        }
        String reject = batch.start(market);
        if (reject != null) {
            log.warn("자동 배치 건너뜀 [{}]: {}", market, reject);
        }
    }
}
