/* 공통: CSS 토큰 → Chart.js 색상, 숫자 포맷, 기본 축 스타일 */
(function (w) {
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const decimals = Number(document.body.dataset.decimals || 0);
  const fmt = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  w.Cockpit = {
    css,
    market: document.body.dataset.market,
    fmt: (v) => (v === null || v === undefined || Number.isNaN(v) ? '-' : fmt.format(v)),
    /** 축/그리드는 뒤로 물러나게(muted, hairline) */
    axis: () => ({
      grid: { color: css('--grid'), drawTicks: false },
      border: { color: css('--axis') },
      ticks: { color: css('--muted'), padding: 6 },
    }),
    baseOptions: () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: css('--ink-2'), boxWidth: 12, boxHeight: 2, usePointStyle: false } },
        tooltip: { backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'),
                   borderColor: css('--axis'), borderWidth: 1, padding: 10 },
      },
    }),
  };
})(window);
