/* 대시보드: 종목 상세 차트(가격 + 매수구간/손절/목표선) + 손절폭 대비 손익비 산점도 */
(function () {
  const C = window.Cockpit;
  let detailChart = null;
  let items = [];

  /** 수평 기준선 데이터셋(이력 길이만큼 같은 값). */
  const level = (label, value, color, dash, n, extra = {}) => ({
    label, data: Array(n).fill(value), borderColor: color, backgroundColor: color,
    borderWidth: 1.5, borderDash: dash, pointRadius: 0, pointHoverRadius: 0, ...extra,
  });

  function renderDetail(it) {
    document.querySelectorAll('.plan-row').forEach((r) => r.classList.toggle('selected', r.dataset.code === it.code));
    document.getElementById('detail-title').textContent = `${it.name} (${it.code}) · ${it.action}`;
    const notes = document.getElementById('detail-notes');
    notes.replaceChildren(...(it.notes || []).map((t) => Object.assign(document.createElement('li'), { textContent: t })));

    const hist = it.history || [];
    const n = hist.length;
    const band = C.css('--series-3');
    const datasets = [
      { label: '종가', data: hist.map((p) => p.c), borderColor: C.css('--series-1'), borderWidth: 2,
        pointRadius: 0, pointHoverRadius: 4, tension: 0 },
    ];
    if (it.buyLow != null && it.buyHigh != null) {
      datasets.push(level('매수 하단', it.buyLow, band, [], n));
      // 매수 상단: 하단까지 반투명 채움 → '매수 구간' 밴드
      datasets.push(level('매수 상단', it.buyHigh, band, [], n,
        { fill: '-1', backgroundColor: band + '26' }));
    }
    if (it.stop != null) datasets.push(level('손절', it.stop, C.css('--critical'), [6, 4], n));
    if (it.t1 != null) datasets.push(level('1차 익절', it.t1, C.css('--good'), [2, 3], n));
    if (it.t2 != null) datasets.push(level('2차 익절', it.t2, C.css('--good'), [8, 4], n));

    const opts = C.baseOptions();
    opts.interaction = { mode: 'index', intersect: false };   // 크로스헤어형 툴팁
    opts.plugins.tooltip.callbacks = { label: (ctx) => ` ${ctx.dataset.label}: ${C.fmt(ctx.parsed.y)}` };
    opts.scales = {
      x: { ...C.axis(), ticks: { ...C.axis().ticks, maxTicksLimit: 6, maxRotation: 0 } },
      y: { ...C.axis(), position: 'right', ticks: { ...C.axis().ticks, callback: (v) => C.fmt(v) } },
    };
    if (detailChart) detailChart.destroy();
    detailChart = new Chart(document.getElementById('detailChart'),
      { type: 'line', data: { labels: hist.map((p) => p.d.slice(5)), datasets }, options: opts });
  }

  function renderScatter() {
    // 판단(실행 상태)별 시리즈: 최대 3개 → 산점도에서 색 구분이 검증된 슬롯 1~3만 사용
    const groups = [
      { action: '지금 매수 가능', label: '매수 가능', color: C.css('--series-1'), shape: 'circle' },
      { action: '돌파 대기(Buy Stop)', label: '돌파 대기', color: C.css('--series-3'), shape: 'rectRot' },
      { action: '지정가 대기', label: '지정가 대기', color: C.css('--series-2'), shape: 'triangle' },
    ];
    const datasets = groups.map((g) => ({
      label: g.label,
      data: items.filter((i) => i.action === g.action && i.riskPct != null && i.rewardRisk != null)
                 .map((i) => ({ x: i.riskPct * 100, y: i.rewardRisk, name: i.name })),
      backgroundColor: g.color, borderColor: C.css('--surface'), borderWidth: 2,
      pointStyle: g.shape, pointRadius: 6, pointHoverRadius: 8, pointHitRadius: 12,
    })).filter((d) => d.data.length);

    const opts = C.baseOptions();
    opts.plugins.legend.labels = { ...opts.plugins.legend.labels, usePointStyle: true, boxWidth: 8, boxHeight: 8 };
    opts.plugins.tooltip.callbacks = {
      label: (ctx) => ` ${ctx.raw.name}: 손절 -${ctx.raw.x.toFixed(1)}% · 손익비 ${ctx.raw.y.toFixed(1)}`,
    };
    opts.scales = {
      x: { ...C.axis(), title: { display: true, text: '손절폭 (%)', color: C.css('--muted') }, beginAtZero: true, grace: '10%' },
      y: { ...C.axis(), title: { display: true, text: '손익비', color: C.css('--muted') }, beginAtZero: true, grace: '10%' },
    };
    new Chart(document.getElementById('rrChart'), { type: 'scatter', data: { datasets }, options: opts });
  }

  async function init() {
    const res = await fetch(`/api/plans/${C.market}`, { headers: { Accept: 'application/json' } });
    if (!res.ok) return;
    const snap = await res.json();
    items = snap.items || [];
    if (!items.length) return;

    document.querySelectorAll('.plan-row').forEach((row) => {
      const pick = () => renderDetail(items.find((i) => i.code === row.dataset.code));
      row.addEventListener('click', (e) => { if (!e.target.closest('a')) pick(); });
      row.addEventListener('keydown', (e) => { if (e.key === 'Enter') pick(); });
    });
    const first = document.querySelector('.plan-row');
    renderDetail(items.find((i) => i.code === first.dataset.code));
    renderScatter();
  }
  init();
})();
