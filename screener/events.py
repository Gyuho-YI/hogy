"""
실적 발표 이벤트 회피.

돌파 직후 실적 발표가 있으면 갭으로 손절선(-8%)을 뚫고 체결될 위험이 큽니다(손절이 계획대로 작동하지 않음).
- 해외: yfinance 실적 일정 → 발표 D-5 영업일 이내면 신규 진입 보류(block)
- 국내: 사전 발표일 데이터가 공개 API 로 제공되지 않으므로, 잠정실적이 몰리는 '실적 시즌'에는 경고만 표시
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

EARNINGS_BLACKOUT_DAYS = 5   # 발표일까지 남은 영업일이 이 값 이하이면 신규 진입 보류

# 국내 잠정실적 공시가 몰리는 구간(분기 종료 후 약 3~6주, 정기보고서 법정 기한까지)
KR_EARNINGS_SEASONS = [((1, 20), (2, 15)), ((4, 15), (5, 15)), ((7, 15), (8, 14)), ((10, 15), (11, 14))]


def business_days_until(target: date, today: date | None = None) -> int:
    """오늘 → target 까지 남은 영업일 수(오늘 제외, 당일 = 0, 지난 날짜 = 음수)."""
    today = today or date.today()
    if target >= today:
        return int(np.busday_count(today, target))
    return -int(np.busday_count(target, today))


def _to_date(x) -> date | None:
    if x is None:
        return None
    try:
        ts = pd.Timestamp(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(ts):
        return None
    return ts.tz_localize(None).date() if ts.tzinfo else ts.date()


def next_earnings_date(tk, today: date | None = None) -> date | None:
    """
    yfinance Ticker → 오늘 이후 가장 가까운 실적 발표일. 조회 실패/미정이면 None.
    버전에 따라 calendar 가 dict(신) 또는 DataFrame(구)이므로 둘 다 처리합니다.
    """
    today = today or date.today()
    cands: list[date] = []
    try:
        cal = tk.calendar
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date") or []
            raw = raw if isinstance(raw, (list, tuple)) else [raw]
            cands += [d for d in (_to_date(r) for r in raw) if d]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if "Earnings Date" in cal.index:
                cands += [d for d in (_to_date(v) for v in cal.loc["Earnings Date"].tolist()) if d]
    except Exception:
        pass
    if not cands:
        try:
            ed = tk.get_earnings_dates(limit=8)
            if ed is not None and len(ed):
                cands += [d for d in (_to_date(i) for i in ed.index) if d]
        except Exception:
            pass
    upcoming = sorted(d for d in cands if d >= today)
    return upcoming[0] if upcoming else None


def earnings_block(days_left: int | None) -> bool:
    """발표가 오늘~D-5 영업일 이내인가(이미 지난 발표는 해당 없음)."""
    return days_left is not None and 0 <= days_left <= EARNINGS_BLACKOUT_DAYS


def kr_earnings_season(today: date | None = None) -> bool:
    today = today or date.today()
    md = (today.month, today.day)
    return any(start <= md <= end for start, end in KR_EARNINGS_SEASONS)


def today_kst() -> date:
    return datetime.now().date()
