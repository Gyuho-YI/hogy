package com.hogy.cockpit.web;

import java.time.LocalDate;

import jakarta.validation.Valid;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.hogy.cockpit.dashboard.KpiService;
import com.hogy.cockpit.journal.JournalService;
import com.hogy.cockpit.journal.Strategy;
import com.hogy.cockpit.journal.TradeForm;
import com.hogy.cockpit.plan.PlanItem;
import com.hogy.cockpit.plan.PlanRepository;
import com.hogy.cockpit.plan.PlanSnapshot;
import com.hogy.cockpit.settings.SettingsService;

/** 화면(Thymeleaf) 컨트롤러: 로그인 / 대시보드 / 매매일지. */
@Controller
public class PageController {

    private final PlanRepository plans;
    private final KpiService kpis;
    private final JournalService journal;
    private final SettingsService settings;

    public PageController(PlanRepository plans, KpiService kpis, JournalService journal, SettingsService settings) {
        this.plans = plans;
        this.kpis = kpis;
        this.journal = journal;
        this.settings = settings;
    }

    @GetMapping("/login")
    public String login() {
        // 데스크톱 최초 실행: 비밀번호가 없으면 설정 화면으로
        return settings.isPasswordReady() ? "login" : "redirect:/setup";
    }

    @GetMapping("/")
    public String home() {
        return "redirect:/dashboard/kr";
    }

    @GetMapping("/dashboard/{market}")
    public String dashboard(@PathVariable String market, Model model) {
        String m = PlanRepository.normalize(market);
        PlanSnapshot snap = plans.load(m);
        model.addAttribute("market", m);
        model.addAttribute("snap", snap);
        model.addAttribute("items", snap.sortedItems());
        model.addAttribute("kpi", kpis.compute(snap, m));
        model.addAttribute("decimals", "us".equals(m) ? 2 : 0);
        return "dashboard";
    }

    /** 매매일지. code 가 있으면 해당 계획 값으로 매수 폼을 미리 채움. */
    @GetMapping("/journal/{market}")
    public String journal(@PathVariable String market, @RequestParam(required = false) String code, Model model) {
        String m = PlanRepository.normalize(market);
        TradeForm form = new TradeForm();
        form.setMarket(m.toUpperCase());
        if (code != null) {
            PlanItem p = plans.load(m).find(code);
            if (p != null) {
                form.setCode(p.code());
                form.setName(p.name());
                form.setStrategy(Strategy.fromStage(p.stage(), m));
                form.setEntryPrice(p.buyHigh());
                form.setQuantity(p.sharesNow() > 0 ? p.sharesNow() : null);
                form.setStopPrice(p.stop());
                form.setTarget1(p.t1());
                form.setTarget2(p.t2());
            }
        }
        fillJournal(m, form, model);
        return "journal";
    }

    @PostMapping("/journal/{market}")
    public String record(@PathVariable String market, @Valid @ModelAttribute("form") TradeForm form,
                         BindingResult binding, Model model) {
        String m = PlanRepository.normalize(market);
        if (binding.hasErrors()) {
            fillJournal(m, form, model);
            return "journal";
        }
        form.setMarket(m.toUpperCase());
        journal.record(form);
        return "redirect:/journal/" + m;
    }

    @PostMapping("/journal/{market}/{id}/close")
    public String close(@PathVariable String market, @PathVariable long id,
                        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate exitDate,
                        @RequestParam double exitPrice) {
        journal.close(id, exitDate, exitPrice);
        return "redirect:/journal/" + PlanRepository.normalize(market);
    }

    @PostMapping("/journal/{market}/{id}/delete")
    public String delete(@PathVariable String market, @PathVariable long id) {
        journal.delete(id);
        return "redirect:/journal/" + PlanRepository.normalize(market);
    }

    /** Python plan_screener.py --stats 입력용 CSV. */
    @GetMapping("/journal/export.csv")
    @ResponseBody
    public ResponseEntity<String> export() {
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=journal_stats.csv")
                .contentType(new MediaType("text", "csv", java.nio.charset.StandardCharsets.UTF_8))
                .body(journal.exportCsv());
    }

    private void fillJournal(String m, TradeForm form, Model model) {
        model.addAttribute("market", m);
        model.addAttribute("form", form);
        model.addAttribute("strategies", Strategy.values());
        model.addAttribute("open", journal.openTrades(m));
        model.addAttribute("closed", journal.closedTrades(m));
        model.addAttribute("stats", journal.stats(m));
        model.addAttribute("monthly", journal.monthly(m));
        model.addAttribute("decimals", "us".equals(m) ? 2 : 0);
        model.addAttribute("today", LocalDate.now());
    }
}
