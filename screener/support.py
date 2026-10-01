"""
지지선 산출 + 추격매수 판단 모듈.

지지선 5종 (가격대가 ±2% 안에서 겹칠수록 강한 '지지 구간'으로 병합)
1) 돌파 피벗     : 돌파 전 저항선. 돌파 후에는 지지로 역할 전환(Role Reversal)
2) 앵커드 VWAP   : 점화일(또는 매집 시작일)부터의 거래량 가중 평균가 = 해당 매수 주체의 평균 단가 근사
3) 매물대(POC)   : 최근 N일 거래량이 가장 많이 쌓인 가격대(Volume Profile)
4) 점화봉 50%    : 점화일 장대양봉의 중간값. 이 아래로 밀리면 돌파 실패 신호
5) 20일선        : 추세 종목의 1차 눌림 지지
6) 박스하단      : 최근 20일 저가. 매집 박스 이탈 = 매집 가설 무효

추격 판단: '얼마나 올랐나'가 아니라 '손절선까지 거리'로 판단합니다.
- 진입가 ~ 가장 가까운 지지(손절선) 거리가 8% 이하이고, ATR 2배 이하이며, 손익비 3:1 이상일 때만 허용
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def atr(px: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR(평균 실제 변동폭). 갭까지 반영한 일일 변동성."""
    prev = px["Close"].shift(1)
    tr = pd.concat([px["High"] - px["Low"], (px["High"] - prev).abs(), (px["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def anchored_vwap(px: pd.DataFrame, anchor: int) -> float:
    """anchor 인덱스부터 현재까지의 VWAP. 대표가격 = (고+저+종)/3."""
    seg = px.iloc[anchor:]
    tp = (seg["High"] + seg["Low"] + seg["Close"]) / 3
    v = seg["Volume"].sum()
    return float((tp * seg["Volume"]).sum() / v) if v > 0 else float("nan")


def volume_poc(px: pd.DataFrame, lookback: int = 120, bins: int = 40) -> float:
    """최근 lookback 일 매물대 중 거래량 최대 가격대(Point of Control)."""
    seg = px.iloc[-lookback:]
    tp = ((seg["High"] + seg["Low"] + seg["Close"]) / 3).to_numpy()
    hist, edges = np.histogram(tp, bins=bins, weights=seg["Volume"].to_numpy())
    k = int(hist.argmax())
    return float((edges[k] + edges[k + 1]) / 2)


@dataclass
class Zone:
    price: float          # 구간 대표가(겹친 지지선 평균)
    sources: list[str]    # 어떤 지지선들이 겹쳤는지
    strength: int         # 겹친 개수(2개 이상 = 강한 지지)
    low: float = 0.0      # 구간 최저 레벨(손절 기준은 평균이 아닌 구간 하단)


def support_zones(px: pd.DataFrame, pivot: float | None = None, ignition_idx: int | None = None,
                  accum_start_idx: int | None = None, merge_tol: float = 0.02) -> list[Zone]:
    """현재가 아래의 지지선을 모아 ±merge_tol 이내끼리 병합, 가까운 순으로 반환."""
    c = px["Close"].iloc[-1]
    levels: list[tuple[float, str]] = []
    if pivot:
        levels.append((pivot, "돌파피벗"))
    if ignition_idx is not None:
        levels.append((anchored_vwap(px, ignition_idx), "AVWAP(점화일)"))
        bar = px.iloc[ignition_idx]
        levels.append(((bar["High"] + bar["Low"]) / 2, "점화봉50%"))
        levels.append((bar["Low"], "점화봉저가"))
    if accum_start_idx is not None:
        levels.append((anchored_vwap(px, accum_start_idx), "AVWAP(매집시작)"))
    levels.append((volume_poc(px), "매물대POC"))
    levels.append((px["Low"].iloc[-20:].min(), "박스하단(20일저가)"))
    levels.append((px["Close"].rolling(20).mean().iloc[-1], "20일선"))

    below = sorted([(p, s) for p, s in levels if pd.notna(p) and p < c], reverse=True)
    zones: list[Zone] = []
    for p, s in below:
        if zones and abs(zones[-1].price - p) / p <= merge_tol:
            z = zones[-1]
            z.sources.append(s)
            z.price = (z.price * (len(z.sources) - 1) + p) / len(z.sources)
            z.strength = len(z.sources)
            z.low = min(z.low, p)
        else:
            zones.append(Zone(p, [s], 1, p))
    for z in zones:
        z.price = round(float(z.price), 2)
        z.low = round(float(z.low), 2)
    return zones


@dataclass
class ChaseVerdict:
    allowed: bool
    entry: float
    stop: float
    stop_dist_pct: float      # 진입가 대비 손절 거리
    atr_multiple: float       # 손절 거리 / ATR
    reward_risk: float | None # 손익비
    shares: int               # 계좌 위험 한도 기준 매수 수량
    wait_price: float | None  # 불허 시 기다릴 눌림 매수 가격(가장 강한 지지 구간)
    reasons: list[str]


def chase_check(px: pd.DataFrame, zones: list[Zone], target: float | None = None,
                account: float = 10_000_000, risk_pct: float = 0.01,
                max_stop_pct: float = 0.08, max_atr_mult: float = 2.0, min_rr: float = 3.0) -> ChaseVerdict:
    """
    현재가 추격 매수 가능 여부.
    - 손절선 = 가장 가까운 '강한 지지(2개 이상 겹침)' 구간 -1%, 없으면 가장 가까운 지지 -1%
    - 수량 = 계좌 × 위험한도(1%) ÷ (진입가 - 손절가)  → 추격할수록 수량이 자동으로 줄어듦
    """
    entry = float(px["Close"].iloc[-1])
    reasons: list[str] = []
    if not zones:
        return ChaseVerdict(False, entry, float("nan"), float("nan"), float("nan"), None, 0, None, ["현재가 아래 지지선 없음"])

    strong = [z for z in zones if z.strength >= 2]
    anchor = strong[0] if strong else zones[0]
    stop = anchor.low * 0.99
    dist = (entry - stop) / entry
    a = atr(px).iloc[-1]
    atr_mult = (entry - stop) / a if a and a > 0 else float("nan")
    rr = (target - entry) / (entry - stop) if target and entry > stop else None

    if dist > max_stop_pct:
        reasons.append(f"손절 거리 {dist:.1%} > {max_stop_pct:.0%}: 이미 늘어난(Extended) 상태")
    if pd.notna(atr_mult) and atr_mult > max_atr_mult:
        reasons.append(f"손절 거리 ATR {atr_mult:.1f}배 > {max_atr_mult}배")
    if rr is not None and rr < min_rr:
        reasons.append(f"손익비 {rr:.1f} < {min_rr}")
    day_chg = entry / px["Close"].iloc[-2] - 1
    if day_chg >= 0.20:
        reasons.append(f"당일 +{day_chg:.0%}: 상한가권 추격 금지(익일 갭하락 위험)")

    allowed = not reasons
    shares = int(account * risk_pct / (entry - stop)) if allowed and entry > stop else 0
    # 불허 시: 1차 눌림 = 가장 가까운 지지, 2차 = 가장 가까운 강한 지지(겹침 2개↑)
    wait = None if allowed else float(zones[0].price)
    if not allowed and strong and strong[0] is not zones[0]:
        reasons.append(f"1차 눌림 {zones[0].price:,.0f}({'+'.join(zones[0].sources)}) / "
                       f"2차 강한 지지 {strong[0].price:,.0f}({'+'.join(strong[0].sources)})")
    return ChaseVerdict(allowed, round(entry, 2), round(float(stop), 2), round(float(dist), 4),
                        round(float(atr_mult), 2), None if rr is None else round(float(rr), 2),
                        shares, wait, reasons or ["추격 허용: 손절 거리·손익비 기준 충족"])
