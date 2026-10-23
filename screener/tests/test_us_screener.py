"""해외 스크리너: 매수 조건 미달 종목도 '관찰'+사유로 내보내고, 단계별 통계를 남기는지(네트워크 없이)."""
import types

import numpy as np
import pandas as pd

import us_screener as u


def _trend(n=300, vcp=False, seed=0):
    """우상향 일봉. vcp=True 면 마지막 구간에 변동성 축소 + 거래량 감소."""
    rng = np.random.default_rng(seed)
    c = np.linspace(50, 100, n) + rng.normal(0, 0.3, n)
    if vcp:
        base = np.r_[np.linspace(100, 82, 10), np.linspace(82, 99, 12), np.linspace(99, 90, 8),
                     np.linspace(90, 98.5, 10), np.linspace(98.5, 94, 6), np.linspace(94, 97.5, 10)]
        c = np.r_[c[: n - len(base)], base]
    v = np.full(n, 1e6)
    if vcp:
        v[-11:] = 4e5
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * 0.995, "Close": c, "Volume": v}, index=idx)


def _down(n=300):
    c = np.linspace(100, 60, n)
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * 0.995, "Close": c, "Volume": 1e6}, index=idx)


def run(monkeypatch, frames, fundamentals):
    monkeypatch.setattr(u, "load_prices", lambda tickers: {t: frames[t] for t in tickers if t in frames})
    monkeypatch.setattr(u.time, "sleep", lambda *_: None)

    class FakeTicker:
        def __init__(self, t):
            rev, de = fundamentals[t]
            q = pd.DataFrame([[rev, 1, 1, 1, 100.0]], index=["Total Revenue"])
            self.quarterly_income_stmt = q
            self.info = {"debtToEquity": de}
    monkeypatch.setattr(u.yf, "Ticker", FakeTicker)
    return u.screen(list(frames), account=20_000)


def test_관찰_사유와_통계(monkeypatch):
    frames = {"GROW": _trend(seed=1), "LOWREV": _trend(seed=2), "DEBT": _trend(seed=3), "VCPX": _trend(vcp=True, seed=4)}
    frames.update({f"D{i}": _down() for i in range(6)})          # RS 순위 비교용 하락 종목
    fundamentals = {"GROW": (130.0, 50), "LOWREV": (105.0, 50), "DEBT": (150.0, 250), "VCPX": (140.0, 30)}
    res, web, stats = run(monkeypatch, frames, fundamentals)

    assert stats["scanned"] == 10 and stats["received"] == 10
    assert stats["trend"] == 4                       # 하락 종목 6개는 추세 탈락
    by = {r["code"]: r for r in web}
    assert set(by) == {"GROW", "LOWREV", "DEBT", "VCPX"}  # 추세 통과 종목은 모두 화면에 노출
    assert any("매출 YoY 5%" in n for n in by["LOWREV"]["notes"])
    assert any("부채비율 250%" in n for n in by["DEBT"]["notes"])
    assert by["GROW"]["stage"] == u.WATCH_STAGE and any("VCP 미형성" in n for n in by["GROW"]["notes"])
    assert by["GROW"]["buyLow"] is None and by["GROW"]["sharesNow"] == 0   # 관찰은 매수 구간 없음
    assert stats["fundamental"] == 2                 # GROW, VCPX


def test_관찰종목_감시가격(monkeypatch):
    frames = {"GROW": _trend(seed=1)}
    frames.update({f"D{i}": _down() for i in range(6)})
    res, web, stats = run(monkeypatch, frames, {"GROW": (105.0, 50)})   # 매출 미달 → 관찰
    w = web[0]
    df = frames["GROW"]
    assert w["watchBreakout"] == round(float(df["High"].iloc[-30:].max()), 2)      # VCP 없으면 30일 고점
    assert w["watchExit"] == round(float(df["Close"].rolling(50).mean().iloc[-1]), 2)   # 50일선
    assert w["buyLow"] is None and w["sharesNow"] == 0                              # 매수 구간 아님
    assert any(n.startswith("감시:") for n in w["notes"])


def test_유동성_미달은_제외(monkeypatch):
    thin = _trend(seed=9)
    thin["Volume"] = 1_000                                   # 거래대금 ≈ $10만 → 제외
    frames = {"THIN": thin, "GROW": _trend(seed=1)}
    frames.update({f"D{i}": _down() for i in range(6)})
    res, web, stats = run(monkeypatch, frames, {"GROW": (130.0, 30)})
    assert stats["received"] == 8 and stats["liquid"] == 7
    assert "THIN" not in {w["code"] for w in web}


def test_전부_하락이면_빈목록이지만_통계는_정상(monkeypatch):
    frames = {f"D{i}": _down() for i in range(5)}
    res, web, stats = run(monkeypatch, frames, {})
    assert web == [] and stats["trend"] == 0 and stats["received"] == 5
