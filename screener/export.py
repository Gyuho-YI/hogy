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
