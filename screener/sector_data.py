"""
섹터·테마 레이더 데이터 수집 + 실행 + JSON 내보내기.

- 국내: pykrx 전 종목 일별 시세(거래대금·등락률) + KRX 업종 분류, 거래대금 급증 종목 뉴스(Google News RSS)
- 해외: yfinance 섹터/테마 ETF
- 결과: output/sectors_{kr,us}.json (웹앱 [섹터] 탭이 읽음)

실행: python cli.py sectors kr|us [--out 폴더] [--no-news]
"""
from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

import sector_radar as sr

NEWS_TOP_N = 30          # 뉴스 조회 대상: 거래대금 급증 상위 N 종목
MIN_VALUE_KR = 50e8      # 급증 종목 최소 거래대금 50억(초소형 잡음 제거)


# ---------------------------------------------------------------------------
# 국내 데이터
# ---------------------------------------------------------------------------
def _kr_dates(n: int) -> list[str]:
    """최근 n 영업일(YYYYMMDD). KOSPI 지수 일봉의 날짜 = 실제 거래일."""
    from pykrx import stock
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=n * 2 + 20)).strftime("%Y%m%d")
    idx = stock.get_index_ohlcv(start, end, "1001").index
    return [d.strftime("%Y%m%d") for d in idx[-n:]]


def load_kr_daily(lookback: int = 20) -> tuple[pd.DataFrame, dict[str, str]]:
    """최근 lookback+1 영업일 전 종목 시세(long) + 종목→업종 매핑."""
    from pykrx import stock
    dates = _kr_dates(lookback + 1)
    today = dates[-1]

    sector_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        sc = stock.get_market_sector_classifications(today, mkt)   # 종목명, 업종명, 종가, 대비, 등락률, 시가총액
        for code, row in sc.iterrows():
            sector_map[str(code)] = f"{row['업종명']}" + ("" if mkt == "KOSPI" else "(코스닥)")
            name_map[str(code)] = str(row["종목명"])

    frames = []
    for i, d in enumerate(dates, 1):
        o = stock.get_market_ohlcv(d, market="ALL")                # 종가, 거래량, 거래대금, 등락률 ...
        o = o[["거래대금", "등락률"]].rename(columns={"거래대금": "value", "등락률": "change"})
        o["date"] = d
        o["code"] = o.index.astype(str)
        frames.append(o)
        time.sleep(0.2)
        if i % 5 == 0:
            print(f"  ... 일별 시세 {i}/{len(dates)}")
    daily = pd.concat(frames, ignore_index=True)
    daily["sector"] = daily["code"].map(sector_map)
    daily["name"] = daily["code"].map(name_map).fillna(daily["code"])
    return daily, sector_map


def kr_surge(daily: pd.DataFrame, top_n: int = NEWS_TOP_N) -> pd.DataFrame:
    """오늘 거래대금 / 직전 20일 평균 배수 상위 종목(최소 거래대금 50억)."""
    today = daily["date"].max()
    piv = daily.pivot_table(index="code", columns="date", values="value", aggfunc="sum")
    avg = piv.drop(columns=[today]).mean(axis=1)
    t = daily[daily["date"] == today].set_index("code")
    t = t[t["value"] >= MIN_VALUE_KR].copy()
    t["value_ratio"] = (t["value"] / avg.reindex(t.index)).replace([np.inf, -np.inf], np.nan)
    t = t.dropna(subset=["value_ratio"]).sort_values("value_ratio", ascending=False).head(top_n)
    return t.reset_index()[["code", "name", "change", "value", "value_ratio"]]


def fetch_headlines(name: str, days: int = 3, limit: int = 15) -> list[str]:
    """Google News RSS(한국어) 최근 n일 헤드라인. 실패 시 빈 목록(배치는 계속)."""
    q = quote(f'"{name}" when:{days}d')   # 정확히 일치하는 종목명 + 최근 n일
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (cockpit personal screener)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        titles = [i.findtext("title") or "" for i in root.iter("item")]
        return [t.rsplit(" - ", 1)[0] for t in titles[:limit]]   # 끝의 ' - 언론사' 제거
    except Exception as e:
        print(f"  ! 뉴스 조회 실패({name}): {e}")
        return []


