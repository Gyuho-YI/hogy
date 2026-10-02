package com.hogy.cockpit.web;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import com.hogy.cockpit.batch.BatchService;
import com.hogy.cockpit.batch.BatchStatus;
import com.hogy.cockpit.config.AppProperties;
import com.hogy.cockpit.plan.PlanRepository;
import com.hogy.cockpit.settings.SettingsService;

/** 최초 비밀번호 설정 / 설정 화면 / 배치 실행 / 프로그램 종료. */
@Controller
public class SettingsController {

    private final SettingsService settings;
    private final BatchService batch;
    private final AppProperties props;
    private final ApplicationContext context;

    public SettingsController(SettingsService settings, BatchService batch, AppProperties props,
                              ApplicationContext context) {
        this.settings = settings;
        this.batch = batch;
        this.props = props;
        this.context = context;
    }

    // ---- 최초 실행: 비밀번호 설정 ----
    @GetMapping("/setup")
    public String setupForm() {
        return settings.isPasswordReady() ? "redirect:/login" : "setup";
    }

    @PostMapping("/setup")
    public String setup(@RequestParam String password, @RequestParam String confirm, Model model) {
        if (settings.isPasswordReady()) {
            return "redirect:/login";
        }
        try {
            settings.setupPassword(password, confirm);
        } catch (IllegalArgumentException e) {
            model.addAttribute("error", e.getMessage());
            return "setup";
        }
        return "redirect:/login?setup";
    }

    // ---- 설정 화면 ----
    @GetMapping("/settings")
    public String page(Model model) {
        model.addAttribute("s", settings.get());
        model.addAttribute("batches", java.util.List.of(batch.status("kr"), batch.status("us")));
        model.addAttribute("batchEnabled", props.batchEnabled());
        model.addAttribute("desktop", props.desktop());
        model.addAttribute("envPassword", props.hasEnvPassword());
        model.addAttribute("username", props.username());
        return "settings";
    }

    @PostMapping("/settings/trading")
    public String trading(@RequestParam(required = false) Double accountKr,
                          @RequestParam(required = false) Double accountUs,
                          @RequestParam(defaultValue = "false") boolean autoBatch, RedirectAttributes ra) {
        settings.updateTrading(accountKr, accountUs, autoBatch);
        ra.addFlashAttribute("ok", "저장했습니다");
        return "redirect:/settings";
    }

    @PostMapping("/settings/password")
    public String password(@RequestParam String current, @RequestParam String password,
                           @RequestParam String confirm, RedirectAttributes ra) {
        try {
            settings.changePassword(current, password, confirm);
            ra.addFlashAttribute("ok", "비밀번호를 변경했습니다");
        } catch (IllegalArgumentException e) {
            ra.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/settings";
    }

    @PostMapping("/settings/batch/{market}")
    public String run(@PathVariable String market, RedirectAttributes ra) {
        String reject = batch.start(market);
        if (reject != null) {
            ra.addFlashAttribute("error", reject);
        } else {
            ra.addFlashAttribute("ok", ("kr".equals(market) ? "국내" : "해외") + " 스크리닝을 시작했습니다(수 분 소요)");
        }
        return "redirect:/settings";
    }

    /** 실행 상태 폴링(설정 화면이 3초마다 호출). */
    @GetMapping("/api/batch/{market}")
    @ResponseBody
    public BatchStatus status(@PathVariable String market) {
        return batch.status(PlanRepository.normalize(market));
    }

    /** 데스크톱 모드 전용: 프로그램 종료. 응답을 먼저 보낸 뒤 0.5초 후 종료. */
    @PostMapping("/settings/shutdown")
    @ResponseBody
    public ResponseEntity<Map<String, String>> shutdown() {
        if (!props.desktop()) {
            return ResponseEntity.badRequest().body(Map.of("message", "서버 모드에서는 종료할 수 없습니다"));
        }
        Thread t = new Thread(() -> {
            try {
                Thread.sleep(500);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            System.exit(SpringApplication.exit(context, () -> 0));
        }, "cockpit-shutdown");
        t.setDaemon(false);
        t.start();
        return ResponseEntity.ok(Map.of("message", "프로그램을 종료합니다. 이 창을 닫아도 됩니다."));
    }
}
