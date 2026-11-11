/*
 * Cockpit 차트 진입점: ztd-charts(React) → 브라우저 전역 window.ZTD
 * Thymeleaf 페이지는 React 없이 이 번들 하나만 불러 씁니다.
 *
 *   ZTD.mount(el, "candlestick", { data, x: "d", ... })   // 같은 el 에 다시 부르면 갱신(애니메이션 이어짐)
 *   ZTD.unmount(el)
 *
 * 색·글꼴은 app.css 의 디자인 토큰과 같은 값으로 고정합니다(차트만 다른 색을 쓰지 않도록).
 */
import { createRoot } from "react-dom/client";
import {
  BarChart, CandlestickChart, FunnelChart, LineChart, ScatterChart, ThemeProvider, lightTheme,
} from "ztd-charts";

const TOKENS = {
  ...lightTheme,
  name: "cockpit",
  bg: "#FFFFFF",
  panel: "#FFFFFF",
  ink: "#09090B",
  muted: "#52525B",
  dim: "#A1A1AA",
  accent: "#0055FF",
  accentText: "#0044CC",
  onAccent: "#FFFFFF",
  onInk: "#FFFFFF",
  line: "#E4E4E7",
  line2: "#F4F4F5",
  neutral: "#D4D4D8",
  neutralStrong: "#71717A",
  onNeutralStrong: "#FFFFFF",
  neutralSoft: "#F4F4F5",
  lift: "#FAFAFA",
  tint: "rgba(0, 85, 255, 0.08)",
  fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
  monoFamily: '"Pretendard Variable", Pretendard, ui-monospace, monospace',
  radius: 8,
  radiusCode: 6,
  radiusMark: 2,
};

const CHARTS = {
  candlestick: CandlestickChart,
  line: LineChart,
  bar: BarChart,
  scatter: ScatterChart,
  funnel: FunnelChart,
};

const roots = new WeakMap();

function mount(el, type, props) {
  const C = CHARTS[type];
  if (!el || !C) throw new Error(`ZTD.mount: unknown chart "${type}"`);
  let root = roots.get(el);
  if (!root) {
    root = createRoot(el);
    roots.set(el, root);
  }
  root.render(
    <ThemeProvider theme={TOKENS} locale="ko-KR">
      <C locale="ko-KR" {...props} />
    </ThemeProvider>,
  );
  return root;
}

function unmount(el) {
  const root = roots.get(el);
  if (root) {
    root.unmount();
    roots.delete(el);
  }
}

window.ZTD = { mount, unmount, tokens: TOKENS, version: "0.7.0" };
