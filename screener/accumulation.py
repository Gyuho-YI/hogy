"""
'눌림 매집'(가격은 횡보·하락, 기관·외국인은 순매수) 탐지 로직. 데이터 소스와 무관한 순수 계산 모듈입니다.

핵심 가설
- 큰손은 VWAP/TWAP 알고리즘으로 분할 매수하므로 가격을 올리지 않고 '매도 물량을 흡수'합니다.
- 그 결과 [가격 ↔ 수급] 사이에 괴리(다이버전스)가 생기고, 매도 물량이 고갈되는 순간
  적은 매수에도 가격이 튀어 오릅니다(점화).

입력
- price: 일봉 DataFrame [Open, High, Low, Close, Volume] (오래된 → 최신)
- flow : 투자자별 '순매수 수량(주)' DataFrame, price 와 같은 날짜 인덱스
         (pykrx get_market_trading_volume_by_date(detail=True) 컬럼명 그대로)
- shares_out: 상장주식수
- short_balance: 공매도 잔고 수량 Series (선택, 숏커버링 판별용)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# '금융투자'는 ETF LP 헤지·차익거래 물량이 섞여 방향성이 약하므로 제외합니다.
# '기타외국인'도 소규모·노이즈가 커서 제외합니다.
SMART_COLS = ["외국인", "연기금", "투신", "사모", "보험", "은행"]
LONG_TERM_COLS = ["연기금", "투신"]  # 상대적으로 보유 기간이 긴 주체


@dataclass
class AccumResult:
    stage: str                 # '해당없음' / '매집 진행' / '매집 후기(점화 대기)' / '점화'
    score: float               # 0~100
    price_chg: float           # 관찰 기간 주가 변화율
    cum_pct_float: float       # 관찰 기간 스마트머니 누적 순매수 / 상장주식수
    buy_day_ratio: float       # 스마트머니 순매수일 비율
    absorb_ratio: float        # 하락일 중 '개인 매도 + 스마트머니 매수'로 받아낸 날의 비율
    long_term_share: float     # 누적 순매수 중 연기금·투신 비중
    ad_divergence: bool        # A/D Line 상승 & 주가 정체
    contraction: bool          # 최근 변동성·거래량 축소(매도 고갈)
    ignition: bool             # 오늘 점화 신호
    short_cover_suspect: bool  # 외국인 매수가 숏커버링 위주일 가능성
    notes: list[str]


def _slope(s: pd.Series) -> float:
    """정규화 선형회귀 기울기(일 평균 변화 / 평균 절댓값)."""
    y = s.to_numpy(dtype=float)
    if len(y) < 3 or np.allclose(y, y[0]):
        return 0.0
    x = np.arange(len(y))
    scale = np.abs(y).mean() or 1.0
    return float(np.polyfit(x, y, 1)[0] / scale)


def analyze_accumulation(
    price: pd.DataFrame,
    flow: pd.DataFrame,
    shares_out: float,
    short_balance: pd.Series | None = None,
    window: int = 40,              # 관찰 기간(약 2개월)
    max_price_chg: float = 0.05,   # 이 기간 주가 상승이 +5% 이하여야 '눌림'
    min_cum_pct: float = 0.01,     # 상장주식수의 1% 이상 순매수
    min_buy_day_ratio: float = 0.55,
) -> AccumResult:
    notes: list[str] = []
    if len(price) < window + 21 or shares_out <= 0:
        return AccumResult("해당없음", 0, 0, 0, 0, 0, 0, False, False, False, False, ["데이터 부족"])

    p = price.iloc[-window:]
    f = flow.reindex(p.index).fillna(0)
    cols = [c for c in SMART_COLS if c in f]
    smart = f[cols].sum(axis=1)
    retail = f["개인"] if "개인" in f else pd.Series(0, index=f.index)

    # [1] 가격 정체 vs 수급 누적
    price_chg = p["Close"].iloc[-1] / p["Close"].iloc[0] - 1
    cum = smart.sum()
    cum_pct = cum / shares_out
    buy_day_ratio = float((smart > 0).mean())

    # [2] '눌러가며 받기': 하락일에 개인은 팔고 스마트머니는 산 날의 비율
    down = p["Close"].diff() < 0
    absorb_ratio = float(((smart > 0) & (retail < 0) & down).sum() / down.sum()) if down.sum() else 0.0

    # [3] 누가 사는가: 연기금·투신 비중이 높을수록 지속성 ↑
    lt = f[[c for c in LONG_TERM_COLS if c in f]].sum(axis=1).sum()
    long_term_share = float(lt / cum) if cum > 0 else 0.0

    # [4] Chaikin A/D Line: 장중 저가에서 받아 종가를 끌어올린 흔적(아래꼬리)이 누적되는가
    rng = (p["High"] - p["Low"]).replace(0, np.nan)
    clv = (((p["Close"] - p["Low"]) - (p["High"] - p["Close"])) / rng).fillna(0)
    ad = (clv * p["Volume"]).cumsum()
    ad_div = _slope(ad) > 0 and price_chg <= max_price_chg

    # [5] 매도 고갈: 최근 10일 일중 변동폭·거래량이 관찰 기간 평균보다 축소
    range_pct = (price["High"] - price["Low"]) / price["Close"]
    vol = price["Volume"]
    contraction = bool(
        range_pct.iloc[-10:].mean() < range_pct.iloc[-window:].mean() * 0.8
        and vol.iloc[-10:].mean() < vol.iloc[-window:].mean() * 0.8
    )

    # [6] 점화: 직전 20일 고가 돌파 + 거래량 20일 평균 2배 + 당일 스마트머니 순매수
    prior_high = price["High"].iloc[-21:-1].max()
    vol20 = vol.iloc[-21:-1].mean()
    ignition = bool(
        price["Close"].iloc[-1] > prior_high and vol20 > 0
        and vol.iloc[-1] >= vol20 * 2 and smart.iloc[-1] > 0
    )

    # [7] 숏커버링 판별: 공매도 잔고 감소분이 외국인 순매수의 절반 이상이면 '진짜 매집' 아님
    short_cover = False
    if short_balance is not None and len(short_balance.dropna()) >= window:
        sb = short_balance.dropna()
        decrease = sb.iloc[-window] - sb.iloc[-1]
        fb = f["외국인"].sum() if "외국인" in f else 0
        if fb > 0 and decrease > 0 and decrease / fb >= 0.5:
            short_cover = True
            notes.append(f"공매도 잔고 {decrease:,.0f}주 감소 → 외국인 매수 상당분이 숏커버 추정")

    # ---- 단계 판정 ----
    accumulating = cum_pct >= min_cum_pct and price_chg <= max_price_chg and buy_day_ratio >= min_buy_day_ratio
    if short_cover:
        accumulating = False
    if not accumulating:
        stage = "해당없음"
    elif ignition:
        stage = "점화"
    elif contraction:
        stage = "매집 후기(점화 대기)"
    else:
        stage = "매집 진행"

    # ---- 점수(0~100): 상대 비교·정렬용 ----
    score = (
        min(cum_pct / 0.03, 1) * 30          # 누적 매집 강도(3% 이상 만점)
        + buy_day_ratio * 15                 # 매수 일관성
        + absorb_ratio * 15                  # 눌림 흡수
        + long_term_share * 10               # 장기 자금 비중
        + ad_div * 10 + contraction * 10 + ignition * 10
    )
    if price_chg < -0.15:
        notes.append("기간 낙폭 15% 초과: 매집이 아닌 '물타기' 가능성 점검")
    if long_term_share < 0.2 and cum > 0:
        notes.append("외국인 단독 매수: CFD·스왑 등 개인 우회 물량 가능성 점검")

    return AccumResult(
        stage, round(score if accumulating else 0, 1), round(float(price_chg), 4), round(float(cum_pct), 4),
        round(buy_day_ratio, 2), round(absorb_ratio, 2), round(long_term_share, 2),
        bool(ad_div), contraction, ignition, short_cover, notes,
    )
