/* 매매일지: 월별 실현손익 막대 (이익 = good, 손실 = critical, ▲▼ 라벨은 표에서 병기) */
(function () {
  const C = window.Cockpit;
  fetch(`/api/journal/${C.market}/monthly`, { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : []))
    .then((rows) => {
      const el = document.getElementById('monthlyChart');
      if (!rows.length) {
        el.parentElement.replaceChildren(Object.assign(document.createElement('p'),
          { className: 'muted', textContent: '청산 기록이 쌓이면 월별 손익이 표시됩니다.' }));
        return;
      }
      const opts = C.baseOptions();
      opts.plugins.legend.display = false;   // 단일 시리즈: 제목이 시리즈명을 대신함
      opts.plugins.tooltip.callbacks = {
        label: (ctx) => {
          const r = rows[ctx.dataIndex];
          const mom = r.momRate == null ? r.momLabel : `${(r.momRate * 100).toFixed(1)}% · ${r.momLabel}`;
          return ` 손익 ${C.fmt(r.pnl)} · ${r.trades}건 · 전월 대비 ${mom}`;
        },
      };
      opts.scales = {
        x: { ...C.axis(), grid: { display: false } },
        y: { ...C.axis(), ticks: { ...C.axis().ticks, callback: (v) => C.fmt(v) } },
      };
      new Chart(el, {
        type: 'bar',
        data: {
          labels: rows.map((r) => r.month),
          datasets: [{
            label: '실현손익', data: rows.map((r) => r.pnl),
            backgroundColor: rows.map((r) => (r.pnl >= 0 ? C.css('--good') : C.css('--critical'))),
            borderRadius: 4, borderSkipped: 'start', maxBarThickness: 36,
          }],
        },
        options: opts,
      });
    });
})();
