"""
진입 시점 비교 백테스트: '미리 사서 대기' vs '점화 확인 후 매수' vs '분할 진입'

비교 전략 (청산 규칙은 3개 전략 모두 동일하게 적용해 '진입 시점'의 효과만 비교)
- A. 선진입  : '매집 후기(점화 대기)' 판정 첫날 종가 매수
- B. 점화진입: '점화' 판정 첫날 종가 매수
- C. 분할진입: A 시점에 1/3 매수 → A 보유 중 점화 발생 시 2/3 추가 매수 (자본 1단위 기준 수익률)

공통 청산 규칙
- 손절  : 진입 직전 20일 최저가 -1% (단, 진입가 -8% 보다 깊으면 -8%로 제한). 갭하락 시 시가 체결
- 익절  : 진입 후 최고 종가가 +10% 이상 도달한 뒤, 종가가 20일선 이탈 시 청산(트레일링)
- 시간손절: A 는 30영업일 내 +3% 미만이면 청산(기회비용 관리), 공통 최대 보유 60영업일

평가 지표: 승률, 평균 손익, 손익비(Payoff), 기대값(Expectancy), 평균 보유일, '20영업일당 기대수익'(자본 효율)

실행: cd screener && python entry_backtest.py   (사용자 PC에서 실행. 약 2년치 KRX 데이터 사용)
주의: 현재 상장 종목만 대상으로 하므로 상장폐지 종목이 빠지는 생존 편향(Survivorship Bias)이 있습니다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from accumulation import analyze_accumulation

MAX_STOP = 0.08
TRAIL_TRIGGER = 0.10
A_NO_PROGRESS_DAYS, A_NO_PROGRESS_MIN = 30, 0.03
MAX_HOLD = 60


@dataclass
class Trade:
    strategy: str
    entry_date: pd.Timestamp
    entry: float
    exit_date: pd.Timestamp
    exit: float
    hold: int
    ret: float
    reason: str
    ticker: str = ""


def stage_series(px: pd.DataFrame, flow: pd.DataFrame, shares_out: float,
                 short_balance: pd.Series | None = None, warmup: int = 61) -> pd.Series:
    """각 날짜 t 시점에 '그날까지의 데이터만' 사용해 매집 단계를 판정(미래 참조 방지)."""
    stages = pd.Series("해당없음", index=px.index, dtype=object)
    for i in range(warmup, len(px)):
        sb = short_balance.loc[: px.index[i]] if short_balance is not None else None
        stages.iloc[i] = analyze_accumulation(px.iloc[: i + 1], flow, shares_out, sb).stage
    return stages


def run_exit(px: pd.DataFrame, i: int, no_progress: bool) -> tuple[int, float, str]:
    """i 일 종가 진입 후 청산 시뮬레이션 → (청산 인덱스, 청산가, 사유)."""
    entry = px["Close"].iloc[i]
    base_low = px["Low"].iloc[max(0, i - 19): i + 1].min() * 0.99
    stop = max(base_low, entry * (1 - MAX_STOP))
    ma20 = px["Close"].rolling(20).mean()
    peak = entry
    last = min(i + MAX_HOLD, len(px) - 1)
    for j in range(i + 1, last + 1):
        o, l, c = px["Open"].iloc[j], px["Low"].iloc[j], px["Close"].iloc[j]
        if l <= stop:
            return j, min(o, stop), "손절"
        peak = max(peak, c)
        if peak >= entry * (1 + TRAIL_TRIGGER) and c < ma20.iloc[j]:
            return j, c, "트레일링"
        if no_progress and j - i == A_NO_PROGRESS_DAYS and c < entry * (1 + A_NO_PROGRESS_MIN):
            return j, c, "시간손절(무진전)"
    return last, px["Close"].iloc[last], "보유기간 만료" if last == i + MAX_HOLD else "데이터 종료"


def simulate(px: pd.DataFrame, stages: pd.Series) -> list[Trade]:
    trades: list[Trade] = []
    prev = stages.shift(1).fillna("해당없음")
    a_sig = np.flatnonzero((stages == "매집 후기(점화 대기)") & (prev != stages))
    b_sig = np.flatnonzero((stages == "점화") & (prev != "점화"))
    idx = px.index

    def mk(name, i, j, xp, why, weight=1.0):
        e = px["Close"].iloc[i]
        return Trade(name, idx[i], e, idx[j], xp, j - i, weight * (xp / e - 1), why)

    # A: 선진입 (보유 중 신호는 무시 → 중복 진입 방지)
    busy = -1
    a_trades = []
    for i in a_sig:
        if i <= busy or i >= len(px) - 1:
            continue
        j, xp, why = run_exit(px, i, no_progress=True)
        a_trades.append((i, j, xp, why))
        trades.append(mk("A.선진입", i, j, xp, why))
        busy = j

    # B: 점화진입
    busy = -1
    b_exits = {}
    for i in b_sig:
        if i <= busy or i >= len(px) - 1:
            continue
        j, xp, why = run_exit(px, i, no_progress=False)
        b_exits[i] = (j, xp, why)
        trades.append(mk("B.점화진입", i, j, xp, why))
        busy = j

    # C: 분할진입 = A 1/3 + (A 보유 중 점화 시) B 2/3. 미집행 2/3 는 현금(수익 0)
    for i, j, xp, why in a_trades:
        r = (xp / px["Close"].iloc[i] - 1) / 3
        hits = [k for k in b_sig if i < k <= j]
        exit_j = j
        if hits:
            k = hits[0]
            kj, kxp, _ = b_exits.get(k) or run_exit(px, k, no_progress=False)
            r += (kxp / px["Close"].iloc[k] - 1) * 2 / 3
            exit_j = max(j, kj)
            why = why + "+점화추가"
        trades.append(Trade("C.분할진입", idx[i], px["Close"].iloc[i], idx[exit_j], np.nan, exit_j - i, r, why))
    return trades


def summarize(trades: list[Trade]) -> pd.DataFrame:
    df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
        return df
    rows = []
    for name, g in df.groupby("strategy"):
        win, loss = g[g["ret"] > 0]["ret"], g[g["ret"] <= 0]["ret"]
        avg_win = win.mean() if len(win) else 0.0
        avg_loss = loss.mean() if len(loss) else 0.0
        exp = g["ret"].mean()
        hold = g["hold"].mean()
        rows.append({
            "전략": name, "거래수": len(g),
            "승률%": round(len(win) / len(g) * 100, 1),
            "평균수익%": round(avg_win * 100, 2), "평균손실%": round(avg_loss * 100, 2),
            # 손익비: 평균손실이 0(무손실)이면 계산 불가 처리
            "손익비": round(avg_win / abs(avg_loss), 2) if avg_loss < 0 else None,
            "기대값%": round(exp * 100, 2), "평균보유일": round(hold, 1),
            "20일당기대%": round(exp / hold * 20 * 100, 2) if hold > 0 else None,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import time
    from datetime import datetime, timedelta

    from kr_accumulation import MIN_MCAP_ACCUM, load
    from kr_screener import biz_date, build_universe

    end = biz_date()
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=730)).strftime("%Y%m%d")
    uni = build_universe(end)
    uni = uni[uni["시가총액"] >= MIN_MCAP_ACCUM].sort_values("시가총액", ascending=False).head(200)

    all_trades: list[Trade] = []
    for n, (t, row) in enumerate(uni.iterrows(), 1):
        try:
            px, flow, sb = load(t, start, end)
            st = stage_series(px, flow, row["상장주식수"], sb)
            for tr in simulate(px, st):
                tr.ticker = f"{t} {row['name']}"
                all_trades.append(tr)
        except Exception as e:
            print(f"  ! {t} 실패: {e}")
        finally:
            time.sleep(0.3)
        if n % 20 == 0:
            print(f"  ... {n}/{len(uni)}")

    pd.set_option("display.width", 200)
    print(summarize(all_trades).to_string(index=False))
    pd.DataFrame([t.__dict__ for t in all_trades]).to_csv(
        f"entry_backtest_{end}.csv", index=False, encoding="utf-8-sig")
