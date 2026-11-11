/* 매매일지: 월별 실현손익 막대(이익 적색 · 손실 청색, 한국식) */
(function () {
  const C = window.Cockpit;
  const el = document.getElementById('monthly-chart');
  C.getJson(`/api/journal/${C.market}/monthly`).then((rows) => {
    if (!rows || !rows.length) {
      el.replaceChildren(C.h('p', { class: 'empty', text: '청산 기록이 쌓이면 표시됩니다' }));
      return;
    }
    C.chart(el, 'line', {
      data: rows.map((r) => ({ month: r.month, 손익: r.pnl })),
      x: 'month', y: ['손익'], height: 220, signColors: true, baseline: 0,
      downColor: '#2563EB', theme: { accent: '#E5323F' }, area: true, dots: true, curve: 'linear', endLabels: false,
      format: { maximumFractionDigits: C.decimals, notation: 'compact' },
    });
  });
})();
