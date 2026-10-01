package com.hogy.cockpit.journal;

import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** 매매일지 1건. exitDate 가 null 이면 보유 중. */
@Entity
@Table(name = "trade")
public class Trade {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 2)
    private String market;          // KR / US

    @Column(nullable = false, length = 20)
    private String code;

    @Column(length = 60)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Strategy strategy;

    @Column(nullable = false)
    private LocalDate entryDate;

    @Column(nullable = false)
    private double entryPrice;

    @Column(nullable = false)
    private int quantity;

    private Double stopPrice;
    private Double target1;
    private Double target2;

    private LocalDate exitDate;
    private Double exitPrice;

    @Column(length = 500)
    private String memo;

    protected Trade() {
    }

    public Trade(String market, String code, String name, Strategy strategy, LocalDate entryDate,
                 double entryPrice, int quantity, Double stopPrice, Double target1, Double target2, String memo) {
        this.market = market;
        this.code = code;
        this.name = name;
        this.strategy = strategy;
        this.entryDate = entryDate;
        this.entryPrice = entryPrice;
        this.quantity = quantity;
        this.stopPrice = stopPrice;
        this.target1 = target1;
        this.target2 = target2;
        this.memo = memo;
    }

    /** 청산 기록. */
    public void close(LocalDate date, double price) {
        this.exitDate = date;
        this.exitPrice = price;
    }

    public boolean isOpen() {
        return exitDate == null;
    }

    /** 수익률. 진입가 0 이하(입력 오류)거나 미청산이면 null. */
    public Double returnRate() {
        if (exitPrice == null || entryPrice <= 0) {
            return null;
        }
        return exitPrice / entryPrice - 1;
    }

    /** 실현 손익(현지 통화). */
    public Double pnl() {
        return exitPrice == null ? null : (exitPrice - entryPrice) * quantity;
    }

    /** 손절 시 손실 금액(보유 중 리스크). 손절가가 없거나 진입가 이상이면 0. */
    public double openRisk() {
        if (stopPrice == null || stopPrice >= entryPrice) {
            return 0.0;
        }
        return (entryPrice - stopPrice) * quantity;
    }

    public double exposure() {
        return entryPrice * quantity;
    }

    public Long getId() { return id; }
    public String getMarket() { return market; }
    public String getCode() { return code; }
    public String getName() { return name; }
    public Strategy getStrategy() { return strategy; }
    public LocalDate getEntryDate() { return entryDate; }
    public double getEntryPrice() { return entryPrice; }
    public int getQuantity() { return quantity; }
    public Double getStopPrice() { return stopPrice; }
    public Double getTarget1() { return target1; }
    public Double getTarget2() { return target2; }
    public LocalDate getExitDate() { return exitDate; }
    public Double getExitPrice() { return exitPrice; }
    public String getMemo() { return memo; }
}