def run_kr(out_dir: Path, with_news: bool = True) -> Path:
    print("[섹터 1/3] 국내 일별 시세·업종 수집")
    daily, sector_map = load_kr_daily()
    print("[섹터 2/3] 업종별 거래대금 쏠림 계산")
    sectors = sr.sector_flow(daily)

    themes_df = pd.DataFrame()
    if with_news:
        print(f"[섹터 3/3] 거래대금 급증 상위 {NEWS_TOP_N}종목 뉴스 → 테마 분류")
        surge = kr_surge(daily)
        heads = {}
        for s in surge.itertuples():
            heads[str(s.code)] = fetch_headlines(str(s.name))
            time.sleep(0.5)
        themes_df = sr.theme_flow(surge, heads, sr.load_themes(out_dir / "themes.json"))
    return export_sectors("kr", sectors, themes_df, sector_map, out_dir)


# ---------------------------------------------------------------------------
# 해외 데이터
# ---------------------------------------------------------------------------
def run_us(out_dir: Path) -> Path:
    import yfinance as yf
    names = {**sr.US_SECTOR_ETFS, **sr.US_THEME_ETFS}
    tickers = list(names) + ["SPY"]
    print(f"[섹터] 해외 섹터·테마 ETF {len(names)}개 수집")
    px = yf.download(tickers, period="6mo", auto_adjust=True, group_by="ticker", progress=False)
    frames = {}
    for t in tickers:
        try:
            df = px[t].dropna()
        except KeyError:
            df = pd.DataFrame()
        if df.empty:  # 병렬 다운로드 실패분 순차 재시도
            try:
                df = yf.Ticker(t).history(period="6mo", auto_adjust=True)[["Close", "Volume"]].dropna()
            except Exception:
                df = pd.DataFrame()
        if not df.empty:
            frames[t] = df
    if len(frames) <= 1:
        raise RuntimeError("ETF 가격 데이터를 받지 못했습니다. 네트워크 또는 Yahoo 접속 상태를 확인하세요.")
    bench = frames.pop("SPY", None)
    sectors = sr.etf_flow(frames, names, bench)
    return export_sectors("us", sectors, pd.DataFrame(), {}, out_dir)


# ---------------------------------------------------------------------------
# 내보내기
# ---------------------------------------------------------------------------
def _clean(v):
    """JSON 표준 값으로 변환(NaN/inf → None, numpy → 파이썬)."""
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (np.floating, float)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def export_sectors(market: str, sectors: pd.DataFrame, themes: pd.DataFrame,
                   code_sector: dict[str, str], out_dir: Path) -> Path:
    """
    sectors_{market}.json
    - hotCodes: 상위 3개 섹터(점수 순, 이탈 제외) 소속 종목 + 상위 3개 테마 종목 → 웹 계획표 '주도' 배지용
    """
    top_secs = [s for s, f in zip(sectors["sector"], sectors["flag"]) if f != "이탈"][:3] if not sectors.empty else []
    hot: dict[str, str] = {}
    if market == "kr":
        for code, sec in code_sector.items():
            if sec in top_secs:
                hot[code] = f"주도 섹터: {sec}"
    if not themes.empty:
        for t in themes.head(3).itertuples():
            for m in t.members:
                hot[m["code"]] = f"주도 테마: {t.theme}"

    cols = ["sector", "ticker", "share", "avg_share", "shift", "ratio", "share_trend", "change", "breadth", "stocks",
            "value", "r1w", "r1m", "rs_1m", "score", "flag", "leaders"]
    payload = {
        "market": market.upper(),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sectors": [{k: (None if (market == "us" and k == "share") else r.get(k)) for k in cols if k in r}
                    for r in sectors.to_dict(orient="records")],
        "themes": themes.to_dict(orient="records") if not themes.empty else [],
        "hotCodes": hot,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sectors_{market}.json"
    path.write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
