/* 섹터 레이더: 쏠림 배수 상위 10 가로 막대 (단일 시리즈, 값 라벨 + 1.0 기준선은 축 그리드로 표현) */
(function () {
  const C = window.Cockpit;
  fetch(`/api/sectors/${C.market}`, { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null))
    .then((snap) => {
      const el = document.getElementById('ratioChart');
      const rows = ((snap && snap.sectors) || []).filter((s) => s.ratio != null)
        .sort((a, b) => b.ratio - a.ratio).slice(0, 10);
      if (!rows.length) {
        el.parentElement.replaceChildren(Object.assign(document.createElement('p'),
          { className: 'muted', textContent: '표시할 데이터가 없습니다.' }));
        return;
      }
      const opts = C.baseOptions();
      opts.indexAxis = 'y';
      opts.plugins.legend.display = false;          // 단일 시리즈: 제목이 시리즈명
      opts.plugins.tooltip.callbacks = {
        label: (ctx) => {
          const s = rows[ctx.dataIndex];
          const ch = s.change == null ? '' : ` · 등락 ${s.change >= 0 ? '+' : ''}${s.change.toFixed(2)}%`;
          return ` 쏠림 ${s.ratio.toFixed(2)}배 · ${s.flag}${ch}`;
        },
      };
      opts.scales = {
        x: { ...C.axis(), beginAtZero: true, suggestedMax: 2,
             ticks: { ...C.axis().ticks, callback: (v) => `${v}배` } },
        y: { ...C.axis(), grid: { display: false } },
      };
      new Chart(el, {
        type: 'bar',
        data: {
          labels: rows.map((s) => s.sector),
          datasets: [{
            label: '쏠림 배수', data: rows.map((s) => s.ratio),
            backgroundColor: C.css('--series-1'), borderRadius: 4, borderSkipped: 'start',
            maxBarThickness: 18,
          }],
        },
        options: opts,
      });
    });
})();
