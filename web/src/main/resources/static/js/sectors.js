/* 섹터 레이더: 쏠림 배수 상위 10 (1.0배 = 평소) */
(function () {
  const C = window.Cockpit;
  const el = document.getElementById('ratio-chart');
  C.getJson(`/api/sectors/${C.market}`).then((snap) => {
    const rows = ((snap && snap.sectors) || []).filter((s) => C.ok(s.ratio))
      .sort((a, b) => b.ratio - a.ratio).slice(0, 10);
    if (!rows.length) {
      el.replaceChildren(C.h('p', { class: 'empty', text: '표시할 데이터 없음' }));
      return;
    }
    C.chart(el, 'bar', {
      data: rows.map((s) => ({ x: s.sector, y: Math.round(s.ratio * 100) / 100 })),
      x: 'x', y: 'y', orientation: 'horizontal', unit: '배', format: { maximumFractionDigits: 2 },
      height: rows.length * 32 + 40, highlight: 'max',
    });
  });
})();
