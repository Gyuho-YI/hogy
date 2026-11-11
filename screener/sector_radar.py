"""
섹터·테마 레이더: '돈이 어디로 몰리는가'를 거래대금과 뉴스로 판별하는 순수 계산 모듈(데이터 수집과 분리).

국내(KR)
- 섹터 쏠림: 업종별 거래대금 '시장 내 비중'이 직전 20일 평균 비중 대비 몇 배인가(쏠림 배수)
  → 시장 전체 거래대금이 늘거나 줄어도 왜곡되지 않도록 '금액'이 아닌 '비중'으로 비교
- 확산도: 섹터 내 상승 종목 비율(대장주 1개만 오르는 섹터 vs 섹터 전체가 오르는 섹터 구분)
- 테마: 거래대금 급증 종목의 최근 뉴스 헤드라인 → 테마 키워드 매칭 → 테마별 집계

해외(US)
- 섹터/테마 ETF 의 달러 거래대금 배수(오늘 / 20일 평균), 1주·1개월 수익률, SPY 대비 상대강도(RS)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 테마 사전: 헤드라인에 키워드가 하나라도 있으면 해당 테마로 분류(대소문자 무시)
# output 폴더의 themes.json 으로 덮어쓰기/추가 가능 → load_themes()
# ---------------------------------------------------------------------------
DEFAULT_THEMES: dict[str, list[str]] = {
    "반도체·HBM": ["반도체", "HBM", "파운드리", "D램", "낸드", "웨이퍼", "후공정", "CXL"],
    "AI·데이터센터": ["AI", "인공지능", "데이터센터", "엔비디아", "GPU", "LLM", "생성형"],
    "전력기기·전력망": ["변압기", "전력기기", "전력망", "송배전", "전선", "ESS", "초고압"],
    "원전·SMR": ["원전", "원자력", "SMR", "소형모듈원자로", "우라늄"],
    "방산": ["방산", "K방산", "무기", "탄약", "미사일", "K9", "전차", "국방"],
    "조선·해운": ["조선", "선박", "LNG선", "수주", "해운", "컨테이너선", "MRO"],
    "2차전지": ["2차전지", "이차전지", "배터리", "양극재", "음극재", "리튬", "전고체", "전해질"],
    "바이오·제약": ["바이오", "신약", "임상", "제약", "FDA", "기술수출", "항체", "비만치료제"],
    "로봇": ["로봇", "휴머노이드", "협동로봇", "자율주행로봇"],
    "자동차": ["자동차", "현대차", "전기차", "완성차", "자율주행"],
    "K뷰티·화장품": ["화장품", "K뷰티", "뷰티", "ODM"],
    "엔터·K컬처": ["엔터", "K팝", "콘서트", "드라마", "웹툰", "아이돌"],
    "우주항공": ["우주", "위성", "발사체", "항공우주", "UAM", "드론"],
    "양자": ["양자", "양자컴퓨터", "양자암호"],
    "가상자산·STO": ["비트코인", "가상자산", "코인", "STO", "스테이블코인", "블록체인"],
    "건설·재건": ["재건", "건설", "인프라", "재개발", "우크라이나"],
    "게임": ["게임", "신작", "MMORPG"],
    "철강·비철": ["철강", "구리", "비철", "알루미늄", "고려아연"],
    "금융·밸류업": ["밸류업", "자사주", "배당", "증권", "은행", "지주사"],
}

# 해외 섹터/테마 ETF → 한글명
US_SECTOR_ETFS: dict[str, str] = {
    "XLK": "기술", "XLC": "커뮤니케이션", "XLY": "경기소비재", "XLP": "필수소비재",
    "XLF": "금융", "XLV": "헬스케어", "XLI": "산업재", "XLE": "에너지",
    "XLB": "소재", "XLU": "유틸리티", "XLRE": "리츠",
}
US_THEME_ETFS: dict[str, str] = {
    "SMH": "반도체", "IGV": "소프트웨어", "CIBR": "사이버보안", "BOTZ": "로봇·AI",
    "ITA": "방산·항공", "URA": "우라늄·원전", "GRID": "전력망", "TAN": "태양광",
    "LIT": "2차전지", "XBI": "바이오", "PAVE": "인프라", "UFO": "우주",
    "IBIT": "비트코인", "GDX": "금광", "COPX": "구리", "KWEB": "중국 인터넷",
}


def load_themes(path: Path | None) -> dict[str, list[str]]:
    """themes.json 이 있으면 기본 사전에 병합(같은 테마명은 덮어씀)."""
    themes = dict(DEFAULT_THEMES)
    if path and path.exists():
        try:
            custom = json.loads(path.read_text(encoding="utf-8"))
            themes.update({k: list(v) for k, v in custom.items() if isinstance(v, list)})
        except (ValueError, OSError) as e:
            print(f"  ! themes.json 읽기 실패(기본 사전 사용): {e}")
    return themes


def _ratio(a: float, b: float) -> float | None:
    """a / b. 분모 0·음수·결측이면 None(0 나누기 방지)."""
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b) or b <= 0:
        return None
    return a / b


# ---------------------------------------------------------------------------
# 1. 국내 섹터 쏠림
# ---------------------------------------------------------------------------
def sector_flow(daily: pd.DataFrame, lookback: int = 20, top_leaders: int = 3) -> pd.DataFrame:
    """
    daily: 종목별 일별 데이터(long format)
      columns = date, code, name, sector, change(등락률 %), value(거래대금)
    반환: 섹터별 오늘 지표(점수 높은 순)
      share(오늘 비중), avg_share(직전 lookback 일 평균 비중), ratio(쏠림 배수), share_trend(최근 3일 비중 연속 증가),
      change(거래대금 가중 등락률), breadth(상승 종목 비율), score, flag, leaders
    """
    d = daily.dropna(subset=["sector", "value"]).copy()
    d = d[d["value"] > 0]
    dates = sorted(d["date"].unique())
    if len(dates) < 2:
        raise ValueError("최소 2영업일 데이터가 필요합니다")
    today = dates[-1]
    prev = dates[-(lookback + 1):-1]

    by = d.groupby(["date", "sector"])["value"].sum().unstack(fill_value=0.0)
    share = by.div(by.sum(axis=1), axis=0)             # 일자별 섹터 비중(합계 1)
    s_today = share.loc[today]
    s_avg = share.loc[prev].mean()
    last3 = share.iloc[-3:] if len(share) >= 3 else share

    t = d[d["date"] == today]
    rows = []
    for sec, g in t.groupby("sector"):
        w = g["value"] / g["value"].sum()
        leaders = g.sort_values("value", ascending=False).head(top_leaders)
        rows.append({
            "sector": sec,
            "share": float(s_today.get(sec, 0.0)),
            "avg_share": float(s_avg.get(sec, 0.0)),
            "ratio": _ratio(float(s_today.get(sec, 0.0)), float(s_avg.get(sec, 0.0))),
            "shift": float(s_today.get(sec, 0.0) - s_avg.get(sec, 0.0)),   # 비중 증가폭(%p/100)
            "share_trend": bool(sec in last3 and last3[sec].is_monotonic_increasing and len(last3) >= 3),
            "change": float((g["change"] * w).sum()),
            "breadth": float((g["change"] > 0).mean()),
            "stocks": int(len(g)),
            "value": float(g["value"].sum()),
            "leaders": [{"code": str(r.code), "name": str(r.name), "change": float(r.change), "value": float(r.value)}
                        for r in leaders.itertuples()],
        })
    out = pd.DataFrame(rows)
    out = _score(out, min_stocks=3)
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def _score(df: pd.DataFrame, min_stocks: int = 1) -> pd.DataFrame:
    """
    점수(0~100) = 쏠림 배수 45% + 비중 증가폭(국내)/상대강도(해외) 순위 25% + 확산도 20% + 등락률 순위 10%
    - 쏠림 배수는 순위가 아닌 '크기'로 반영: 0.5배 이하 0점 ~ 2.5배 이상 만점(3.4배와 1.2배가 순위 한 칸 차이로 뭉개지는 것 방지)
    - '비중 크기'가 아닌 '증가폭'을 쓰는 이유: 대형주가 많은 섹터(전기전자 등)가 평소 수준이어도 상위에 오르는 왜곡 방지
    - 종목 수가 너무 적은 섹터(1~2개)는 노이즈가 커서 감점
    """
    df = df.copy()
    r = df["ratio"].fillna(0)
    momentum = df["shift"] if "shift" in df else df["share"]
    ratio_pts = ((r - 0.5) / (2.5 - 0.5)).clip(0, 1)
    df["score"] = (ratio_pts * 45 + momentum.rank(pct=True) * 25
                   + df["breadth"].fillna(0) * 20 + df["change"].rank(pct=True) * 10)
    if "stocks" in df:
        df.loc[df["stocks"] < min_stocks, "score"] *= 0.6
    df["score"] = df["score"].round(1)
    df["flag"] = [_flag(x) for x in df.itertuples()]
    return df


def _flag(x) -> str:
    ratio = x.ratio if x.ratio is not None and not (isinstance(x.ratio, float) and math.isnan(x.ratio)) else 0
    if ratio >= 3 and x.change >= 5:
        return "과열"           # 돈과 가격이 동시에 급등 → 추격 주의
    if ratio >= 1.5 and getattr(x, "share_trend", False):
        return "신규 유입"       # 비중이 3일 연속 늘며 평소의 1.5배 이상
    if ratio >= 1.5:
        return "유입"
    if 0 < ratio < 0.7:
        return "이탈"
    return "보통"


# ---------------------------------------------------------------------------
# 2. 국내 테마(뉴스)
# ---------------------------------------------------------------------------
def match_themes(headlines: list[str], themes: dict[str, list[str]]) -> dict[str, int]:
    """헤드라인 목록에서 테마별 키워드 등장 헤드라인 수."""
    hits: dict[str, int] = {}
    for h in headlines:
        low = h.lower()
        for theme, kws in themes.items():
            if any(k.lower() in low for k in kws):
                hits[theme] = hits.get(theme, 0) + 1
    return hits


def theme_flow(surge: pd.DataFrame, headlines: dict[str, list[str]], themes: dict[str, list[str]],
               min_hits: int = 2) -> pd.DataFrame:
    """
    surge: 거래대금 급증 종목 columns = code, name, change, value, value_ratio(오늘/20일 평균)
    headlines: code → 최근 헤드라인 목록
    - 종목별로 헤드라인 min_hits 개 이상 언급된 테마(최대 2개)에 배정 → 테마별 합산
    - 테마 점수 = 소속 종목 거래대금 합(억) × 평균 거래대금 배수의 로그 → '돈 + 쏠림 강도' 동시 반영
    """
    rows = []
    for s in surge.itertuples():
        hits = match_themes(headlines.get(str(s.code), []), themes)
        top = [t for t, n in sorted(hits.items(), key=lambda kv: -kv[1]) if n >= min_hits][:2]
        for t in top:
            rows.append({"theme": t, "code": str(s.code), "name": str(s.name), "change": float(s.change),
                         "value": float(s.value), "value_ratio": float(s.value_ratio), "hits": hits[t],
                         "headline": next((h for h in headlines.get(str(s.code), [])
                                           if any(k.lower() in h.lower() for k in themes[t])), "")})
    if not rows:
        return pd.DataFrame(columns=["theme", "stocks", "value", "avg_ratio", "avg_change", "score", "members"])
    m = pd.DataFrame(rows)
    out = []
    for t, g in m.groupby("theme"):
        g = g.sort_values("value", ascending=False)
        avg_ratio = float(g["value_ratio"].mean())
        out.append({
            "theme": t, "stocks": int(len(g)), "value": float(g["value"].sum()),
            "avg_ratio": avg_ratio, "avg_change": float(g["change"].mean()),
            "score": round(math.log1p(g["value"].sum() / 1e8) * math.log1p(max(avg_ratio, 0)), 2),
            "members": [{"code": r.code, "name": r.name, "change": r.change, "value_ratio": r.value_ratio,
                         "headline": r.headline} for r in g.itertuples()],
        })
    return pd.DataFrame(out).sort_values("score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. 해외 ETF
# ---------------------------------------------------------------------------
def etf_flow(prices: dict[str, pd.DataFrame], names: dict[str, str], benchmark: pd.DataFrame | None,
             lookback: int = 20) -> pd.DataFrame:
    """
    prices: 티커 → 일봉(Close, Volume). 달러 거래대금 = Close × Volume
    - ratio: 오늘 거래대금 / 직전 lookback 일 평균
    - rs_1m: 1개월 수익률 - 벤치마크(SPY) 1개월 수익률(%p)
    - share/breadth 대신 추세(종가 > 50일선) 사용
    """
    bench_1m = None
    if benchmark is not None and len(benchmark) > 22:
        bench_1m = benchmark["Close"].iloc[-1] / benchmark["Close"].iloc[-22] - 1
    rows = []
    for t, df in prices.items():
        if df is None or len(df) < lookback + 2:
            continue
        dv = df["Close"] * df["Volume"]
        avg = dv.iloc[-(lookback + 1):-1].mean()
        c = df["Close"]
        r1w = c.iloc[-1] / c.iloc[-6] - 1
        r1m = c.iloc[-1] / c.iloc[-22] - 1 if len(c) > 22 else np.nan
        rows.append({
            "sector": f"{names.get(t, t)} ({t})", "ticker": t,
            "ratio": _ratio(float(dv.iloc[-1]), float(avg)),
            "share": float(dv.iloc[-1]), "change": float((c.iloc[-1] / c.iloc[-2] - 1) * 100),
            "r1w": float(r1w * 100), "r1m": float(r1m * 100) if np.isfinite(r1m) else None,
            "rs_1m": float((r1m - bench_1m) * 100) if bench_1m is not None and np.isfinite(r1m) else None,
            "breadth": float(c.iloc[-1] > c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else 0.0,
            "share_trend": bool(dv.iloc[-3:].is_monotonic_increasing),
            "stocks": 1, "value": float(dv.iloc[-1]), "leaders": [],
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    # 해외는 '비중' 대신 1개월 상대강도를 순위에 사용
    out["share"] = out["rs_1m"].fillna(out["r1w"])
    out = _score(out)
    return out.sort_values("score", ascending=False).reset_index(drop=True)
