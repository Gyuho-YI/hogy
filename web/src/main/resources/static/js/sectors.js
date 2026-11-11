/*
 * 섹터 레이더
 * ① 섹터 맵(Finviz 맵 형태): 넓이 = 거래대금, 색 = 등락률(상승 적색 · 하락 청색, ±3% 에서 최대)
 *    국내는 섹터 안에 대장주 3종목 + 나머지(기타)를 중첩, 해외는 섹터·테마 ETF 1단
 *    배치는 ztd-charts 의 squarify(Bruls 등 squarified treemap), 그리기는 SVG
 * ② 쏠림 배수 상위 10 (ztd BarChart)
 */
(function () {
  const C = window.Cockpit;
  const NS = 'http://www.w3.org/2000/svg';
  const MAX_CHG = 3;            // 색이 가장 진해지는 등락률(%)
  const NEUTRAL = [228, 228, 231];
  const UP = [200, 30, 43];     // +3% 이상
  const DOWN = [29, 78, 216];   // −3% 이하
  const HEAD = 20;              // 섹터 머리글 높이(px)
  const GAP = 2;

  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  function colorOf(chg) {
    if (!C.ok(chg)) return { fill: `rgb(${NEUTRAL})`, ink: '#52525B' };
    const t = Math.min(Math.abs(chg) / MAX_CHG, 1);
    const rgb = mix(NEUTRAL, chg >= 0 ? UP : DOWN, Math.sqrt(t));
    return { fill: `rgb(${rgb})`, ink: t > 0.35 ? '#FFFFFF' : '#09090B' };
  }
  const fmtChg = (c) => (C.ok(c) ? `${c >= 0 ? '+' : '−'}${C.num(Math.abs(c), 2)}%` : '–');

  function svg(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    if (text !== undefined) el.textContent = text;
    return el;
  }

  /** 칸 하나: 사각형 + (들어가면) 이름·등락률, 마우스 오버 시 기본 툴팁 */
  function tile(g, r, name, chg, tip, strong) {
    const { fill, ink } = colorOf(chg);
    const cell = svg('g', { class: 'tm-cell', tabindex: '0', role: 'img', 'aria-label': `${name} ${fmtChg(chg)}` });
    cell.append(svg('rect', { x: r.x, y: r.y, width: Math.max(r.w, 0), height: Math.max(r.h, 0), fill }));
    cell.append(svg('title', {}, tip));
    const size = Math.max(10, Math.min(strong ? 18 : 15, Math.sqrt(r.w * r.h) / 6));
    if (r.w > 44 && r.h > size * 2.4) {
      const cx = r.x + r.w / 2;
      const cy = r.y + r.h / 2;
      const maxChars = Math.floor(r.w / (size * 0.95));
      // 길면 '이름 (티커)' → '이름' → '티커' 순으로 들어가는 표기를 고르고, 그래도 길면 말줄임
      const m = /^(.*?)\s*\(([^)]+)\)$/.exec(name);
      const options = m ? [name, m[1], m[2]] : [name];
      const fit = options.find((o) => o.length <= maxChars);
      const label = fit || `${options[options.length - 1].slice(0, Math.max(maxChars - 1, 1))}…`;
      cell.append(svg('text', { x: cx, y: cy - size * 0.15, 'text-anchor': 'middle', fill: ink,
        'font-size': size, 'font-weight': 700, 'letter-spacing': '-0.02em' }, label));
      cell.append(svg('text', { x: cx, y: cy + size * 1.05, 'text-anchor': 'middle', fill: ink,
        'font-size': Math.max(10, size * 0.78), 'font-weight': 600, opacity: 0.9 }, fmtChg(chg)));
    }
    g.append(cell);
  }

  function drawMap(el, sectors, market) {
    const rows = sectors.filter((s) => C.ok(s.value) && s.value > 0).sort((a, b) => b.value - a.value);
    if (!rows.length || !window.ZTD) {
      el.replaceChildren(C.h('p', { class: 'empty', text: '표시할 데이터 없음' }));
      return;
    }
    const W = el.clientWidth || 800;
    const H = W < 560 ? 360 : Math.round(Math.min(480, Math.max(340, W * 0.4)));
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: 'tm',
      role: 'img', 'aria-label': '섹터 맵: 넓이 거래대금, 색 등락률' });
    const boxes = window.ZTD.squarify(rows.map((s) => s.value), { x: 0, y: 0, w: W, h: H });
    const total = rows.reduce((a, s) => a + s.value, 0);

    rows.forEach((s, i) => {
      const b = boxes[i];
      const g = svg('g', {});
      const share = `${C.num((s.value / total) * 100, 1)}%`;
      const leaders = (s.leaders || []).filter((l) => C.ok(l.value) && l.value > 0);
      const nested = market === 'kr' && leaders.length && b.w > 90 && b.h > HEAD + 40;
      if (!nested) {
        tile(g, { x: b.x + GAP / 2, y: b.y + GAP / 2, w: b.w - GAP, h: b.h - GAP }, s.sector, s.change,
          `${s.sector}\n등락 ${fmtChg(s.change)} · 거래대금 비중 ${share} · 쏠림 ${C.num(s.ratio, 2)}배`, true);
        root.append(g);
        return;
      }
      // 섹터 머리글(먹색 띠) + 안쪽 종목 칸
      g.append(svg('rect', { x: b.x + GAP / 2, y: b.y + GAP / 2, width: b.w - GAP, height: b.h - GAP, fill: '#18181B' }));
      g.append(svg('text', { x: b.x + 8, y: b.y + 14, fill: '#FFFFFF', 'font-size': 11, 'font-weight': 700,
        'letter-spacing': '0.02em' }, `${s.sector}  ${fmtChg(s.change)}`));
      const inner = { x: b.x + GAP, y: b.y + HEAD, w: b.w - GAP * 2, h: b.h - HEAD - GAP };
      const rest = s.value - leaders.reduce((a, l) => a + l.value, 0);
      const kids = leaders.map((l) => ({ name: l.name, value: l.value, change: l.change, code: l.code }));
      if (rest > s.value * 0.02) kids.push({ name: `기타 ${Math.max((s.stocks || 0) - leaders.length, 0)}종목`, value: rest, change: s.change, rest: true });
      kids.sort((a, b2) => b2.value - a.value);
      window.ZTD.squarify(kids.map((k) => k.value), inner).forEach((r, j) => {
        const k = kids[j];
        tile(g, { x: r.x + GAP / 2, y: r.y + GAP / 2, w: r.w - GAP, h: r.h - GAP }, k.name, k.change,
          `${k.name}${k.code ? ` (${k.code})` : ''} · ${s.sector}\n등락 ${fmtChg(k.change)}${k.rest ? ' (섹터 가중 평균)' : ''}`);
      });
      root.append(g);
    });
    el.replaceChildren(root);
  }

  function legend(el) {
    const steps = [-3, -2, -1, 0, 1, 2, 3];
    el.replaceChildren(...steps.map((v) => {
      const { fill, ink } = colorOf(v);
      return C.h('span', { style: `background:${fill};color:${ink}`, text: v === 0 ? '0%' : `${v > 0 ? '+' : '−'}${Math.abs(v)}%` });
    }));
  }

  C.getJson(`/api/sectors/${C.market}`).then((snap) => {
    const sectors = (snap && snap.sectors) || [];
    const mapEl = document.getElementById('sector-map');
    if (mapEl) {
      drawMap(mapEl, sectors, C.market);
      let w = mapEl.clientWidth;
      new ResizeObserver(() => {                  // 폭이 바뀔 때만 다시 배치
        if (Math.abs(mapEl.clientWidth - w) > 8) { w = mapEl.clientWidth; drawMap(mapEl, sectors, C.market); }
      }).observe(mapEl);
    }
    const lg = document.getElementById('map-legend');
    if (lg) legend(lg);

    const el = document.getElementById('ratio-chart');
    const rows = sectors.filter((s) => C.ok(s.ratio)).sort((a, b) => b.ratio - a.ratio).slice(0, 10);
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
