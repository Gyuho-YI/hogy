package com.hogy.cockpit.web;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.hogy.cockpit.journal.JournalService;
import com.hogy.cockpit.journal.MonthlyPnl;
import com.hogy.cockpit.plan.PlanRepository;
import com.hogy.cockpit.plan.PlanSnapshot;
import com.hogy.cockpit.sector.SectorService;
import com.hogy.cockpit.sector.SectorSnapshot;

/** Chart.js 가 호출하는 JSON API (로그인 세션 필요). */
@RestController
@RequestMapping("/api")
public class ApiController {

    private final PlanRepository plans;
    private final JournalService journal;
    private final SectorService sectors;

    public ApiController(PlanRepository plans, JournalService journal, SectorService sectors) {
        this.plans = plans;
        this.journal = journal;
        this.sectors = sectors;
    }

    @GetMapping("/sectors/{market}")
    public SectorSnapshot sectors(@PathVariable String market) {
        return sectors.load(market);
    }

    @GetMapping("/plans/{market}")
    public PlanSnapshot plans(@PathVariable String market) {
        return plans.load(market);
    }

    @GetMapping("/journal/{market}/monthly")
    public List<MonthlyPnl> monthly(@PathVariable String market) {
        return journal.monthly(PlanRepository.normalize(market));
    }
}
