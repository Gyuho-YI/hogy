"""
해외 검사 대상(유니버스): S&P 1500(대형 500 + 중형 400 + 소형 600) + 나스닥100 ≈ 1,550종목.

- 구성 종목은 지수 변경(편입·편출)이 잦으므로 실행 시 위키백과 구성 종목 표에서 자동 수집
- 실패 대비 3단 폴백: ① 실시간 수집 → ② 직전 성공 캐시(output/us_universe_cache.json) → ③ 내장 기본 목록(130종목)
- 사용자가 output/us_universe.txt 를 두면 그 목록이 최우선(cli.py)
"""
from __future__ import annotations

import io
import json
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

SOURCES = {
    "S&P500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "S&P400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "S&P600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    "NASDAQ100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}
MIN_EXPECTED = 1_200          # 이보다 적게 모이면 수집 실패로 간주(표 구조 변경 등)
CACHE_NAME = "us_universe_cache.json"
_TICKER = re.compile(r"^[A-Z][A-Z0-9\-]{0,6}$")
_UA = {"User-Agent": "Mozilla/5.0 (cockpit personal screener; contact: local)"}


def normalize(sym: str) -> str | None:
    """위키백과 표기(BRK.B) → yfinance 표기(BRK-B). 형식이 이상하면 None."""
    s = str(sym).strip().upper().replace(".", "-").split()[0] if str(sym).strip() else ""
    return s if _TICKER.match(s) else None


def parse_symbols(html: str) -> list[str]:
    """페이지 내 표 중 'Symbol' 또는 'Ticker' 열이 있는 첫 표의 종목 코드."""
    for t in pd.read_html(io.StringIO(html)):
        cols = {str(c).strip().lower(): c for c in t.columns}
        key = cols.get("symbol") or cols.get("ticker") or cols.get("ticker symbol")
        if key is not None and len(t) >= 50:
            out = [normalize(x) for x in t[key].tolist()]
            return [x for x in out if x]
    return []


def fetch_live(timeout: int = 20) -> tuple[list[str], dict[str, int]]:
    """4개 지수 구성 종목 실시간 수집. 실패한 지수는 0으로 기록하고 계속."""
    tickers: list[str] = []
    counts: dict[str, int] = {}
    for name, url in SOURCES.items():
        try:
            r = requests.get(url, headers=_UA, timeout=timeout)
            r.raise_for_status()
            syms = parse_symbols(r.text)
        except Exception as e:  # 네트워크·표 구조 변경
            print(f"  ! {name} 구성 종목 수집 실패: {type(e).__name__}")
            syms = []
        counts[name] = len(syms)
        tickers.extend(syms)
    return list(dict.fromkeys(tickers)), counts       # 순서 유지 중복 제거


def load_universe(out_dir: Path, extras: list[str]) -> tuple[list[str], str]:
    """
    반환: (종목 목록, 출처 설명). extras(내장 성장주 목록)는 항상 합침.
    """
    cache = out_dir / CACHE_NAME
    live, counts = fetch_live()
    if len(live) >= MIN_EXPECTED:
        out_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"date": date.today().isoformat(), "counts": counts, "tickers": live},
                                    ensure_ascii=False), encoding="utf-8")
        src = "실시간(" + ", ".join(f"{k} {v}" for k, v in counts.items()) + ")"
        return list(dict.fromkeys(live + extras)), src
    if cache.exists():
        try:
            c = json.loads(cache.read_text(encoding="utf-8"))
            age = (date.today() - datetime.fromisoformat(c["date"]).date()).days
            print(f"  구성 종목 실시간 수집 실패 → 캐시 사용({c['date']}, {age}일 전)")
            return list(dict.fromkeys(c["tickers"] + extras)), f"캐시({c['date']})"
        except (ValueError, KeyError, OSError) as e:
            print(f"  ! 캐시 읽기 실패: {e}")
    print("  구성 종목 수집·캐시 모두 실패 → 내장 기본 목록 사용")
    return list(extras), "내장 기본 목록"
