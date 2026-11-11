package com.hogy.cockpit.journal;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TradeRepository extends JpaRepository<Trade, Long> {

    List<Trade> findByMarketAndExitDateIsNullOrderByEntryDateDesc(String market);

    List<Trade> findByMarketAndExitDateIsNotNullOrderByExitDateDesc(String market);

    List<Trade> findByExitDateIsNotNullOrderByExitDateAsc();
}
