"""1단계 규칙: 해외 점화 판정(형태+거래량), 매물 저항 손익비, 백테스트 비용·손절 규칙 통일 (네트워크 없이)."""
import numpy as np
import pandas as pd

import entry_backtest as bt
import us_screener as u
from common import detect_vcp
from trade_plan import build_plan, kelly_edge


def _vcp_base(n=300, seed=4):
    """우상향 후 수축 베이스(T1 18% → T2 9% → T3 4.6%) + 거래량 고갈."""
    rng = np.random.default_rng(seed)
    c = np.linspace(50, 100, n) + rng.normal(0, 0.3, n)
    base = np.r_[np.linspace(100, 82, 10), np.linspace(82, 99, 12), np.linspace(99, 90, 8),
                 np.linspace(90, 98.5, 10), np.linspace(98.5, 94, 6), np.linspace(94, 97.5, 10)]
    c = np.r_[c[: n - len(base)], base]
    v = np.full(n, 1e6)
    v[-11:] = 4e5
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * 0.995, "Close": c, "Volume": v}, index=idx)


def _with_breakout(df, vol):
    """피벗 위 종가 + 지정 거래량의 돌파봉 1개 추가."""
    pivot = detect_vcp(df).pivot
    c = pivot * 1.02
    bar = pd.DataFrame({"Open": [c * 0.99], "High": [c * 1.005], "Low": [c * 0.985], "Close": [c], "Volume": [vol]},
                       index=df.index[-1:] + pd.offsets.BDay(1))
    return pd.concat([df, bar])


def test_거래량_동반_돌파만_점화():
    base = _vcp_base()
    assert detect_vcp(base).is_vcp
    hot = _with_breakout(base, vol=3e6)       # 50일 평균(≈0.9M)의 300%
    v = detect_vcp(hot)
    assert v.shape_ok and v.breakout_days_ago == 0 and v.breakout_today
    assert u.classify_stage(v, float(hot["Close"].iloc[-1]))[0] == "점화"


def test_거래량_없는_돌파는_점화_아님():
    weak = _with_breakout(_vcp_base(), vol=9e5)  # 평균 수준 거래량
    v = detect_vcp(weak)
    stage, note = u.classify_stage(v, float(weak["Close"].iloc[-1]))
    assert stage == "추세만 충족" and "거래량" in note


def test_돌파_다음날도_점화_유지():
    hot = _with_breakout(_vcp_base(), vol=3e6)
    nxt = hot.iloc[-1:].copy()
    nxt.index = nxt.index + pd.offsets.BDay(1)
    nxt["Volume"] = 1.2e6
    two = pd.concat([hot, nxt])
    v = detect_vcp(two)
    assert v.breakout_days_ago == 1
    assert u.classify_stage(v, float(two["Close"].iloc[-1]))[0] == "점화"


def _box_under_high(n=300, peak=53_000.0, box=50_000.0):
    """52주 고점(peak) 아래 박스권(box) 종목. 국내 가격대(호가 100원)."""
    c = np.r_[np.linspace(40_000, peak, 150), np.linspace(peak, box, 80), np.full(n - 230, box)]
    c = c + np.sin(np.arange(n)) * 150
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * 0.995, "Close": c, "Volume": 1e6}, index=idx)


EDGE = kelly_edge(0.5, 2.0, 100)


def test_매물_저항까지_2R_미만이면_진입_보류():
    px = _box_under_high(peak=51_000.0)             # 고점까지 약 +2%, 손절폭 약 1.6% → 2R 미만
    p = build_plan(px, "매집 후기(점화 대기)", EDGE, 10_000_000, pivot=50_300.0)
    assert p.rr_resistance is not None and p.rr_resistance < 2
    assert "rr_resistance" in p.blocks and p.action == "관망" and p.shares_now == 0
    assert any("저항" in n for n in p.notes)


def test_매수_하단은_상단을_넘지_않음():
    px = _box_under_high(peak=70_000.0)
    p = build_plan(px, "매집 후기(점화 대기)", EDGE, 10_000_000, pivot=50_300.0)
    assert p.buy_low <= p.buy_high


def test_저항이_멀면_정상_진행():
    px = _box_under_high(peak=70_000.0)             # 고점까지 +40%
    p = build_plan(px, "매집 후기(점화 대기)", EDGE, 10_000_000, pivot=50_300.0)
    assert p.rr_resistance is not None and p.rr_resistance >= 2
    assert "rr_resistance" not in p.blocks and p.action == "지금 매수 가능"


def test_저항_손익비_계산값():
    px = _box_under_high(peak=51_000.0)
    p = build_plan(px, "매집 후기(점화 대기)", EDGE, 10_000_000, pivot=50_300.0)
    hi52 = float(px["High"].iloc[-252:].max())
    expect = (hi52 * 0.99 - p.buy_high) / (p.buy_high - p.stop)
    assert abs(p.rr_resistance - expect) / expect < 0.1     # 호가 보정 전/후 차이 허용


def test_백테스트_비용_차감():
    px = _box_under_high(peak=70_000.0)
    st = pd.Series("해당없음", index=px.index, dtype=object)
    st.iloc[200] = "점화"
    trades = bt.simulate(px, st)
    b = [t for t in trades if t.strategy == "B.점화진입"][0]
    gross = b.exit / b.entry - 1
    assert abs(b.ret - (gross - bt.ROUND_TRIP_COST)) < 1e-12


def test_백테스트_손절은_계획과_같은_규칙():
    px = _box_under_high(peak=70_000.0)
    edge = EDGE
    i = len(px) - 1
    pivot = float(px["High"].iloc[-21:-1].max())
    plan = build_plan(px, "매집 후기(점화 대기)", edge, 10_000_000, pivot=pivot, accum_start_idx=i - 40)
    s = bt.entry_stop(px, i, "pre")
    assert 0 <= s - plan.stop < 100     # 계획 손절은 호가 단위(5만원대 100원)로 내림 보정
    assert s < px["Close"].iloc[-1]
