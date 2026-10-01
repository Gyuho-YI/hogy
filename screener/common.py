"""
공통 유틸리티: 신장률(YoY) 안전 계산, 이동평균 트렌드 템플릿, VCP(변동성 축소 패턴) 탐지.

- 해외(us_screener.py) / 국내(kr_screener.py) 스크리너가 함께 사용합니다.
- 입력 DataFrame 은 최소 'High', 'Low', 'Close', 'Volume' 컬럼을 가진 일봉 데이터(오래된 → 최신 순)여야 합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. 신장률(YoY) 안전 계산
# ---------------------------------------------------------------------------
@dataclass
class Growth:
    rate: float | None  # 신장률(0.2 = +20%). 계산 불가 시 None
    label: str          # '정상' / '적자전환' / '흑자전환' / '적자축소' / '적자확대' / '적자지속' / '계산불가'


def safe_yoy(curr: float | None, prev: float | None) -> Growth:
    """
    전년 대비 신장률을 예외 상황까지 고려해 계산합니다.

    - 분모(prev)가 None/NaN/0      → 계산불가 (0으로 나누기 방지)
    - prev > 0                     → 일반 공식 (curr - prev) / prev
    - prev < 0 (전년 적자)         → 부호 왜곡 방지를 위해 |prev| 로 나누고 상태 라벨 부여
        * curr >= 0 : 흑자전환
        * curr < 0 and 개선 : 적자축소
        * curr < 0 and 악화 : 적자확대
    - 결과가 마이너스(역성장)여도 값은 그대로 반환하며, 판단은 호출부에서 수행합니다.
    """
    if curr is None or prev is None or pd.isna(curr) or pd.isna(prev):
        return Growth(None, "계산불가")
    if prev == 0:
        return Growth(None, "계산불가")

    rate = (curr - prev) / abs(prev)
    if prev > 0:
        return Growth(rate, "적자전환" if curr < 0 else "정상")
    if curr >= 0:
        return Growth(rate, "흑자전환")
    return Growth(rate, "적자축소" if curr > prev else ("적자지속" if curr == prev else "적자확대"))


# ---------------------------------------------------------------------------
# 2. 미너비니 트렌드 템플릿 (8개 조건 중 가격 기반 7개)
# ---------------------------------------------------------------------------
def trend_template(df: pd.DataFrame, short: int = 50, mid: int = 150, long: int = 200) -> dict:
    """
    원전 트렌드 템플릿 조건을 점검합니다. (8번째 조건 RS Rating 은 유니버스 전체가 필요하므로 호출부에서 계산)

    1) 종가 > 150일선, 200일선     2) 150일선 > 200일선
    3) 200일선 최소 1개월 우상향    4) 50일선 > 150일선 > 200일선
    5) 종가 > 50일선               6) 종가 >= 52주 저점 * 1.30
    7) 종가 >= 52주 고점 * 0.75
    국내 시장용으로는 short/mid/long 을 20/60/120 으로 바꿔 호출합니다.
    """
    close = df["Close"]
    if len(close) < long + 21:
        return {"pass": False, "reason": "데이터 부족"}

    ma_s = close.rolling(short).mean()
    ma_m = close.rolling(mid).mean()
    ma_l = close.rolling(long).mean()
    c, s, m, l_ = close.iloc[-1], ma_s.iloc[-1], ma_m.iloc[-1], ma_l.iloc[-1]

    last_252 = df.iloc[-252:]
    hi52, lo52 = last_252["High"].max(), last_252["Low"].min()

    conds = {
        "price>mid&long": c > m and c > l_,
        "mid>long": m > l_,
        "long_rising": l_ > ma_l.iloc[-21],
        "short>mid>long": s > m > l_,
        "price>short": c > s,
        "above_52w_low_30%": lo52 > 0 and c >= lo52 * 1.30,
        "within_25%_of_52w_high": c >= hi52 * 0.75,
    }
    return {
        "pass": all(conds.values()),
        "conds": conds,
        "pct_from_high": (c / hi52 - 1) if hi52 else None,
    }


# ---------------------------------------------------------------------------
# 3. VCP (Volatility Contraction Pattern) 탐지
# ---------------------------------------------------------------------------
@dataclass
class VCPResult:
    is_vcp: bool
    contractions: list[float] = field(default_factory=list)  # 각 조정폭(0.20 = -20%)
    pivot: float | None = None                                # 마지막 고점 = 돌파 기준선
    volume_dry_up: bool = False                               # 공급 고갈 여부
    breakout_today: bool = False                              # 당일 거래량 동반 돌파 여부
    extended: bool = False                                    # 피벗 대비 5% 이상 이격(추격 금지)
    note: str = ""


def detect_vcp(
    df: pd.DataFrame,
    base_len: int = 65,          # 베이스 탐색 구간(약 3개월)
    swing: int = 5,              # 스윙 고점 판정 좌우 봉 수
    max_first_depth: float = 0.35,
    max_last_depth: float = 0.10,
    breakout_vol_mult: float = 2.0,   # 돌파일 거래량 >= 50일 평균의 200%
    dry_up_ratio: float = 0.7,        # 최근 10일 평균 거래량 <= 50일 평균의 70%
    chase_limit: float = 0.05,        # 피벗 +5% 초과 시 추격 금지
) -> VCPResult:
    """
    단순화된 VCP 탐지 로직.
    - 베이스 구간 내 스윙 고점들을 찾고, 각 고점 이후 다음 고점 전까지의 최저점으로 조정폭을 계산
    - 조정폭이 오른쪽으로 갈수록 줄어들고(T1 > T2 > T3), 마지막 조정이 10% 이하이면 VCP 로 판단
    - 마지막 스윙 고점을 피벗으로 보고, 당일 거래량 동반 돌파 여부를 함께 반환
    """
    if len(df) < max(base_len, 50) + swing:
        return VCPResult(False, note="데이터 부족")

    base = df.iloc[-base_len:]
    highs, lows = base["High"].to_numpy(), base["Low"].to_numpy()

    # 스윙 고점: 좌우 swing 봉 내 최고가 (마지막 swing 봉은 확정 불가 → 제외)
    peak_idx = [
        i for i in range(swing, len(base) - swing)
        if highs[i] == highs[i - swing: i + swing + 1].max()
    ]
    # 인접 중복 고점 제거 + 점점 낮아지거나 비슷한 고점만 사용(베이스 상단 저항)
    peak_idx = [p for k, p in enumerate(peak_idx) if k == 0 or p - peak_idx[k - 1] > swing]
    if len(peak_idx) < 2:
        return VCPResult(False, note="스윙 고점 부족")

    contractions = []
    for k, p in enumerate(peak_idx):
        end = peak_idx[k + 1] if k + 1 < len(peak_idx) else len(base)
        trough = lows[p:end].min()
        contractions.append((highs[p] - trough) / highs[p])

    # 조건: 2회 이상 수축, 단조 감소(10% 허용오차), 첫 조정 35% 이하, 마지막 조정 10% 이하
    shrinking = all(contractions[i + 1] <= contractions[i] * 1.1 for i in range(len(contractions) - 1))
    shape_ok = (
        len(contractions) >= 2
        and shrinking
        and contractions[0] <= max_first_depth
        and contractions[-1] <= max_last_depth
    )

    vol = df["Volume"]
    vol50 = vol.iloc[-51:-1].mean()  # 당일 제외 50일 평균
    dry_up = vol50 > 0 and vol.iloc[-11:-1].mean() <= vol50 * dry_up_ratio

    pivot = float(highs[peak_idx[-1]])
    c, prev_c = df["Close"].iloc[-1], df["Close"].iloc[-2]
    breakout = c > pivot and prev_c <= pivot and vol50 > 0 and vol.iloc[-1] >= vol50 * breakout_vol_mult
    extended = c > pivot * (1 + chase_limit)

    return VCPResult(
        is_vcp=bool(shape_ok and dry_up),
        contractions=[round(float(x), 4) for x in contractions],
        pivot=pivot,
        volume_dry_up=bool(dry_up),
        breakout_today=bool(breakout),
        extended=bool(extended),
        note="" if shape_ok else "수축 패턴 불충족",
    )


def rs_rank(returns: pd.Series) -> pd.Series:
    """유니버스 내 수익률 백분위(0~100). 미너비니 RS Rating 근사치(70 이상 통과)."""
    return returns.rank(pct=True) * 100
