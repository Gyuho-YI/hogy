"""
웹앱 연동용 JSON 내보내기.

- 결과를 output/latest_{market}.json 과 output/{market}_{YYYYMMDD}.json 으로 저장합니다.
- Spring Boot 등 웹 서버는 이 파일만 읽으면 되므로 Python(스크리닝)과 Java(서비스)가 분리됩니다.
- NaN/Infinity 는 JSON 표준이 아니므로 null 로 변환합니다(Jackson 파싱 오류 방지).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "output"


def export_json(df: pd.DataFrame, market: str) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    finite = df.replace([np.inf, -np.inf], np.nan)
    clean = finite.astype(object).where(finite.notna(), None)
    payload = {
        "market": market.upper(),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "count": len(clean),
        "items": clean.to_dict(orient="records"),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    latest = OUT_DIR / f"latest_{market}.json"
    latest.write_text(text, encoding="utf-8")
    (OUT_DIR / f"{market}_{datetime.now():%Y%m%d}.json").write_text(text, encoding="utf-8")
    return latest


# ---------------------------------------------------------------------------
# 웹앱 표준 스키마: 국내·해외 공통 영문 키 (Spring Boot DTO 와 1:1 대응)
# ---------------------------------------------------------------------------
def _num(x):
    """NaN/inf/None → None, numpy 숫자 → float."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def plan_record(code: str, name: str, stage: str, plan, px: pd.DataFrame, history_days: int = 120) -> dict:
    """TradePlan + 최근 종가 이력 → 웹앱용 레코드."""
    hist = px["Close"].iloc[-history_days:]
    return {
        "code": str(code), "name": str(name), "stage": stage, "action": plan.action,
        "close": _num(px["Close"].iloc[-1]),
        "buyLow": _num(plan.buy_low), "buyHigh": _num(plan.buy_high),
        "stop": _num(plan.stop), "riskPct": _num(plan.risk_pct),
        "t1": _num(plan.t1), "t2": _num(plan.t2), "addTrigger": _num(plan.add_trigger),
        "weightPct": _num(plan.weight * 100), "sharesNow": int(plan.shares_now), "sharesAdd": int(plan.shares_add),
        "edgeSource": plan.edge.source, "notes": list(plan.notes),
        "history": [{"d": d.strftime("%Y-%m-%d"), "c": _num(c)} for d, c in hist.items()],
    }


def export_plans(market: str, records: list[dict], account: float) -> Path:
    """웹앱이 읽는 output/plans_{market}.json 저장."""
    OUT_DIR.mkdir(exist_ok=True)
    payload = {
        "market": market.upper(),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "account": account,
        "items": records,
    }
    path = OUT_DIR / f"plans_{market}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
