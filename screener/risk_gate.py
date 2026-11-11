"""
포트폴리오 리스크 게이트: 후보를 점수 순으로 '체결됐다고 가정하고' 하나씩 쌓으면서 한도를 넘는 종목의 신규 진입을 막습니다.

trader-risk 의 원칙을 스윙 매매 계획에 맞게 옮겼습니다.
- 개별로는 괜찮아도 '함께' 보유하면 한도를 넘는 조합을 잡아냅니다(누적 판정).
- 차단은 최종입니다. 차단된 종목은 매수 구간·손절가는 남기되(감시용) 이번 수량은 0 입니다.
- 이미 보유 중인 위험(held_heat)을 먼저 깔고 시작할 수 있습니다(매매일지의 미청산 포지션).

검사 순서 (먼저 걸린 사유 하나만 기록)
1) 최대 동시 보유 종목 수   max_positions
2) 동일 업종·섹터 집중      max_per_group  (국내 테마 동조화 대비, 업종 미상은 제외)
3) 포트폴리오 총 위험(Heat)  Σ(비중 × 손절폭) ≤ max_heat
"""
from __future__ import annotations

from dataclasses import dataclass, field

from trade_plan import TradePlan, block_entry


@dataclass
class GateLimits:
    max_heat: float = 0.06       # 동시 보유 총 위험 6%(손절 동시 발생 시 계좌 손실 상한)
    max_positions: int = 6       # 신규 + 기존 보유 합산
    max_per_group: int = 2       # 같은 업종/섹터 최대 종목 수
    held_heat: float = 0.0       # 이미 보유 중인 포지션의 위험 합계
    held_positions: int = 0
    held_groups: dict[str, int] = field(default_factory=dict)


@dataclass
class Candidate:
    code: str
    plan: TradePlan
    score: float                 # 높을수록 우선(해외 RS, 국내 매집 점수)
    group: str | None = None     # 업종/섹터(미상이면 None → 집중 한도 미적용)


def plan_heat(p: TradePlan) -> float:
    """종목 하나가 손절될 때의 계좌 손실 비율 = 비중 × 손절폭."""
    if p.risk_pct != p.risk_pct:  # NaN
        return 0.0
    return float(p.weight) * float(p.risk_pct)


def is_entry(p: TradePlan) -> bool:
    return p.action != "관망" and p.shares_now > 0


def apply_gate(cands: list[Candidate], limits: GateLimits | None = None) -> dict:
    """
    후보 목록을 제자리에서 수정(차단 종목 → 관망)하고 요약을 돌려줍니다.
    반환: {"heatUsed": 0.052, "heatLimit": 0.06, "passed": 4, "gated": 2, "positions": 4}
    """
    lim = limits or GateLimits()
    heat = lim.held_heat
    positions = lim.held_positions
    groups = dict(lim.held_groups)
    passed = gated = 0

    for c in sorted(cands, key=lambda x: x.score, reverse=True):
        p = c.plan
        if not is_entry(p):
            continue
        h = plan_heat(p)
        reason = None
        if positions + 1 > lim.max_positions:
            reason = f"동시 보유 {lim.max_positions}종목 한도"
        elif c.group and groups.get(c.group, 0) + 1 > lim.max_per_group:
            reason = f"'{c.group}' {lim.max_per_group}종목 집중 한도"
        elif heat + h > lim.max_heat + 1e-9:
            reason = f"총 위험 {heat + h:.1%} > {lim.max_heat:.0%}"
        if reason:
            block_entry(p, "gate", f"리스크 게이트: {reason} → 신규 진입 보류")
            gated += 1
            continue
        heat += h
        positions += 1
        if c.group:
            groups[c.group] = groups.get(c.group, 0) + 1
        passed += 1

    return {"heatUsed": round(heat, 4), "heatLimit": lim.max_heat, "passed": passed,
            "gated": gated, "positions": positions}
