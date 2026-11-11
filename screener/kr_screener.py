"""
국내 주식 스크리너: '펀더멘털' 대신 '돈의 흐름(거래대금·수급) + 추세'를 1차 필터로 사용

설계 철학
- 국내 단기 시세는 실적보다 테마/수급(외국인·기관·세력)이 먼저 움직입니다.
- 따라서 [유동성 → 수급 → 추세/VCP → 과열 배제] 순으로 거르고,
  펀더멘털은 '탈락 기준(적자 확대·관리종목)'으로만 약하게 사용합니다.
- 테마 판별(왜 오르는가)은 정량화가 어려우므로, 최종 후보를 CSV 로 내보내
  LLM(Claude 등)에게 뉴스/공시 기반 테마 태깅을 맡기는 2단계 구조입니다.

데이터: pykrx (KRX 정보데이터시스템). 장 마감 후(18시 이후) 실행 권장.
실행: pip install -r requirements.txt && python screener/kr_screener.py
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

from common import detect_vcp, trend_template

# ---- 파라미터 (국내 시장 특성 반영) ---------------------------------------
MIN_MCAP = 1_000e8            # 시총 1,000억 이상 (작전성 초소형주 배제)
TOP_N_BY_VALUE = 300          # 20일 평균 거래대금 상위 N 종목만 정밀 분석
VALUE_SPIKE_MULT = 3.0        # 최근 5일 중 거래대금이 20일 평균의 300% 이상인 날 존재 → '돈이 들어온 흔적'
SMART_MONEY_DAYS = 5          # 외국인+기관 수급 관찰 기간
MIN_SMART_BUY_DAYS = 3        # 그 중 외국인+기관 합산 순매수일 최소 일수
MAX_DAY_CHANGE = 0.20         # 당일 +20% 이상(상한가 근접) → 추격 금지
MAX_5D_RETURN = 0.40          # 5일 +40% 이상 → 과열 배제
STOP_LOSS = 0.07              # 국내 권장 손절선 -7% (가격제한폭 30%·VI 감안해 미국보다 타이트)


def biz_date(offset_days: int = 0) -> str:
    """가장 최근 영업일(YYYYMMDD). 휴장일이면 직전 영업일로 보정."""
    d = (datetime.now() - timedelta(days=offset_days)).strftime("%Y%m%d")
    return stock.get_nearest_business_day_in_a_week(d)


def build_universe(date: str) -> pd.DataFrame:
    """KOSPI+KOSDAQ 전 종목 → 우선주/스팩/리츠/소형주 제외."""
    cap = stock.get_market_cap(date, market="ALL")  # 종가, 시가총액, 거래량, 거래대금, 상장주식수
    cap = cap[cap["시가총액"] >= MIN_MCAP].copy()
    cap["name"] = [stock.get_market_ticker_name(t) for t in cap.index]
    excl = cap["name"].str.contains("스팩|리츠|우$|우B$|우C$", regex=True)
    cap = cap[~excl & cap.index.str.endswith("0")]  # 보통주 코드는 0 으로 끝남
    return cap


def smart_money(ticker: str, start: str, end: str) -> dict:
    """투자자별 순매수대금(원). 외국인+기관 연속성, 개인 매도 여부를 반환."""
    tv = stock.get_market_trading_value_by_date(start, end, ticker).tail(SMART_MONEY_DAYS)
    if tv.empty:
        return {"ok": False}
    smart = tv["외국인합계"] + tv["기관합계"]
    return {
        "ok": True,
        "smart_buy_days": int((smart > 0).sum()),
        "smart_sum_억": round(smart.sum() / 1e8, 1),
        "retail_sum_억": round(tv["개인"].sum() / 1e8, 1),
    }


def screen() -> pd.DataFrame:
    end = biz_date()
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=400)).strftime("%Y%m%d")

    uni = build_universe(end)
    print(f"[1/4] 유동성 유니버스(시총 {MIN_MCAP/1e8:,.0f}억↑): {len(uni)}종목")

    # 당일 거래대금 기준 1차 컷(정밀 분석 호출 수 제한)
    cand = uni.sort_values("거래대금", ascending=False).head(TOP_N_BY_VALUE)

    out = []
    for i, (t, row) in enumerate(cand.iterrows(), 1):
        try:
            df = stock.get_market_ohlcv(start, end, t).rename(
                columns={"시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume", "거래대금": "Value"}
            )
            df = df[df["Volume"] > 0]  # 거래정지일 제거
            if len(df) < 150:
                continue
            if "Value" not in df:  # 구버전 pykrx 대응: 근사 거래대금
                df["Value"] = df["Close"] * df["Volume"]

            # --- [2] 거래대금 폭발: 최근 5일 중 20일 평균 대비 3배 이상인 날이 있는가 ---
            val20 = df["Value"].rolling(20).mean().shift(1)
            spike = (df["Value"] / val20).iloc[-5:].max()
            if pd.isna(spike) or spike < VALUE_SPIKE_MULT:
                continue

            # --- [3] 추세: 국내는 순환이 빨라 20/60/120 일선 정배열 사용 ---
            tt = trend_template(df, short=20, mid=60, long=120)
            if not tt["pass"]:
                continue

            # --- [4] 과열 배제: 상한가 추격/단기 폭등 종목 제외 ---
            day_chg = df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1
            ret5 = df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1
            if day_chg >= MAX_DAY_CHANGE or ret5 >= MAX_5D_RETURN:
                continue

            # --- [5] 수급: 외국인+기관이 실제로 사고 있는가 (개인 단독 랠리 배제) ---
            sm = smart_money(t, start, end)
            if not sm["ok"] or sm["smart_buy_days"] < MIN_SMART_BUY_DAYS:
                continue

            v = detect_vcp(df, base_len=45, max_last_depth=0.12)  # 국내 변동성 감안 완화
            close = float(df["Close"].iloc[-1])
            out.append({
                "code": t,
                "name": row["name"],
                "시총(억)": round(row["시가총액"] / 1e8),
                "거래대금배수": round(spike, 1),
                "5일수익%": round(ret5 * 100, 1),
                "52w고점대비%": round(tt["pct_from_high"] * 100, 1),
                "기관외인순매수일": sm["smart_buy_days"],
                "기관외인합(억)": sm["smart_sum_억"],
                "개인합(억)": sm["retail_sum_억"],
                "VCP": v.is_vcp,
                "pivot": v.pivot,
                "손절가": round(close * (1 - STOP_LOSS)),
            })
        except Exception as e:
            print(f"  ! {t} 조회 실패: {e}")
        finally:
            time.sleep(0.2)  # KRX 서버 부하 방지
        if i % 50 == 0:
            print(f"  ... {i}/{len(cand)} 진행")

    res = pd.DataFrame(out)
    print(f"[4/4] 최종 후보: {len(res)}종목")
    if res.empty:
        return res
    # 점수: 수급 강도(외인+기관 순매수 규모) 우선, VCP 가점
    res["score"] = res["기관외인합(억)"].rank(pct=True) * 70 + res["VCP"].astype(int) * 30
    return res.sort_values("score", ascending=False)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    result = screen()
    print(result.to_string(index=False))
    if not result.empty:
        # 다음 단계: 이 CSV 를 LLM 에 넘겨 '테마 태깅 + 재료 지속성' 판단 (README 프롬프트 참조)
        fname = f"kr_candidates_{biz_date()}.csv"
        result.to_csv(fname, index=False, encoding="utf-8-sig")  # 엑셀 한글 깨짐 방지
        print(f"\n저장 완료: {fname}")
