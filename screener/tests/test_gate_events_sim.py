"""2~4단계: 리스크 게이트, 실적 발표 회피, 일봉 시뮬레이터, EPS·마진 펀더멘털 (네트워크 없이)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

import events as ev
import us_screener as u
from risk_gate import Candidate, GateLimits, apply_gate
from simulate import simulate_plan, sim_verdict
from trade_plan import Edge, TradePlan


def _plan(weight=0.2, risk=0.05, action="지금 매수 가능", shares=10):
    e = Edge(None, None, 0, None, None, 0.01, "test")
    return TradePlan(action, "점화", 95, 100, 95, 110, 115, "", risk, e, weight, shares, 0, None, [])


# ---------------- 리스크 게이트 ----------------
def test_게이트_총위험_누적_컷():
    # 각 1% 위험(20% × 5%) → 6개까지 통과, 7번째부터 보류(점수 높은 순)
    cands = [Candidate(f"S{i}", _plan(), score=100 - i) for i in range(8)]
    rep = apply_gate(cands, GateLimits(max_heat=0.06, max_positions=10))
    assert rep["passed"] == 6 and rep["gated"] == 2 and rep["heatUsed"] == pytest.approx(0.06)
    blocked = [c.code for c in cands if "gate" in c.plan.blocks]
    assert blocked == ["S6", "S7"]
    assert all(c.plan.shares_now == 0 and c.plan.action == "관망" for c in cands if c.code in blocked)


def test_게이트_업종_집중_한도():
    cands = [Candidate("A", _plan(), 90, "반도체"), Candidate("B", _plan(), 80, "반도체"),
             Candidate("C", _plan(), 70, "반도체"), Candidate("D", _plan(), 60, "은행"), Candidate("E", _plan(), 50)]
    apply_gate(cands, GateLimits(max_per_group=2))
    assert [c.code for c in cands if "gate" in c.plan.blocks] == ["C"]
    assert any("반도체" in n for n in cands[2].plan.notes)


def test_게이트_기존보유_위험_반영():
    cands = [Candidate("A", _plan(), 90), Candidate("B", _plan(), 80)]
    rep = apply_gate(cands, GateLimits(held_heat=0.05, max_heat=0.06))
    assert rep["passed"] == 1 and "gate" in cands[1].plan.blocks


def test_게이트는_관망_종목을_세지_않음():
    cands = [Candidate("A", _plan(action="관망", shares=0), 99), Candidate("B", _plan(), 1)]
    rep = apply_gate(cands, GateLimits(max_positions=1))
    assert rep["passed"] == 1 and not cands[1].plan.blocks


# ---------------- 실적 발표 ----------------
def test_영업일_계산과_차단_구간():
    mon = date(2026, 11, 9)
    assert ev.business_days_until(date(2026, 11, 13), mon) == 4       # 월 → 금
    assert ev.business_days_until(date(2026, 11, 16), mon) == 5       # 다음 월
    assert ev.earnings_block(5) and ev.earnings_block(0)
    assert not ev.earnings_block(6) and not ev.earnings_block(-1) and not ev.earnings_block(None)


class _Cal:
    def __init__(self, cal=None, ed=None):
        self.calendar = cal
        self._ed = ed

    def get_earnings_dates(self, limit=8):
        if self._ed is None:
            raise RuntimeError("no data")
        return self._ed


def test_실적일_조회_dict_와_대체경로():
    today = date(2026, 11, 10)
    tk = _Cal({"Earnings Date": [date(2026, 11, 13), date(2026, 11, 14)]})
    assert ev.next_earnings_date(tk, today) == date(2026, 11, 13)
    idx = pd.DatetimeIndex(["2026-08-01", "2027-02-03"]).tz_localize("America/New_York")
    tk2 = _Cal({}, pd.DataFrame({"EPS Estimate": [1, 2]}, index=idx))
    assert ev.next_earnings_date(tk2, today) == date(2027, 2, 3)
    assert ev.next_earnings_date(_Cal(None, None), today) is None


def test_국내_실적시즌():
    assert ev.kr_earnings_season(date(2026, 11, 11))
    assert not ev.kr_earnings_season(date(2026, 12, 15))


# ---------------- 시뮬레이터 ----------------
def _walk(drift, n=400, vol=0.015, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    idx = pd.bdate_range("2024-06-03", periods=n)
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.006, "Low": np.minimum(o, c) * 0.994,
                         "Close": c, "Volume": 1e6}, index=idx)


def test_시뮬레이터_확률_합과_재현성():
    px = _walk(0.0)
    e = float(px["Close"].iloc[-1])
    a = simulate_plan(px, e, e * 0.95, e * 1.10, n=4000)
    b = simulate_plan(px, e, e * 0.95, e * 1.10, n=4000)
    assert a.ok and a.p_target + a.p_stop + a.p_open == pytest.approx(1, abs=1e-3)
    assert a.p_target == b.p_target                      # 고정 시드
    assert a.target_r == pytest.approx(2.0)
    assert len(a.fan["p50"]) == 60 and a.hist_n > 100
    assert sum(x["share"] for x in a.r_hist) == pytest.approx(1, abs=1e-3)


def test_추세에_따라_결과가_갈림():
    up, down = _walk(0.004, seed=1), _walk(-0.004, seed=1)
    eu, ed = float(up["Close"].iloc[-1]), float(down["Close"].iloc[-1])
    su = simulate_plan(up, eu, eu * 0.95, eu * 1.10, n=4000)
    sd = simulate_plan(down, ed, ed * 0.95, ed * 1.10, n=4000)
    assert su.p_target > sd.p_target and su.exp_r > sd.exp_r
    blk_d, note_d = sim_verdict(sd)
    assert blk_d and "진입 보류" in note_d           # 하락 추세는 둘 다 음수 → 차단
    assert not sim_verdict(su)[0]


def test_시뮬레이터_잘못된_입력():
    px = _walk(0.0)
    assert not simulate_plan(px, 100, 101, 110).ok      # 손절 > 진입
    assert not simulate_plan(px.iloc[:10], 100, 95, 110).ok


# ---------------- 펀더멘털 ----------------
class _Tk:
    def __init__(self, eps, rev, op):
        cols = pd.to_datetime([f"2026-{m:02d}-28" for m in (9, 6, 3)] + ["2025-12-31", "2025-09-30", "2025-06-30"])
        self.quarterly_income_stmt = pd.DataFrame([rev, eps, op], index=["Total Revenue", "Diluted EPS", "Operating Income"],
                                                  columns=cols[: len(rev)])
        self.info = {}


def test_EPS_가속과_마진_개선():
    tk = _Tk(eps=[1.5, 1.2, 1.0, 0.9, 1.0, 0.95], rev=[130, 120, 110, 105, 100, 98], op=[26, 22, 18, 16, 15, 14])
    f = u.quarterly_fundamentals(tk)
    assert f.eps.rate == pytest.approx(0.5) and f.eps_prev.rate == pytest.approx(1.2 / 0.95 - 1)
    assert f.eps_accelerating is True                    # 50% > 직전 분기 26% → 가속
    assert f.op_margin == pytest.approx(0.2) and f.margin_delta == pytest.approx(0.2 - 0.15)
    assert not f.failures()


def test_EPS_기준_탈락과_계산불가():
    weak = u.quarterly_fundamentals(_Tk(eps=[1.1, 1, 1, 1, 1.0], rev=[130, 1, 1, 1, 100], op=[1, 1, 1, 1, 1]))
    assert weak.failures() == ["EPS YoY 10% < 25%"]
    loss = u.quarterly_fundamentals(_Tk(eps=[-0.2, 1, 1, 1, 0.5], rev=[130, 1, 1, 1, 100], op=[1, 1, 1, 1, 1]))
    assert loss.failures() == ["EPS 적자전환"]
    short = u.quarterly_fundamentals(_Tk(eps=[1.5, 1.2], rev=[130, 120], op=[1, 1]))
    assert short.eps.label == "계산불가" and not short.failures()   # 데이터 부족은 탈락시키지 않음
