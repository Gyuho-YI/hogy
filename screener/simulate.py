"""
일봉 시뮬레이터(Time Machine 의 스윙 매매판): 매매 계획을 '그 종목 자신의 최근 1년 일봉'으로 1만 번 다시 돌려 봅니다.

trader-timemachine(5분봉·당일 청산)의 방식을 일봉·최대 60영업일 보유로 옮겼습니다.

1) 몬테카를로(블록 부트스트랩)
   - 최근 lookback 일의 각 봉을 '전일 종가 대비 비율'(시가/고가/저가/종가)로 바꿔 둡니다.
   - 연속된 block 일 묶음을 무작위로 이어 붙여 앞으로 horizon 일의 가상 경로를 만듭니다
     (하루씩 뽑으면 사라지는 추세·변동성 군집을 묶음으로 보존).
   - 매수 상단 체결 가정 → 매일 손절 먼저, 다음 목표가 확인. 한 봉이 둘 다 닿으면 손절로 셉니다(보수적).
   - 갭하락으로 손절선 아래에서 시작하면 시가 체결(-1R 보다 나쁠 수 있음).
2) 과거 재현(history)
   - 같은 손절폭·목표폭을 최근 lookback 일의 매일 종가 진입에 적용해 실제로 어떻게 끝났는지 셉니다.

R: 목표 도달 = +목표R, 손절 = (청산가-진입가)/위험, 기간 만료 = 마지막 종가 기준.

주의: 시뮬레이션은 '이 종목의 최근 성격이 이어진다면'의 분포이지 예측이 아닙니다. 상승 추세 종목은 표본 자체가
상승 편향을 가지므로, 결과는 켈리 비중 계산에 넣지 않고 '명백히 불리한 계획'을 걸러내는 필터로만 씁니다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

N_PATHS = 10_000
HORIZON = 60          # 최대 보유 영업일(백테스트 MAX_HOLD 와 동일)
BLOCK = 5             # 블록 길이(1주)
LOOKBACK = 250        # 표본 기간(약 1년)
SEED = 19
FAN_Q = (10, 25, 50, 75, 90)
MIN_HISTORY = 30      # 과거 재현 판단에 필요한 최소 표본 수


@dataclass
class SimResult:
    ok: bool
    note: str = ""
    n: int = 0
    p_target: float | None = None      # 목표 선도달 확률
    p_stop: float | None = None        # 손절 선도달 확률
    p_open: float | None = None        # 기간 내 미결(만료)
    exp_r: float | None = None         # 평균 R
    median_r: float | None = None
    avg_days: float | None = None      # 평균 보유일(청산까지)
    target_r: float | None = None
    hist_n: int = 0                    # 과거 재현 표본 수
    hist_p_target: float | None = None
    hist_p_stop: float | None = None
    hist_exp_r: float | None = None
    fan: dict[str, list[float]] = field(default_factory=dict)   # 일자별 종가 분위수(p10~p90), 진입가 = 1.0 기준
    r_hist: list[dict] = field(default_factory=list)            # R 분포 히스토그램 [{r, share}]

    def to_record(self) -> dict:
        d = asdict(self)
        return {
            "ok": d["ok"], "note": d["note"], "n": d["n"],
            "pTarget": d["p_target"], "pStop": d["p_stop"], "pOpen": d["p_open"],
            "expR": d["exp_r"], "medianR": d["median_r"], "avgDays": d["avg_days"], "targetR": d["target_r"],
            "histN": d["hist_n"], "histPTarget": d["hist_p_target"], "histPStop": d["hist_p_stop"],
            "histExpR": d["hist_exp_r"], "fan": d["fan"], "rHist": d["r_hist"],
        }


def _ratios(px: pd.DataFrame, lookback: int) -> np.ndarray | None:
    """(L, 4) 배열: 전일 종가 대비 시가·고가·저가·종가 비율. 결측·0 은 제외."""
    seg = px[["Open", "High", "Low", "Close"]].iloc[-(lookback + 1):].to_numpy(dtype=float)
    if len(seg) < BLOCK * 4 + 1:
        return None
    prev = seg[:-1, 3:4]
    r = seg[1:] / prev
    r = r[np.isfinite(r).all(axis=1) & (prev[:, 0] > 0)]
    return r if len(r) >= BLOCK * 4 else None


def _resolve(o, h, lo, c, entry, stop, target):
    """
    가격 경로(N, T) → 청산 일자·청산가·결과(1 목표 / -1 손절 / 0 만료).
    같은 봉에서 손절과 목표가 모두 닿으면 손절(보수적).
    """
    n, t = c.shape
    stop_hit = lo <= stop
    tgt_hit = h >= target
    big = t + 1
    first_stop = np.where(stop_hit.any(axis=1), stop_hit.argmax(axis=1), big)
    first_tgt = np.where(tgt_hit.any(axis=1), tgt_hit.argmax(axis=1), big)
    rows = np.arange(n)
    outcome = np.zeros(n, dtype=int)
    exit_px = c[:, -1].copy()
    exit_day = np.full(n, t - 1)

    s = (first_stop <= first_tgt) & (first_stop < big)
    exit_day[s] = first_stop[s]
    exit_px[s] = np.minimum(o[rows[s], first_stop[s]], stop)   # 갭하락은 시가 체결
    outcome[s] = -1

    g = (first_tgt < first_stop) & (first_tgt < big)
    exit_day[g] = first_tgt[g]
    exit_px[g] = target          # 갭상승도 목표가 체결로 보수 처리
    outcome[g] = 1
    return exit_day, exit_px, outcome


def simulate_plan(px: pd.DataFrame, entry: float, stop: float, target: float,
                  n: int = N_PATHS, horizon: int = HORIZON, block: int = BLOCK,
                  lookback: int = LOOKBACK, seed: int = SEED) -> SimResult:
    if not all(np.isfinite([entry, stop, target])) or not (stop < entry < target):
        return SimResult(False, "손절 < 진입 < 목표 조건 불충족")
    ratios = _ratios(px, lookback)
    if ratios is None:
        return SimResult(False, "표본 일봉 부족")
    risk = entry - stop
    target_r = (target - entry) / risk

    # ---- 1) 블록 부트스트랩 경로 ----
    rng = np.random.default_rng(seed)
    k = -(-horizon // block)
    starts = rng.integers(0, len(ratios) - block + 1, size=(n, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :horizon]
    r = ratios[idx]                                  # (n, horizon, 4)
    closes = entry * np.cumprod(r[:, :, 3], axis=1)
    prev = np.concatenate([np.full((n, 1), entry), closes[:, :-1]], axis=1)
    o, h, lo = prev * r[:, :, 0], prev * r[:, :, 1], prev * r[:, :, 2]
    day, xp, out = _resolve(o, h, lo, closes, entry, stop, target)
    rr = (xp - entry) / risk

    fan = {f"p{q}": [round(float(v / entry), 4) for v in np.percentile(closes, q, axis=0)] for q in FAN_Q}
    edges = np.arange(-2.0, max(3.0, target_r + 0.5) + 0.25, 0.5)
    counts, _ = np.histogram(np.clip(rr, edges[0], edges[-1] - 1e-9), bins=edges)
    r_hist = [{"r": round(float(edges[i] + 0.25), 2), "share": round(float(c / n), 4)} for i, c in enumerate(counts)]

    res = SimResult(
        True, "", n,
        p_target=round(float((out == 1).mean()), 4), p_stop=round(float((out == -1).mean()), 4),
        p_open=round(float((out == 0).mean()), 4), exp_r=round(float(rr.mean()), 3),
        median_r=round(float(np.median(rr)), 3), avg_days=round(float(day.mean() + 1), 1),
        target_r=round(float(target_r), 2), fan=fan, r_hist=r_hist,
    )

    # ---- 2) 과거 재현: 같은 손절폭·목표폭으로 최근 매일 종가 진입 ----
    hist = px[["Open", "High", "Low", "Close"]].iloc[-(lookback + horizon + 1):].to_numpy(dtype=float)
    stop_pct, tgt_pct = stop / entry, target / entry
    hr, hn = [], 0
    for i in range(len(hist) - 1):
        fwd = hist[i + 1: i + 1 + horizon]
        if len(fwd) < 10:          # 이후 데이터가 너무 짧은 진입일은 제외
            break
        e = hist[i, 3]
        d, x, _ = _resolve(fwd[None, :, 0], fwd[None, :, 1], fwd[None, :, 2], fwd[None, :, 3],
                           e, e * stop_pct, e * tgt_pct)
        hr.append((float(x[0]) - e) / (e - e * stop_pct))
        hn += 1
    if hn:
        a = np.asarray(hr)
        res.hist_n = hn
        res.hist_p_target = round(float((a >= target_r - 1e-9).mean()), 4)
        res.hist_p_stop = round(float((a <= -1 + 1e-9).mean()), 4)
        res.hist_exp_r = round(float(a.mean()), 3)
    return res


def sim_verdict(s: SimResult) -> tuple[bool, str]:
    """
    필터 판정: 몬테카를로와 과거 재현이 '둘 다' 기대 R < 0 일 때만 진입 보류(한쪽만 불리하면 경고).
    반환: (차단 여부, 메모)
    """
    if not s.ok:
        return False, f"시뮬레이션 생략({s.note})"
    mc_bad = s.exp_r is not None and s.exp_r < 0
    hist_bad = s.hist_n >= MIN_HISTORY and s.hist_exp_r is not None and s.hist_exp_r < 0
    summary = (f"시뮬 {s.n:,}회: 목표 {s.p_target:.0%} · 손절 {s.p_stop:.0%} · 평균 {s.exp_r:+.2f}R"
               + (f" / 과거 {s.hist_n}회 평균 {s.hist_exp_r:+.2f}R" if s.hist_n else ""))
    if mc_bad and hist_bad:
        return True, summary + " → 기대값 음수, 진입 보류"
    if mc_bad or hist_bad:
        return False, summary + " (한쪽 기대값 음수: 비중 축소 검토)"
    return False, summary
