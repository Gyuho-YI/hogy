"""
해외(미국) 주식 스크리너: 미너비니 트렌드 템플릿 + RS Rating + VCP + 펀더멘털(분기 YoY)

원본 스크립트 대비 개선 사항
- 가격 데이터를 yf.download 로 일괄 수집 + 실패 종목만 순차 재시도(Rate Limit·캐시 충돌 대응)
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


def load_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    일괄 다운로드 후, 실패 종목만 1개씩 재시도.
    yfinance 병렬 다운로드는 내부 시간대 캐시(SQLite) 충돌로 'database is locked' 가 간헐 발생 → 순차 재시도로 보완.
    """
    px = yf.download(tickers, period="2y", auto_adjust=True, group_by="ticker", progress=False)
    frames: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = px[t].dropna() if len(tickers) > 1 else px.dropna()
        except KeyError:
            df = pd.DataFrame()
        if not df.empty:
            frames[t] = df

    missing = [t for t in tickers if t not in frames]
    for t in missing:
        try:
            df = yf.Ticker(t).history(period="2y", auto_adjust=True)[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if not df.empty:
                frames[t] = df
                print(f"  재시도 성공: {t}")
        except Exception as e:
            print(f"  ! {t} 재시도 실패: {e}")
        time.sleep(0.3)
    print(f"  가격 수신 {len(frames)}/{len(tickers)}종목")
    return frames


def screen(tickers: list[str], account: float = 10_000) -> tuple[pd.DataFrame, list[dict]]:
    """account: 계좌 평가금액(USD). 해외 전략 백테스트가 없으므로 고정 위험 1%로 사이징."""
    edge = edge_from_returns(pd.Series(dtype=float), "해외 백테스트 없음")
    plans, web = [], []
    print(f"[1/3] 가격 데이터 일괄 수집: {len(tickers)}종목")
    frames = load_prices(tickers)

    # --- [1] 기술적 필터 (펀더멘털 API 호출 전에 먼저 걸러 호출 수 최소화) ---
    rows = []
    for t, df in frames.items():
        tt = trend_template(df)
        rows.append({"ticker": t, "df": df, "tt": tt, "wret": weighted_return(df["Close"])})

    if not rows:
        # 전부 실패 = 네트워크/차단 문제. 빈 결과로 덮어쓰지 않도록 예외로 중단(이전 계획 유지)
        raise RuntimeError("가격 데이터를 하나도 받지 못했습니다. 네트워크 또는 Yahoo 접속 상태를 확인하세요.")
    base = pd.DataFrame(rows).dropna(subset=["wret"])
    if base.empty:
        return base, []
    base["rs"] = rs_rank(base["wret"])
    stage1 = base[base["tt"].map(lambda x: x["pass"]) & (base["rs"] >= MIN_RS)]
    print(f"[2/3] 트렌드 템플릿 + RS>={MIN_RS} 통과: {len(stage1)}종목")

    # --- [2] 펀더멘털 필터 + VCP ---
    out = []
    for _, r in stage1.iterrows():
        tk = yf.Ticker(r["ticker"])
        try:
            g = quarterly_revenue_yoy(tk)
            de = tk.info.get("debtToEquity")
        except Exception as e:  # 통신 오류는 로그를 남기고 건너뜀
            print(f"  ! {r['ticker']} 재무 조회 실패: {e}")
            continue
        finally:
            time.sleep(0.3)  # 성공/실패 무관하게 딜레이 적용

        if g.rate is None or g.rate < MIN_REV_YOY:
            continue
        if de is not None and de > MAX_DEBT_EQUITY:
            continue

        v = detect_vcp(r["df"])
        # 매매 계획: 돌파 당일/돌파 후 → '점화', VCP 형성 중 → '돌파 대기'(Buy Stop), 그 외 → 계획 없음
        close = float(r["df"]["Close"].iloc[-1])
        if v.pivot and close > v.pivot:
            stage = "점화"
        elif v.is_vcp:
            stage = "돌파 대기"
        else:
            stage = "추세만 충족"
        p = build_plan(r["df"], stage, edge, account, pivot=v.pivot, market="US")
        plans.append(p)
        if stage != "추세만 충족":
            web.append(plan_record(r["ticker"], r["ticker"], stage, p, r["df"]))
        out.append({
            "ticker": r["ticker"],
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

    print(f"[3/3] 펀더멘털 통과: {len(out)}종목")
    for w in portfolio_heat(plans):
        print("⚠", w)
    res = pd.DataFrame(out)
    return (res.sort_values(["VCP", "RS"], ascending=False) if not res.empty else res), web


# RS Rating 은 상대 지표이므로 유니버스가 클수록 의미가 있습니다(예: S&P500 + Nasdaq100).
DEFAULT_UNIVERSE = ["NVDA", "AAPL", "PLTR", "CRWD", "SMCI", "CELH", "TSLA", "META",
                    "MSFT", "AMZN", "GOOGL", "AVGO", "AMD", "NFLX", "ANET", "APP",
                    "AXON", "DDOG", "NET", "SHOP", "UBER", "TTD", "ELF", "DECK"]


if __name__ == "__main__":
    universe = DEFAULT_UNIVERSE
    pd.set_option("display.width", 200)
    import os
    account = float(os.environ.get("ACCOUNT_US", 20_000))  # 계좌 평가금액(USD)
    res, web = screen(universe, account=account)
    print("웹앱 계획 JSON:", export_plans("us", web, account))
    print(res.to_string(index=False))
    if not res.empty:
        from export import export_json
        print("저장 완료:", export_json(res, "us"))
