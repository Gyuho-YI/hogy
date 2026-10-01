package com.hogy.cockpit.journal;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.hogy.cockpit.util.SafeMath;

@Service
@Transactional(readOnly = true)
public class JournalService {

    private final TradeRepository repo;

    public JournalService(TradeRepository repo) {
        this.repo = repo;
    }

    public List<Trade> openTrades(String market) {
        return repo.findByMarketAndExitDateIsNullOrderByEntryDateDesc(market.toUpperCase());
    }

    public List<Trade> closedTrades(String market) {
        return repo.findByMarketAndExitDateIsNotNullOrderByExitDateDesc(market.toUpperCase());
    }

    @Transactional
    public Trade record(TradeForm form) {
        return repo.save(form.toEntity());
    }

    @Transactional
    public void close(long id, LocalDate date, double price) {
        if (price <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "청산가는 0보다 커야 합니다");
        }
        Trade t = repo.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        t.close(date, price);
    }

    @Transactional
    public void delete(long id) {
        repo.deleteById(id);
    }

    public JournalStats stats(String market) {
        return JournalStats.from(closedTrades(market).stream().map(Trade::returnRate).toList());
    }

    /** 보유 중 포지션의 손절 시 손실 합계(포트폴리오 Heat 계산용). */
    public double openRisk(String market) {
        return openTrades(market).stream().mapToDouble(Trade::openRisk).sum();
    }

    /** 보유 중 포지션 매입금액 합계(현금 비중 계산용). */
    public double openExposure(String market) {
        return openTrades(market).stream().mapToDouble(Trade::exposure).sum();
    }

    /** 월별 실현손익(청산월 기준)과 전월 대비 증감률. 손실 월 → 이익 월은 '흑자전환' 라벨. */
    public List<MonthlyPnl> monthly(String market) {
        Map<YearMonth, double[]> agg = new TreeMap<>();
        for (Trade t : closedTrades(market)) {
            double[] a = agg.computeIfAbsent(YearMonth.from(t.getExitDate()), k -> new double[2]);
            a[0] += t.pnl();
            a[1] += 1;
        }
        List<MonthlyPnl> out = new ArrayList<>();
        Double prev = null;
        for (Map.Entry<YearMonth, double[]> e : agg.entrySet()) {
            double pnl = e.getValue()[0];
            SafeMath.Growth g = SafeMath.growth(pnl, prev);
            out.add(new MonthlyPnl(e.getKey().toString(), pnl, (int) e.getValue()[1], g.rate(), g.label()));
            prev = pnl;
        }
        return out;
    }

    /**
     * 실전 거래를 Python 백테스트와 같은 형식(strategy,ret)으로 내보냄.
     * → python plan_screener.py --stats journal.csv 로 실전 승률 기반 켈리 사이징 가능.
     */
    public String exportCsv() {
        StringBuilder sb = new StringBuilder("strategy,ret,market,code,entry_date,exit_date\n");
        for (Trade t : repo.findByExitDateIsNotNullOrderByExitDateAsc()) {
            Double r = t.returnRate();
            if (r == null) {
                continue;
            }
            sb.append(t.getStrategy().label()).append(',').append(String.format("%.6f", r)).append(',')
              .append(t.getMarket()).append(',').append(t.getCode()).append(',')
              .append(t.getEntryDate()).append(',').append(t.getExitDate()).append('\n');
        }
        return sb.toString();
    }
}
