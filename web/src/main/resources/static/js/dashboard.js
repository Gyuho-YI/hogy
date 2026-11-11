/*
 * 매매 계획 화면
 * - 계획표 행 선택 → 우측 상세(가격 수준 · 캔들 + 매수구간/손절/목표 · 시뮬레이션 · 펀더멘털 · 판단 근거)
 * - 하단: 손절폭 × 손익비 산점도, 후보별 시뮬레이션 기대 R
 * 차트: ztd-charts (common.js → Cockpit.chart)
 */
(function () {
  const C = window.Cockpit;
  const { h } = C;
  const US = C.market === 'us';
  let items = [];
  let selected = null;

  const BLOCK_LABEL = { rr_resistance: '매물 저항', earnings: '실적 발표', gate: '리스크 한도', sim: '기대값 음수' };
  const ACTION = {
    '지금 매수 가능': ['buy', '매수 가능'],
    '돌파 대기(Buy Stop)': ['stop-order', '돌파 대기'],
    '지정가 대기': ['limit', '지정가 대기'],
  };
  const actionable = (it) => it.action !== '관망' && it.sharesNow > 0;
  function actionOf(it) {
    if (ACTION[it.action]) return ACTION[it.action];
    if ((it.stage || '').startsWith('관찰')) return ['watch', '관찰'];
    return (it.blocks || []).length ? ['held', '보류'] : ['hold', '관망'];
  }
  const pctFrom = (v, base) => (C.ok(v) && C.ok(base) && base ? (v / base - 1) * 100 : null);
  const signed = (v, d = 1) => (C.ok(v) ? `${v >= 0 ? '+' : '−'}${C.num(Math.abs(v), d)}%` : '');

  /* ── 상세: 머리 ─────────────────────────────────────────── */
  function head(it) {
    const hist = it.history || [];
    const last = hist.length ? hist[hist.length - 1].c : it.close;
    const prev = hist.length > 1 ? hist[hist.length - 2].c : null;
    const chg = pctFrom(last, prev);
    const [key, label] = actionOf(it);
    const meta = [it.code, it.stage, it.sector].filter(Boolean).join(' · ');
    const tags = [h('span', { class: `st ${key}`, text: label })];
    (it.blocks || []).forEach((b) => tags.push(' ', h('span', { class: 'tag neg', text: BLOCK_LABEL[b] || b })));
    if (it.earningsDate) {
      const near = C.ok(it.earningsDays) && it.earningsDays <= 10;
      tags.push(' ', h('span', { class: `tag ${near ? 'warn' : ''}`, text: `실적 ${it.earningsDate.slice(5).replace('-', '/')}${C.ok(it.earningsDays) ? ` · D-${it.earningsDays}` : ''}` }));
    } else if (it.earningsSeason) {
      tags.push(' ', h('span', { class: 'tag warn', text: '실적 시즌' }));
    }
    if (C.ok(it.score)) tags.push(' ', h('span', { class: 'tag', text: US ? `RS ${C.num(it.score)}` : `매집 ${C.num(it.score)}점` }));
    return h('div', { class: 'dt-h' },
      h('div', { class: 'dt-top' },
        h('div', {}, h('h2', { class: 'dt-name', text: it.name }), h('p', { class: 'dt-code', text: meta })),
        h('div', { class: 'dt-px' }, h('b', { text: C.px(last) }),
          h('span', { class: chg == null ? '' : chg >= 0 ? 'up' : 'down', text: chg == null ? '' : `${signed(chg, 2)} 전일 대비` }))),
      h('div', { class: 'dt-tags' }, tags,
        actionable(it) ? h('a', { class: 'btn sm pri dt-rec', href: `/journal/${C.market}?code=${encodeURIComponent(it.code)}`, text: '일지에 기록' }) : null));
  }

  /* ── 상세: 가격 수준 4칸 ────────────────────────────────── */
  function levels(it) {
    const cell = (k, v, sub, cls = '') => h('div', { class: `lv ${cls}` }, h('span', { text: k }), h('b', { text: v }), h('i', { text: sub || '' }));
    if (it.watchBreakout != null && !actionable(it) && it.buyLow == null) {
      return h('div', { class: 'levels' },
        cell('돌파 감시', C.px(it.watchBreakout), signed(pctFrom(it.watchBreakout, it.close))),
        cell('50일선 이탈', C.px(it.watchExit), signed(pctFrom(it.watchExit, it.close)), 'stop'),
        cell('현재가', C.px(it.close), it.stage),
        cell('수량', '–', '매수 구간 아님'));
    }
    return h('div', { class: 'levels' },
      cell('매수 구간', it.buyLow != null ? `${C.px(it.buyLow)}–${C.px(it.buyHigh)}` : '–',
        it.sharesNow > 0 ? `${C.num(it.sharesNow)}주 · 비중 ${C.num(it.weightPct, 1)}%` : '이번 수량 없음', 'zone'),
      cell('손절', C.px(it.stop), C.ok(it.riskPct) ? `−${C.num(it.riskPct * 100, 1)}%` : '', 'stop'),
      cell('목표 1', C.px(it.t1), it.t1 && it.buyHigh ? `${signed(pctFrom(it.t1, it.buyHigh))} · 1/3` : '', 'tgt'),
      cell('목표 2', C.px(it.t2), it.rewardRisk != null ? `${C.num(it.rewardRisk, 1)}R · 1/3` : '', 'tgt'));
  }

  /* ── 상세: 가격 차트 ────────────────────────────────────── */
  function priceChart(it, el) {
    const hist = (it.history || []).filter((p) => C.ok(p.c));
    const ohlc = hist.length && hist.every((p) => C.ok(p.o) && C.ok(p.h) && C.ok(p.l));
    const ann = [];
    if (C.ok(it.buyLow) && C.ok(it.buyHigh)) ann.push({ type: 'band', y: [it.buyLow, it.buyHigh], label: '매수' });
    if (C.ok(it.stop)) ann.push({ type: 'line', y: it.stop, label: '손절' });
    if (C.ok(it.t1)) ann.push({ type: 'line', y: it.t1, label: '목표 1' });
    if (C.ok(it.t2)) ann.push({ type: 'line', y: it.t2, label: '목표 2' });
    if (C.ok(it.watchBreakout) && !C.ok(it.buyLow)) ann.push({ type: 'line', y: it.watchBreakout, label: '돌파 감시' });
    if (C.ok(it.watchExit) && !C.ok(it.buyLow)) ann.push({ type: 'line', y: it.watchExit, label: '50일선' });
    const common = { data: hist, x: 'd', height: 300, animateOnView: false, annotations: ann, format: { maximumFractionDigits: C.decimals },
      ariaLabel: `${it.name} 최근 ${hist.length}일 가격과 매매 기준선` };
    if (ohlc) {
      C.chart(el, 'candlestick', { ...common, open: 'o', high: 'h', low: 'l', close: 'c',
        volume: hist.every((p) => C.ok(p.v)) ? 'v' : undefined, ma: [20, 50],
        upColor: '#E5323F', downColor: '#2563EB' });
    } else {
      C.chart(el, 'line', { ...common, y: 'c', showLabels: false });
    }
  }

  /* ── 상세: 시뮬레이션 ───────────────────────────────────── */
  function simSection(it) {
    const s = it.sim;
    if (!s || !C.ok(s.pTarget)) return null;
    const trio = h('div', { class: 'trio' },
      h('div', {}, h('span', { text: '목표 선도달' }), h('b', { text: C.pct(s.pTarget) }), h('i', { text: `${C.num(s.targetR, 1)}R` })),
      h('div', {}, h('span', { text: '손절 선도달' }), h('b', { text: C.pct(s.pStop) }), h('i', { text: `미결 ${C.pct(s.pOpen)}` })),
      h('div', {}, h('span', { text: '평균' }), h('b', { class: s.expR >= 0 ? 'up' : 'down', text: C.r(s.expR) }),
        h('i', { text: `보유 ${C.num(s.avgDays, 0)}일` })));
    const fan = h('div', { class: 'chart h-sm', role: 'img', 'aria-label': '시뮬레이션 가격 분포(10~90% 구간)' });
    const dist = h('div', { class: 'chart h-sm', role: 'img', 'aria-label': '시뮬레이션 R 분포' });
    const hist = s.histN ? `과거 재현 ${C.num(s.histN)}회 · 목표 ${C.pct(s.histPTarget)} · 평균 ${C.r(s.histExpR)}` : '';
    const sec = h('section', { class: 'dt-sec' },
      h('div', { class: 'dt-sec-h' }, h('h3', { text: '시뮬레이션' }), h('span', { text: `${C.num(s.n)}회 · 60영업일` })),
      trio,
      h('div', { class: 'dt-sec-h' }, h('h3', { text: '가격 분포' }), h('span', { text: '중앙값 · 10–90% 구간' })), fan,
      h('div', { class: 'dt-sec-h', style: 'margin-top:16px' }, h('h3', { text: '결과 분포' }), h('span', { text: hist })), dist);

    requestAnimationFrame(() => {
      const base = it.buyHigh || it.close;
      const p = s.fan || {};
      const rows = (p.p50 || []).map((v, i) => ({ day: i + 1, 중앙값: base * v, lo: base * p.p10[i], hi: base * p.p90[i] }));
      const ann = [];
      if (C.ok(it.stop)) ann.push({ type: 'line', y: it.stop, label: '손절' });
      if (C.ok(it.t1)) ann.push({ type: 'line', y: it.t1, label: '목표 1' });
      C.chart(fan, 'line', { data: rows, x: 'day', xType: 'linear', y: ['중앙값'], lower: ['lo'], upper: ['hi'],
        height: 160, animateOnView: false, annotations: ann, showLabels: false, endLabels: false, format: { maximumFractionDigits: C.decimals } });
      const bins = (s.rHist || []).map((b) => ({ r: `${b.r > 0 ? '+' : b.r < 0 ? '−' : ''}${C.num(Math.abs(b.r), Number.isInteger(b.r) ? 0 : 1)}R`, share: b.share * 100 }));
      const maxR = bins.reduce((m, b, i) => (b.share > bins[m].share ? i : m), 0);
      C.chart(dist, 'bar', { data: bins, x: 'r', y: 'share', unit: '%', format: { maximumFractionDigits: 0 },
        height: 150, animateOnView: false, highlight: maxR, showLabels: false });
    });
    return sec;
  }

  /* ── 상세: 펀더멘털(해외) ───────────────────────────────── */
  function fundSection(it) {
    const f = it.fundamentals;
    if (!f) return null;
    const v = (x, label) => (C.ok(x) ? signed(x) : label || '–');
    const cell = (k, val, cls) => h('div', {}, h('span', { text: k }), h('b', { class: cls || '', text: val }));
    const cls = (x) => (C.ok(x) ? (x >= 0 ? 'up' : 'down') : '');
    return h('section', { class: 'dt-sec' },
      h('div', { class: 'dt-sec-h' }, h('h3', { text: '분기 실적' }), h('span', { text: '전년 동기 대비' })),
      h('div', { class: 'kv' },
        cell('매출', v(f.revYoy, f.revLabel), cls(f.revYoy)),
        cell('희석 EPS', v(f.epsYoy, f.epsLabel), cls(f.epsYoy)),
        cell('EPS 추세', f.epsAccel == null ? '–' : f.epsAccel ? '가속' : '둔화'),
        cell('영업이익률', C.ok(f.opMargin) ? `${C.num(f.opMargin, 1)}%` : '–'),
        cell('이익률 변화', C.ok(f.marginDelta) ? `${f.marginDelta >= 0 ? '+' : '−'}${C.num(Math.abs(f.marginDelta), 1)}%p` : '–', cls(f.marginDelta)),
        cell('실적 발표', it.earningsDate ? it.earningsDate.slice(5).replace('-', '/') : '미정')));
  }

  /* ── 상세: 판단 근거 ────────────────────────────────────── */
  function notesSection(it) {
    const notes = it.notes || [];
    if (!notes.length && !it.edgeSource) return null;
    const isBlock = (t) => /보류|금지|중단/.test(t);
    return h('section', { class: 'dt-sec' },
      h('div', { class: 'dt-sec-h' }, h('h3', { text: '판단 근거' }), h('span', { text: it.edgeSource || '' })),
      h('ul', { class: 'log-list' }, notes.map((t) => h('li', { class: isBlock(t) ? 'blk' : '', text: t }))));
  }

  function renderDetail(it) {
    if (!it) return;
    selected = it.code;
    document.querySelectorAll('#plan-table .row').forEach((r) => r.classList.toggle('sel', r.dataset.code === it.code));
    const box = document.getElementById('detail');
    const chartEl = h('div', { class: 'chart h-lg' });
    const priceSec = h('section', { class: 'dt-sec' },
      h('div', { class: 'dt-sec-h' }, h('h3', { text: '가격' }), h('span', { text: `최근 ${(it.history || []).length}영업일 · 20/50일선` })), chartEl);
    box.replaceChildren(...[head(it), levels(it), priceSec, simSection(it), fundSection(it), notesSection(it)].filter(Boolean));
    requestAnimationFrame(() => priceChart(it, chartEl));
    renderBottom();
  }

  /* ── 하단 분포 차트 ─────────────────────────────────────── */
  function renderBottom() {
    const pts = items.filter((i) => C.ok(i.riskPct) && i.sim && C.ok(i.sim.pTarget));
    const rr = document.getElementById('rr-chart');
    if (rr) {
      if (!pts.length) rr.replaceChildren(h('p', { class: 'empty', text: '시뮬레이션 결과 없음' }));
      else C.chart(rr, 'scatter', {
        data: pts.map((i) => ({ name: i.name, code: i.code, x: Math.round(i.riskPct * 1000) / 10, y: Math.round(i.sim.pTarget * 100) })),
        x: 'x', y: 'y', label: 'name', xLabel: '손절폭 (%)', yLabel: '목표 선도달 (%)', zero: true, height: 240,
        unit: '%', highlight: (d) => d.code === selected, refLines: { y: 33 },
      });
    }
    const ex = document.getElementById('exp-chart');
    const sims = items.filter((i) => i.sim && C.ok(i.sim.expR));
    if (ex) {
      if (!sims.length) ex.replaceChildren(h('p', { class: 'empty', text: '시뮬레이션 결과 없음' }));
      else C.chart(ex, 'bar', {
        data: sims.map((i) => ({ x: i.name, y: Math.round(i.sim.expR * 100) / 100, code: i.code })),
        x: 'x', y: 'y', orientation: 'horizontal', sort: true, unit: 'R', format: { maximumFractionDigits: 2 },
        height: Math.max(110, sims.length * 32 + 56),
        highlight: (d) => d.code === selected,
      });
    }
  }

  /* ── 필터 ───────────────────────────────────────────────── */
  function bindFilter() {
    const seg = document.getElementById('plan-filter');
    if (!seg) return;
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      seg.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
      document.querySelectorAll('#plan-table .row').forEach((r) => {
        const act = r.dataset.act === 'true';
        r.hidden = b.dataset.f === 'act' ? !act : b.dataset.f === 'rest' ? act : false;
      });
    });
  }

  async function init() {
    const snap = await C.getJson(`/api/plans/${C.market}`);
    items = (snap && snap.items) || [];
    if (!items.length) return;
    const byCode = Object.fromEntries(items.map((i) => [i.code, i]));
    document.querySelectorAll('#plan-table .row').forEach((row) => {
      const pick = () => renderDetail(byCode[row.dataset.code]);
      row.addEventListener('click', (e) => { if (!e.target.closest('a')) pick(); });
      row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    });
    bindFilter();
    const first = document.querySelector('#plan-table .row');
    if (first) renderDetail(byCode[first.dataset.code]);
  }
  init();
})();
