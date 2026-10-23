"""
해외(미국) 주식 스크리너: 미너비니 트렌드 템플릿 + RS Rating + VCP + 펀더멘털(분기 YoY)

원본 스크립트 대비 개선 사항
- 검사 대상: S&P 1500 + 나스닥100(약 1,550종목, us_universe.py) → 유동성 필터(주가 $10↑, 거래대금 $20M↑)
- 가격 데이터를 200종목씩 일괄 수집 + 실패분 순차 재시도(Rate Limit·캐시 충돌 대응)
- 관찰 종목: 탈락 사유 + 감시 가격(돌파 감시선·50일선 이탈선)
- 트렌드 템플릿 7개 가격 조건 + RS Rating(유니버스 내 백분위) 반영
- 매출 YoY 를 분기 손익계산서(전년 동기 대비)로 직접 계산, 분모 0/음수 예외 처리
- 데이터 결측을 0 으로 덮지 않고 '계산불가'로 명시(조용한 탈락 방지)
- VCP 탐지 및 피벗 / 추격 금지 여부 출력

실행: pip install -r requirements.txt && python screener/us_screener.py
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

from common import detect_vcp, rs_rank, safe_yoy, trend_template
from export import export_plans, plan_record
from trade_plan import build_plan, edge_from_returns, portfolio_heat

MIN_REV_YOY = 0.20      # 매출 YoY 20% 이상
MAX_DEBT_EQUITY = 100   # 부채비율(D/E) 100% 이하 (금융업은 구조상 높으므로 별도 유니버스 권장)
MIN_RS = 70             # RS Rating 70 이상
MIN_PRICE = 10.0        # 유동성 필터: 주가 $10 이상(초저가주 제외)
MIN_DOLLAR_VOL = 20e6   # 유동성 필터: 50일 평균 거래대금 $2,000만 이상
MAX_FUNDAMENTAL = 250   # 재무 조회 상한(추세 통과가 많을 때 RS 상위부터) → 실행 시간·차단 위험 관리
MAX_WATCH = 60          # 화면에 내보낼 관찰 종목 상한(RS 상위부터)
CHUNK = 200             # 가격 일괄 다운로드 묶음 크기
MAX_SINGLE_RETRY = 40   # 개별 재시도 상한(대량 실패 시 시간 폭증 방지)


def weighted_return(close: pd.Series) -> float | None:
    """IBD 방식 가중 수익률: 최근 3개월 40%, 6/9/12개월 각 20%."""
    if len(close) < 253:
        return None
    c = close.iloc[-1]
    r = lambda n: c / close.iloc[-n] - 1  # noqa: E731
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def quarterly_revenue_yoy(tk: yf.Ticker):
    """최근 분기 매출 vs 전년 동기 매출. 실패 시 info['revenueGrowth'] 로 대체."""
    try:
        q = tk.quarterly_income_stmt
        if q is not None and "Total Revenue" in q.index and q.shape[1] >= 5:
            rev = q.loc["Total Revenue"]
            return safe_yoy(rev.iloc[0], rev.iloc[4])
    except Exception:
        pass
    g = tk.info.get("revenueGrowth")
    return safe_yoy(1 + g, 1) if g is not None else safe_yoy(None, None)


def _split(px: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """yf.download 결과(종목별 MultiIndex 또는 단일 종목 평면 컬럼) → 종목별 일봉."""
    out: dict[str, pd.DataFrame] = {}
    if px is None or px.empty:
        return out
    multi = isinstance(px.columns, pd.MultiIndex)
    for t in tickers:
        try:
            df = px[t] if multi else px
        except KeyError:
            continue
        df = df.dropna()
        if not df.empty and {"Close", "Volume"}.issubset(df.columns):
            out[t] = df
    return out


def load_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    약 1,550종목을 200개씩 나눠 일괄 다운로드 → 실패분은 순차 일괄 재시도 → 남은 소수만 개별 재시도.
    yfinance 병렬 다운로드는 내부 시간대 캐시(SQLite) 충돌로 'database is locked' 가 간헐 발생.
    """
    frames: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK):
        part = tickers[i:i + CHUNK]
        px = yf.download(part, period="2y", auto_adjust=True, group_by="ticker", progress=False, threads=True)
        frames.update(_split(px, part))
        print(f"  ... 가격 {min(i + CHUNK, len(tickers))}/{len(tickers)}")

    missing = [t for t in tickers if t not in frames]
    if missing:
        px = yf.download(missing, period="2y", auto_adjust=True, group_by="ticker", progress=False, threads=False)
        frames.update(_split(px, missing))
        missing = [t for t in tickers if t not in frames]
    for t in missing[:MAX_SINGLE_RETRY]:
        try:
            df = yf.Ticker(t).history(period="2y", auto_adjust=True)[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if not df.empty:
                frames[t] = df
                print(f"  재시도 성공: {t}")
        except Exception as e:
            print(f"  ! {t} 재시도 실패: {type(e).__name__}")
        time.sleep(0.3)
    print(f"  가격 수신 {len(frames)}/{len(tickers)}종목")
    return frames


def is_liquid(df: pd.DataFrame) -> bool:
    """주가 $10 이상 + 50일 평균 거래대금 $2,000만 이상."""
    if len(df) < 50:
        return False
    dv = (df["Close"] * df["Volume"]).iloc[-50:].mean()
    return float(df["Close"].iloc[-1]) >= MIN_PRICE and float(dv) >= MIN_DOLLAR_VOL


def watch_levels(df: pd.DataFrame) -> dict:
    """
    관찰 종목 감시 가격(매수 구간이 아님 → 수량 계산 없음).
    - 돌파 감시선: VCP 피벗이 있으면 피벗, 없으면 최근 30거래일 고점 → 거래량 동반 돌파 시 재검토
    - 이탈선: 50일선 → 종가 이탈 시 추세 훼손(관찰 제외 후보)
    """
    v = detect_vcp(df)
    breakout = float(v.pivot) if v.pivot else float(df["High"].iloc[-30:].max())
    exit_line = float(df["Close"].rolling(50).mean().iloc[-1])
    return {"watchBreakout": round(breakout, 2), "watchExit": round(exit_line, 2)}


WATCH_STAGE = "관찰(추세 통과)"


def _watch(df: pd.DataFrame, ticker: str, edge, account: float, reasons: list[str]) -> dict:
    """매수 조건 미달이지만 추세는 통과한 종목 → 화면에 '관찰'로 노출(탈락 사유 포함)."""
    p = build_plan(df, WATCH_STAGE, edge, account, market="US")   # 매수 구간 없음(관망)
    lv = watch_levels(df)
    c = float(df["Close"].iloc[-1])
    p.notes = reasons + [f"감시: {lv['watchBreakout']:,.2f} 돌파({lv['watchBreakout'] / c - 1:+.1%}) 시 재검토 · "
                         f"50일선 {lv['watchExit']:,.2f}({lv['watchExit'] / c - 1:+.1%}) 이탈 시 제외"]
    rec = plan_record(ticker, ticker, WATCH_STAGE, p, df)
    rec.update(lv)
    return rec


def screen(tickers: list[str], account: float = 10_000) -> tuple[pd.DataFrame, list[dict], dict]:
    """
    account: 계좌 평가금액(USD). 해외 전략 백테스트가 없으므로 고정 위험 1%로 사이징.
    반환: (상세 표, 웹 레코드, 단계별 통계)
    - 웹 레코드: 매수 후보(돌파 대기·점화) + 추세 통과 종목('관찰', 탈락 사유 포함) → 결과가 0건이어도 이유를 확인 가능
    """
    edge = edge_from_returns(pd.Series(dtype=float), "해외 백테스트 없음")
    plans, web = [], []
    stats = {"scanned": len(tickers), "received": 0, "liquid": 0, "trend": 0, "fundamental": 0, "setup": 0}
    print(f"[1/3] 가격 데이터 일괄 수집: {len(tickers)}종목")
    frames = load_prices(tickers)
    stats["received"] = len(frames)

    # --- [1] 기술적 필터 (펀더멘털 API 호출 전에 먼저 걸러 호출 수 최소화) ---
    if not frames:
        # 전부 실패 = 네트워크/차단 문제. 빈 결과로 덮어쓰지 않도록 예외로 중단(이전 계획 유지)
        raise RuntimeError("가격 데이터를 하나도 받지 못했습니다. 네트워크 또는 Yahoo 접속 상태를 확인하세요.")
    frames = {t: df for t, df in frames.items() if is_liquid(df)}
    stats["liquid"] = len(frames)
    print(f"  유동성 통과(주가 ${MIN_PRICE:.0f}↑, 거래대금 ${MIN_DOLLAR_VOL / 1e6:.0f}M↑): {len(frames)}종목")

    rows = []
    for t, df in frames.items():
        tt = trend_template(df)
        rows.append({"ticker": t, "df": df, "tt": tt, "wret": weighted_return(df["Close"])})

    if not rows:
        return pd.DataFrame(), [], stats
    base = pd.DataFrame(rows).dropna(subset=["wret"])
    if base.empty:
        return base, [], stats
    base["rs"] = rs_rank(base["wret"])
    stage1 = base[base["tt"].map(lambda x: x["pass"]) & (base["rs"] >= MIN_RS)]
    stats["trend"] = len(stage1)
    print(f"[2/3] 트렌드 템플릿 + RS>={MIN_RS} 통과: {len(stage1)}종목")

    # --- [2] 펀더멘털 필터 + VCP ---
    out = []
    watch_count = 0

    def add_watch(rec: dict) -> None:
        nonlocal watch_count
        if watch_count < MAX_WATCH:          # 화면 과밀 방지: RS 상위부터
            web.append(rec)
            watch_count += 1

    for n, (_, r) in enumerate(stage1.sort_values("rs", ascending=False).iterrows()):
        t, df = r["ticker"], r["df"]
        rs_note = f"RS {r['rs']:.0f} · 52주 고점 대비 {r['tt']['pct_from_high'] * 100:+.1f}%"
        if n >= MAX_FUNDAMENTAL:
            add_watch(_watch(df, t, edge, account, [rs_note, f"재무 조회 생략(RS 상위 {MAX_FUNDAMENTAL}종목 초과)"]))
            continue
        tk = yf.Ticker(t)
        try:
            g = quarterly_revenue_yoy(tk)
            de = tk.info.get("debtToEquity")
        except Exception as e:  # 통신 오류는 '관찰'로 남기고 계속
            print(f"  ! {t} 재무 조회 실패: {e}")
            add_watch(_watch(df, t, edge, account, [rs_note, "재무 데이터 조회 실패 → 펀더멘털 미확인"]))
            continue
        finally:
            time.sleep(0.3)  # 성공/실패 무관하게 딜레이 적용

        fails = []
        if g.rate is None:
            fails.append("매출 성장률 계산불가")
        elif g.rate < MIN_REV_YOY:
            fails.append(f"매출 YoY {g.rate * 100:.0f}% < {MIN_REV_YOY * 100:.0f}%")
        if de is not None and de > MAX_DEBT_EQUITY:
            fails.append(f"부채비율 {de:.0f}% > {MAX_DEBT_EQUITY}%")
        if fails:
            add_watch(_watch(df, t, edge, account, [rs_note, "펀더멘털 미달: " + ", ".join(fails)]))
            continue
        stats["fundamental"] += 1

        v = detect_vcp(df)
        # 매매 계획: 돌파 당일/돌파 후 → '점화', VCP 형성 중 → '돌파 대기'(Buy Stop), 그 외 → 관찰
        close = float(df["Close"].iloc[-1])
        if v.pivot and close > v.pivot:
            stage = "점화"
        elif v.is_vcp:
            stage = "돌파 대기"
        else:
            stage = "추세만 충족"
        p = build_plan(df, stage, edge, account, pivot=v.pivot, market="US")
        plans.append(p)
        if stage == "추세만 충족":
            shrink = " → ".join(f"{c * 100:.0f}%" for c in v.contractions)
            vcp_note = f"VCP 미형성({v.note or '거래량 미감소'})" + (f": 조정폭 {shrink}" if shrink else "")
            add_watch(_watch(df, t, edge, account, [rs_note, f"매출 YoY {g.rate * 100:.0f}% 충족", vcp_note]))
        else:
            stats["setup"] += 1
            web.append(plan_record(t, t, stage, p, df))
        out.append({
            "ticker": t,
            "RS": round(r["rs"], 1),
            "rev_yoy%": round(g.rate * 100, 1),
            "yoy_label": g.label,
            "D/E": de,
            "52w고점대비%": round(r["tt"]["pct_from_high"] * 100, 1),
            "VCP": v.is_vcp,
            "수축폭": v.contractions,
            "pivot": round(v.pivot, 2) if v.pivot else None,
            "오늘돌파": v.breakout_today,
            "추격금지": v.extended,
            "단계": stage, "판단": p.action,
            "매수구간": f"{p.buy_low:,.2f} ~ {p.buy_high:,.2f}" if p.buy_low == p.buy_low else "-",
            "손절가": p.stop, "손절폭%": round(p.risk_pct * 100, 1) if p.risk_pct == p.risk_pct else None, "1차익절(1/3)": p.t1, "2차익절(1/3)": p.t2,
            "비중%": round(p.weight * 100, 1), "수량": p.shares_now,
            "메모": " / ".join(p.notes),
        })

    stats["watch"] = watch_count
    print(f"[3/3] 펀더멘털 통과: {stats['fundamental']}종목 · 매수 셋업(VCP/돌파): {stats['setup']}종목 · 관찰 표시 {watch_count}")
    for w in portfolio_heat(plans):
        print("⚠", w)
    res = pd.DataFrame(out)
    return (res.sort_values(["VCP", "RS"], ascending=False) if not res.empty else res), web, stats


# RS Rating 은 상대 지표이므로 유니버스가 클수록 의미가 있습니다(예: S&P500 + Nasdaq100).
DEFAULT_UNIVERSE = [
    # 나스닥100 주요 구성(2026 기준, 상장폐지·변경 티커는 다운로드 실패로 자동 제외)
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX", "AMD", "PEP",
    "ADBE", "CSCO", "TMUS", "LIN", "INTU", "QCOM", "TXN", "AMGN", "ISRG", "CMCSA", "HON", "AMAT",
    "BKNG", "VRTX", "ADP", "PANW", "ADI", "SBUX", "GILD", "MU", "LRCX", "MELI", "REGN", "KLAC",
    "MDLZ", "SNPS", "CDNS", "PYPL", "CRWD", "MAR", "CTAS", "ORLY", "ASML", "ABNB", "FTNT", "CEG",
    "WDAY", "MRVL", "CSX", "DASH", "ROP", "ADSK", "PCAR", "NXPI", "CHTR", "MNST", "CPRT", "PAYX",
    "AEP", "ODFL", "KDP", "ROST", "FAST", "TTD", "EA", "VRSK", "DDOG", "CTSH", "BKR", "EXC", "XEL",
    "GEHC", "LULU", "IDXX", "KHC", "CCEP", "FANG", "ZS", "ON", "TEAM", "CSGP", "BIIB", "DXCM",
    "MDB", "WBD", "ARM", "GFS", "PLTR", "APP", "AXON", "SHOP", "MSTR",
    # 성장·모멘텀 대표주
    "NET", "UBER", "SMCI", "ANET", "VRT", "HOOD", "COIN", "RKLB", "ONON", "NU", "SOFI", "CAVA",
    "DUOL", "TOST", "CRDO", "ALAB", "IONQ", "HIMS", "RDDT", "CELH", "ELF", "DECK", "SPOT", "NOW",
    "CRM", "ORCL", "GE", "ETN", "PWR", "LLY", "NVO", "TSM", "SNOW", "MNDY", "CPNG", "FICO",
]


if __name__ == "__main__":
    universe = DEFAULT_UNIVERSE
    pd.set_option("display.width", 200)
    import os
    account = float(os.environ.get("ACCOUNT_US", 20_000))  # 계좌 평가금액(USD)
    res, web, stats = screen(universe, account=account)
    print("웹앱 계획 JSON:", export_plans("us", web, account, stats))
    print(res.to_string(index=False))
    if not res.empty:
        from export import export_json
        print("저장 완료:", export_json(res, "us"))
