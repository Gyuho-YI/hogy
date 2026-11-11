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
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from common import Growth, detect_vcp, rs_rank, safe_yoy, trend_template
from events import business_days_until, earnings_block, next_earnings_date, today_kst
from export import export_plans, plan_record
from risk_gate import Candidate, apply_gate
from simulate import sim_verdict, simulate_plan
from trade_plan import block_entry, build_plan, edge_from_returns

MIN_REV_YOY = 0.20      # 매출 YoY 20% 이상
MIN_EPS_YOY = 0.25      # 희석 EPS YoY 25% 이상(미너비니 SEPA 기준). 계산불가면 탈락시키지 않고 메모만
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


@dataclass
class Fundamentals:
    """분기 손익계산서 기반 펀더멘털(모두 전년 동기 대비)."""
    rev: Growth
    eps: Growth
    eps_prev: Growth                 # 직전 분기의 EPS YoY(가속 판단용)
    op_margin: float | None          # 최근 분기 영업이익률
    op_margin_prev: float | None     # 전년 동기 영업이익률

    @property
    def eps_accelerating(self) -> bool | None:
        if self.eps.rate is None or self.eps_prev.rate is None:
            return None
        return bool(self.eps.rate > self.eps_prev.rate)

    @property
    def margin_delta(self) -> float | None:
        if self.op_margin is None or self.op_margin_prev is None:
            return None
        return self.op_margin - self.op_margin_prev

    def failures(self) -> list[str]:
        """EPS 기준 탈락 사유. 데이터가 없으면(계산불가) 탈락시키지 않습니다."""
        f = []
        if self.eps.label in ("적자전환", "적자확대", "적자지속"):
            f.append(f"EPS {self.eps.label}")
        elif self.eps.label == "정상" and self.eps.rate is not None and self.eps.rate < MIN_EPS_YOY:
            f.append(f"EPS YoY {self.eps.rate * 100:.0f}% < {MIN_EPS_YOY * 100:.0f}%")
        return f

    def to_record(self) -> dict:
        pct = lambda x: None if x is None else round(x * 100, 1)  # noqa: E731
        return {
            "revYoy": pct(self.rev.rate), "revLabel": self.rev.label,
            "epsYoy": pct(self.eps.rate), "epsLabel": self.eps.label,
            "epsYoyPrev": pct(self.eps_prev.rate), "epsAccel": self.eps_accelerating,
            "opMargin": pct(self.op_margin), "opMarginPrev": pct(self.op_margin_prev),
            "marginDelta": pct(self.margin_delta),
        }


