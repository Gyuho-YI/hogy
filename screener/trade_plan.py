"""
매매 계획(Trade Plan) 엔진: 하프 켈리 비중 + 매수 구간 + 손절 + 매도 구간(분할 익절·트레일링·클라이맥스)

[하프 켈리를 '손실 위험 비율'로 쓰는 이유]
- 켈리 공식 f* = p - q/b (p: 승률, q=1-p, b: 손익비)는 '한 번 질 때 잃는 자본 비율'의 최적값입니다.
- 주식은 손절선이 있으므로 전액을 잃지 않습니다. 따라서
    계좌 위험 비율(risk) = f*/2 (하프 켈리)
    포지션 비중(weight) = risk / 손절폭      예) risk 1.5%, 손절폭 6% → 비중 25%
- 풀 켈리는 승률·손익비 추정 오차에 극도로 민감해 계좌 변동성이 과도하므로 절반만 사용합니다.
- 추가 안전장치
    1) 승률은 Wilson 하한값(표본이 적을수록 보수적으로 깎임) 사용
    2) 표본 30건 미만이면 켈리 대신 고정 위험 1% 적용
    3) 종목당 위험 상한 2%, 비중 상한 25%, 기대값 ≤ 0 이면 매수 금지
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from support import Zone, atr, support_zones

# ---- 리스크 한도 ---------------------------------------------------------
MAX_RISK_PER_TRADE = 0.02   # 종목당 계좌 위험 상한 2%
MAX_WEIGHT = 0.25           # 종목당 비중 상한 25%
FALLBACK_RISK = 0.01        # 표본 부족 시 고정 위험 1%
MIN_SAMPLES = 30
MAX_STOP = 0.08             # 손절폭 상한 8%
CHASE_LIMIT = 0.05          # 피벗 +5% 초과 시 추격 금지


# ---------------------------------------------------------------------------
# 1. 호가 단위 (KRX, 2023.01 개편 기준 / KOSPI·KOSDAQ 공통)
# ---------------------------------------------------------------------------
def tick_size(price: float) -> int:
    for limit, tick in [(2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)]:
        if price < limit:
            return tick
    return 1_000


def to_tick(price: float, mode: str = "down", market: str = "KR") -> float:
    """주문 가능한 호가로 보정. 매수 지정가·손절·목표가 모두 '불리한 쪽'(down)으로 보수적 처리.
    market='US' 는 $1 이상 주식의 최소 호가 $0.01 기준."""
    if price is None or not math.isfinite(price) or price <= 0:
        return float("nan")
    if market == "US":
        return round((math.floor if mode == "down" else math.ceil)(price * 100) / 100, 2)
    t = tick_size(price)
    return float((math.floor if mode == "down" else math.ceil)(price / t) * t)


# ---------------------------------------------------------------------------
# 2. 하프 켈리
# ---------------------------------------------------------------------------
@dataclass
class Edge:
    p: float | None          # 승률(Wilson 하한 적용 후)
    b: float | None          # 손익비 = 평균수익 / |평균손실|
    n: int                   # 표본 수
    kelly: float | None      # 풀 켈리(위험 비율)
    half_kelly: float | None
    risk: float              # 최종 적용 위험 비율(상한·대체값 반영)
    source: str              # 산출 근거


def wilson_lower(p_hat: float, n: int, z: float = 1.0) -> float:
    """승률의 Wilson 하한(z=1.0 ≈ 단측 84%). 표본이 적을수록 승률을 보수적으로 낮춤."""
    if n == 0:
        return 0.0
    d = 1 + z * z / n
    c = p_hat + z * z / (2 * n)
    m = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return (c - m) / d


def edge_from_returns(returns: pd.Series, source: str = "백테스트") -> Edge:
    r = pd.Series(returns).dropna()
    n = len(r)
    wins, losses = r[r > 0], r[r <= 0]
    avg_loss = losses.mean() if len(losses) else 0.0
    # 손실이 없거나(분모 0) 표본 부족 → 켈리 계산 불가, 고정 위험 사용
    if n < MIN_SAMPLES or avg_loss >= 0 or not len(wins):
        why = f"표본 {n}건 < {MIN_SAMPLES}" if n < MIN_SAMPLES else "손익 분포 불충분"
        return Edge(None, None, n, None, None, FALLBACK_RISK, f"{source}: {why} → 고정 위험 {FALLBACK_RISK:.0%}")
    p = wilson_lower(len(wins) / n, n)
    b = float(wins.mean() / abs(avg_loss))
    return kelly_edge(p, b, n, source)


def kelly_edge(p: float, b: float, n: int = 0, source: str = "가정") -> Edge:
    p, b = float(p), float(b)
    k = p - (1 - p) / b
    half = k / 2
    if half <= 0:
        risk, note = 0.0, "기대값 ≤ 0 → 매수 금지"
    elif half > MAX_RISK_PER_TRADE:
        risk, note = MAX_RISK_PER_TRADE, f"하프켈리 {half:.1%} > 상한 → {MAX_RISK_PER_TRADE:.0%}"
    else:
        risk, note = half, "하프켈리 적용"
    return Edge(round(p, 3), round(b, 2), n, round(k, 4), round(half, 4), round(risk, 4), f"{source}: {note}")


# ---------------------------------------------------------------------------
# 3. 매매 계획
# ---------------------------------------------------------------------------
@dataclass
class TradePlan:
    action: str                 # '지금 매수 가능' / '지정가 대기' / '관망'
    stage: str
    buy_low: float
    buy_high: float
    stop: float
    t1: float                   # 1차 익절(2R): 1/3 매도 후 손절을 본전으로 상향
    t2: float                   # 2차 익절(3R 또는 52주 고점 직전): 1/3 매도
    trail_rule: str             # 잔여 1/3 청산 규칙
    risk_pct: float             # 손절폭(매수 상단 기준)
    edge: Edge
    weight: float               # 계좌 대비 비중(최종)
    shares_now: int             # 이번에 매수할 수량
    shares_add: int             # 점화 확인 시 추가 수량(점화 대기 단계)
    add_trigger: float | None   # 추가 매수 트리거 가격
    notes: list[str] = field(default_factory=list)


def climax_signal(px: pd.DataFrame, entry_idx: int | None = None) -> list[str]:
    """보유 중 '강할 때 매도' 신호. 해당 시 잔여 물량의 절반 익절 권고."""
    c = px["Close"]
    sig = []
    ext = c.iloc[-1] / c.rolling(20).mean().iloc[-1] - 1
    if ext >= 0.25:
        sig.append(f"20일선 대비 +{ext:.0%} 이격(과열)")
    seg = c.iloc[entry_idx:] if entry_idx is not None else c.iloc[-30:]
    rets = seg.pct_change().dropna()
    if len(rets) >= 5 and rets.iloc[-1] == rets.max() and rets.iloc[-1] >= 0.10:
        sig.append(f"보유 기간 최대 상승일(+{rets.iloc[-1]:.0%})")
    if px["Volume"].iloc[-1] >= px["Volume"].iloc[-60:].max() and rets.iloc[-1] > 0:
        sig.append("60일 최대 거래량 동반 급등")
    return sig


def build_plan(px: pd.DataFrame, stage: str, edge: Edge, account: float,
               pivot: float | None = None, ignition_idx: int | None = None,
               accum_start_idx: int | None = None, market: str = "KR") -> TradePlan:
    """
    stage
    - '점화'                         : 피벗 돌파 완료(국내 점화 / 해외 VCP 돌파)
    - '매집 후기(점화 대기)'·'매집 진행': 국내 매집 단계 → 1/3 선진입
    - '돌파 대기'                    : 해외 VCP 형성 중 → 선진입 없이 피벗 Buy Stop 주문(미너비니 원칙)
    """
    c = float(px["Close"].iloc[-1])
    notes: list[str] = []
    zones = support_zones(px, pivot=pivot, ignition_idx=ignition_idx, accum_start_idx=accum_start_idx)
    add_trigger = None
    tranche = 1.0

    # ---- (1) 매수 구간 ----
    if stage == "점화" or (pivot and c > pivot and ignition_idx is not None):
        lo, hi = pivot, pivot * (1 + CHASE_LIMIT)
        if c > hi:
            # 이미 늘어남: 첫 눌림(가장 가까운 지지)에서 지정가 대기
            near = zones[0].price if zones else pivot
            lo, hi = near * 0.99, near * 1.01  # 지지선 ±1% 에 지정가
            action = "지정가 대기"
            notes.append(f"피벗+5% 초과(현재 {c / pivot - 1:+.1%}) → 추격 금지, 첫 눌림 대기")
        elif c < pivot:
            action = "관망"
            notes.append("피벗 하회 마감: 돌파 실패 여부 확인 전 관망")
        else:
            action = "지금 매수 가능"
    elif stage == "돌파 대기" and pivot:
        # 미너비니: 피벗 돌파 '당일'에만 매수. 피벗~+5% 구간에 Buy Stop(조건부 지정가) 주문을 걸어 둠
        lo, hi = pivot, pivot * (1 + CHASE_LIMIT)
        action = "돌파 대기(Buy Stop)"
        notes.append("피벗 돌파 + 거래량 50일 평균 200% 이상일 때만 체결 유효(장 마감 후 거래량 확인)")
    elif stage in ("매집 후기(점화 대기)", "매집 진행"):
        # 박스 상단 근처 추격을 피하고 하단 쪽에서 분할 매수: [현재가 -3% ~ 현재가], 박스하단 위로 제한
        box_low = float(px["Low"].iloc[-20:].min())
        lo, hi = max(c * 0.97, box_low * 1.01), c
        tranche = 1 / 3  # 분할 진입: 1/3 선진입, 2/3 는 점화 시
        add_trigger = pivot if pivot else float(px["High"].iloc[-21:-1].max())
        action = "지금 매수 가능" if stage == "매집 후기(점화 대기)" else "관망"
        if stage == "매집 진행":
            notes.append("매집 진행 단계: 변동성 축소(점화 대기) 전환 시 1차 진입")
    else:
        return _empty_plan(stage, edge, ["매집/점화 단계 아님"])

    # ---- (2) 손절: 매수 하단 아래 가장 가까운 '강한 지지' -1%, 없으면 가장 가까운 지지 -1% ----
    below = [z for z in zones if z.low < lo * 0.999]
    strong = [z for z in below if z.strength >= 2]
    base = (strong or below or [Zone(lo * 0.95, ["기본 -5%"], 1, lo * 0.95)])[0]
    stop = base.low * 0.99
    if (hi - stop) / hi > MAX_STOP:
        stop = hi * (1 - MAX_STOP)
        notes.append(f"지지선이 멀어 매수 상단 대비 -{MAX_STOP:.0%} 고정 손절")
    else:
        notes.append(f"손절 근거: {'+'.join(base.sources)}")
    stop = min(stop, lo * 0.99)  # 손절가는 반드시 매수 하단 아래
    risk_ps = hi - stop  # 1주당 위험(최악 체결가 기준)
    risk_pct = risk_ps / hi

    # ---- (3) 매도 구간: 1R 단위 분할 익절 + 저항 반영 ----
    t1 = hi + 2 * risk_ps
    t2 = hi + 3 * risk_ps
    hi52 = float(px["High"].iloc[-252:].max())
    if t1 < hi52 * 0.99 < t2:
        t2 = hi52 * 0.99
        notes.append(f"52주 고점 {hi52:,.0f} 매물 저항 → 2차 목표 하향")
    trail = "잔여 1/3: 20일선을 대량거래 동반 종가 이탈 시 전량 / 클라이맥스 신호 시 절반 선익절"
    climax = climax_signal(px)
    if len(climax) >= 2:  # 단일 신호는 정상 돌파일에도 흔하므로 2개 이상일 때만 경고
        notes.append("클라이맥스 신호(보유자 매도 검토): " + ", ".join(climax))

    # ---- (4) 하프 켈리 사이징 ----
    if edge.risk <= 0:
        action = "관망"
        notes.append("기대값 ≤ 0: 매수 금지")
    raw_weight = edge.risk / risk_pct if risk_pct > 0 else 0.0
    weight = min(raw_weight, MAX_WEIGHT)
    if raw_weight > MAX_WEIGHT:
        notes.append(f"비중 상한 {MAX_WEIGHT:.0%} 적용(손절폭이 좁아 켈리 비중 {raw_weight:.0%} 산출)")
    total_shares = int(account * weight / hi) if hi > 0 else 0
    shares_now = int(total_shares * tranche)
    shares_add = total_shares - shares_now if tranche < 1 else 0
    if action == "관망":
        shares_now = 0

    return TradePlan(
        action, stage, to_tick(lo, market=market), to_tick(hi, market=market), to_tick(stop, market=market),
        to_tick(t1, market=market), to_tick(t2, market=market), trail,
        round(risk_pct, 4), edge, round(weight, 4), shares_now, shares_add,
        to_tick(add_trigger, "up", market) if add_trigger else None, notes,
    )


def _empty_plan(stage: str, edge: Edge, notes: list[str]) -> TradePlan:
    nan = float("nan")
    return TradePlan("관망", stage, nan, nan, nan, nan, nan, "", nan, edge, 0.0, 0, 0, None, notes)


def portfolio_heat(plans: list[TradePlan], max_heat: float = 0.06) -> list[str]:
    """동시 보유 시 총 위험(Σ 비중×손절폭)이 계좌의 6%를 넘지 않도록 경고. 국내 테마 동조화 대비."""
    heat = sum(p.weight * p.risk_pct for p in plans if p.action != "관망" and p.risk_pct == p.risk_pct)
    return [] if heat <= max_heat else [f"총 위험 {heat:.1%} > {max_heat:.0%}: 점수 하위 종목부터 제외 권장"]
