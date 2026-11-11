/* 공통: 숫자 포맷 · DOM 헬퍼 · 차트 마운트(ztd-charts 번들 window.ZTD) */
(function (w) {
  const decimals = Number(document.body.dataset.decimals || 0);
  const nf = (d) => new Intl.NumberFormat('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const price = nf(decimals);

  /** 값이 없거나 NaN 이면 '–' */
  const ok = (v) => v !== null && v !== undefined && !Number.isNaN(v);

  /** 태그 + 속성 + 자식으로 요소 생성(innerHTML 미사용 → 문자열 주입 없음) */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else el.setAttribute(k, v);
    });
    kids.flat().forEach((k) => { if (k !== null && k !== undefined && k !== false) el.append(k.nodeType ? k : String(k)); });
    return el;
  }

  w.Cockpit = {
    market: document.body.dataset.market,
    decimals,
    ok,
    h,
    /** 가격(시장별 소수 자릿수) */
    px: (v) => (ok(v) ? price.format(v) : '–'),
    /** 일반 숫자 */
    num: (v, d = 0) => (ok(v) ? nf(d).format(v) : '–'),
    /** 0~1 비율 → % */
    pct: (v, d = 0) => (ok(v) ? `${nf(d).format(v * 100)}%` : '–'),
    /** 부호 있는 R */
    r: (v, d = 2) => (ok(v) ? `${v >= 0 ? '+' : '−'}${nf(d).format(Math.abs(v))}R` : '–'),
    /** 차트 마운트: 번들이 없으면(오프라인 캐시 등) 조용히 생략 */
    chart(el, type, props) {
      if (!el || !w.ZTD) return;
      try { w.ZTD.mount(el, type, props); } catch (e) { console.error(e); }
    },
    async getJson(url) {
      const r = await fetch(url, { headers: { Accept: 'application/json' } });
      return r.ok ? r.json() : null;
    },
  };
})(window);
