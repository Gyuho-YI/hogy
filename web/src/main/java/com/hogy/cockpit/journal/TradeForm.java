package com.hogy.cockpit.journal;

import java.time.LocalDate;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.format.annotation.DateTimeFormat;

/** 매수 기록 입력 폼. 대시보드의 '일지에 기록' 버튼이 계획값으로 미리 채웁니다. */
public class TradeForm {

    @NotBlank
    private String market = "KR";
    @NotBlank
    private String code;
    private String name;
    @NotNull
    private Strategy strategy = Strategy.IGNITION;
    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate entryDate = LocalDate.now();
    @NotNull
    @Positive
    private Double entryPrice;
    @NotNull
    @Positive
    private Integer quantity;
    private Double stopPrice;
    private Double target1;
    private Double target2;
    private String memo;

    public Trade toEntity() {
        return new Trade(market.toUpperCase(), code.trim(), name, strategy, entryDate,
                entryPrice, quantity, stopPrice, target1, target2, memo);
    }

    public String getMarket() { return market; }
    public void setMarket(String market) { this.market = market; }
    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Strategy getStrategy() { return strategy; }
    public void setStrategy(Strategy strategy) { this.strategy = strategy; }
    public LocalDate getEntryDate() { return entryDate; }
    public void setEntryDate(LocalDate entryDate) { this.entryDate = entryDate; }
    public Double getEntryPrice() { return entryPrice; }
    public void setEntryPrice(Double entryPrice) { this.entryPrice = entryPrice; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public Double getStopPrice() { return stopPrice; }
    public void setStopPrice(Double stopPrice) { this.stopPrice = stopPrice; }
    public Double getTarget1() { return target1; }
    public void setTarget1(Double target1) { this.target1 = target1; }
    public Double getTarget2() { return target2; }
    public void setTarget2(Double target2) { this.target2 = target2; }
    public String getMemo() { return memo; }
    public void setMemo(String memo) { this.memo = memo; }
}