def _row(q: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    for n in names:
        if n in q.index:
            return pd.to_numeric(q.loc[n], errors="coerce")
    return None


def _at(s: pd.Series | None, i: int):
    return None if s is None or len(s) <= i else s.iloc[i]


def quarterly_fundamentals(tk: yf.Ticker) -> Fundamentals:
    """
    분기 손익계산서(최신 → 과거 열 순서)로 매출·EPS YoY, EPS 가속, 영업이익률 변화를 계산.
    열이 부족한 항목은 '계산불가'로 남깁니다(0 으로 채우지 않음).
    """
    rev_g = quarterly_revenue_yoy(tk)
    try:
        q = tk.quarterly_income_stmt
    except Exception:
        q = None
    if q is None or getattr(q, "empty", True):
        none = safe_yoy(None, None)
        return Fundamentals(rev_g, none, none, None, None)
    eps = _row(q, ("Diluted EPS", "Basic EPS"))
    rev = _row(q, ("Total Revenue", "Operating Revenue"))
    op = _row(q, ("Operating Income", "Total Operating Income As Reported"))

    def margin(i):
        r, o = _at(rev, i), _at(op, i)
        if r is None or o is None or pd.isna(r) or pd.isna(o) or r == 0:
            return None
        return float(o / r)

    return Fundamentals(
        rev=rev_g,
        eps=safe_yoy(_at(eps, 0), _at(eps, 4)),
        eps_prev=safe_yoy(_at(eps, 1), _at(eps, 5)),
        op_margin=margin(0), op_margin_prev=margin(4),
    )


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
    - 돌파 감시선: 현재가 위의 VCP 피벗, 없거나 이미 지났으면 최근 30거래일 고점 → 거래량 동반 돌파 시 재검토
    - 이탈선: 50일선 → 종가 이탈 시 추세 훼손(관찰 제외 후보)
    """
    v = detect_vcp(df)
    close = float(df["Close"].iloc[-1])
    recent_high = float(df["High"].iloc[-30:].max())       # 항상 현재가 이상
    # 이미 지나간(현재가보다 낮은) 피벗은 감시선으로 무의미 → 최근 고점 사용
    breakout = float(v.pivot) if v.pivot and v.pivot >= close else recent_high
    exit_line = float(df["Close"].rolling(50).mean().iloc[-1])
    return {"watchBreakout": round(breakout, 2), "watchExit": round(exit_line, 2)}


def _simulate(df: pd.DataFrame, p) -> dict | None:
    """매수 상단 체결 → 손절 vs 1차 목표(2R) 시뮬레이션. 기대값이 명백히 음수면 진입 보류."""
    if not (p.buy_high == p.buy_high and p.stop == p.stop and p.t1 == p.t1):
        return None
    s = simulate_plan(df, p.buy_high, p.stop, p.t1)
    block, note = sim_verdict(s)
    if block:
        block_entry(p, "sim", note)
    elif s.ok:
        p.notes.append(note)
    return s.to_record() if s.ok else None


WATCH_STAGE = "관찰(추세 통과)"


def classify_stage(v, close: float) -> tuple[str, str]:
    """
    VCP 결과 → 매매 단계.
    - '점화'     : 수축 형태 충족 + 최근 5영업일 내 '거래량 200% 동반' 피벗 돌파 + 현재가가 피벗 위
    - '돌파 대기': VCP 형성 완료(형태 + 거래량 고갈), 아직 피벗 아래 → Buy Stop
    - '추세만 충족': 그 외(피벗 위라도 거래량 없는 돌파, 형태 미충족은 매수 셋업이 아님)
    반환: (단계, 탈락 시 사유)
    """
    if v.pivot and close > v.pivot:
        if v.shape_ok and v.breakout_days_ago is not None:
            return "점화", ""
        if not v.shape_ok:
            return "추세만 충족", "피벗 위지만 VCP 수축 형태 미충족"
        return "추세만 충족", "피벗 위지만 거래량 동반 돌파 없음(50일 평균 200% 미만)"
    if v.is_vcp:
        return "돌파 대기", ""
    shrink = " → ".join(f"{c * 100:.0f}%" for c in v.contractions)
    return "추세만 충족", f"VCP 미형성({v.note or '거래량 미감소'})" + (f": 조정폭 {shrink}" if shrink else "")


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
    setups: list[dict] = []
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
            fu = quarterly_fundamentals(tk)
            g = fu.rev
            info = tk.info or {}
            de = info.get("debtToEquity")
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
        fails += fu.failures()
        if fails:
            add_watch(_watch(df, t, edge, account, [rs_note, "펀더멘털 미달: " + ", ".join(fails)]))
            continue
        stats["fundamental"] += 1

        v = detect_vcp(df)
        stage, stage_note = classify_stage(v, float(df["Close"].iloc[-1]))
        p = build_plan(df, stage, edge, account, pivot=v.pivot, market="US")
        plans.append(p)
        if stage == "추세만 충족":
            add_watch(_watch(df, t, edge, account, [rs_note, f"매출 YoY {g.rate * 100:.0f}% 충족", stage_note]))
            continue

        # ---- 사후 규칙: 실적 발표 회피 → 시뮬레이션 필터 (게이트는 전 종목을 모은 뒤) ----
        try:
            ed = next_earnings_date(tk)
        except Exception:
            ed = None
        days = business_days_until(ed, today_kst()) if ed else None
        if earnings_block(days):
            block_entry(p, "earnings", f"실적 발표 {ed:%m/%d}(D-{days}) → 발표 후 재평가")
        sim = _simulate(df, p)
        setups.append({"code": t, "stage": stage, "plan": p, "df": df, "score": float(r["rs"]),
                       "sector": info.get("sector"),
                       "extra": {"score": round(float(r["rs"]), 1), "sector": info.get("sector"),
                                 "earningsDate": ed.isoformat() if ed else None, "earningsDays": days,
                                 "fundamentals": fu.to_record(), "sim": sim,
                                 "vcp": {"contractions": v.contractions, "pivot": v.pivot,
                                         "breakoutDaysAgo": v.breakout_days_ago}},
                       "row": {
                           "ticker": t, "RS": round(r["rs"], 1),
                           "rev_yoy%": round(g.rate * 100, 1), "yoy_label": g.label,
                           "eps_yoy%": fu.to_record()["epsYoy"], "eps_label": fu.eps.label,
                           "op_margin%": fu.to_record()["opMargin"], "D/E": de,
                           "52w고점대비%": round(r["tt"]["pct_from_high"] * 100, 1),
                           "VCP": v.is_vcp, "수축폭": v.contractions,
                           "pivot": round(v.pivot, 2) if v.pivot else None,
                           "오늘돌파": v.breakout_today, "추격금지": v.extended, "단계": stage,
                           "실적발표": ed.isoformat() if ed else None}})

    # ---- 리스크 게이트: RS 높은 순으로 누적(총 위험·보유 수·섹터 집중) ----
    gate = apply_gate([Candidate(x["code"], x["plan"], x["score"], x["sector"]) for x in setups])
    stats.update({"setup": len(setups), "gated": gate["gated"], "heatUsed": gate["heatUsed"]})
    for x in setups:
        p = x["plan"]
        web.append(plan_record(x["code"], x["code"], x["stage"], p, x["df"], extra=x["extra"]))
        sim = x["extra"]["sim"] or {}
        out.append({**x["row"],
                    "판단": p.action,
                    "매수구간": f"{p.buy_low:,.2f} ~ {p.buy_high:,.2f}" if p.buy_low == p.buy_low else "-",
                    "손절가": p.stop, "손절폭%": round(p.risk_pct * 100, 1) if p.risk_pct == p.risk_pct else None,
                    "1차익절(1/3)": p.t1, "2차익절(1/3)": p.t2,
                    "저항R": p.rr_resistance, "시뮬목표%": sim.get("pTarget"), "시뮬평균R": sim.get("expR"),
                    "비중%": round(p.weight * 100, 1), "수량": p.shares_now,
                    "메모": " / ".join(p.notes)})

    stats["watch"] = watch_count
    print(f"[3/3] 펀더멘털 통과: {stats['fundamental']}종목 · 매수 셋업(VCP/돌파): {stats['setup']}종목 · 관찰 표시 {watch_count}")
    print(f"  리스크 게이트: 총 위험 {gate['heatUsed']:.1%} / 한도 {gate['heatLimit']:.0%} · 보류 {gate['gated']}종목")
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
