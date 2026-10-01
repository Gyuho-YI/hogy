"""
국내 '눌림 매집' 스크리너 (pykrx).

kr_screener.py 와의 차이
- kr_screener: 이미 거래대금이 터진 종목(시세 초입)을 찾습니다.
- kr_accumulation: 아직 조용하지만 기관·외국인이 물량을 모으는 종목(시세 이전)을 찾습니다.
  → 당일 거래대금 상위로 거르지 않고, 시가총액 기준 유니버스를 사용합니다.

실행: cd screener && python kr_accumulation.py   (장 마감 후 18시 이후 권장)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

from accumulation import analyze_accumulation
from kr_screener import biz_date, build_universe

MIN_MCAP_ACCUM = 2_000e8  # 기관 매집은 중대형주 위주 → 시총 2,000억 이상
TOP_N_BY_MCAP = 400       # 호출 수 제한


def load(ticker: str, start: str, end: str):
    px = stock.get_market_ohlcv(start, end, ticker).rename(
        columns={"시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume"}
    )
    px = px[px["Volume"] > 0]
    # 투자자별 순매수 '수량'(주). 대금이 아닌 수량을 써야 주가 수준과 무관하게 상장주식수 대비 비율 계산 가능
    flow = stock.get_market_trading_volume_by_date(start, end, ticker, detail=True)
    try:
        sb = stock.get_shorting_balance_by_date(start, end, ticker)["공매도잔고"]
    except Exception:
        sb = None  # 공매도 잔고 미제공 종목/기간은 숏커버 판별 생략
    return px, flow, sb


def screen() -> pd.DataFrame:
    end = biz_date()
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=150)).strftime("%Y%m%d")

    uni = build_universe(end)
    uni = uni[uni["시가총액"] >= MIN_MCAP_ACCUM].sort_values("시가총액", ascending=False).head(TOP_N_BY_MCAP)
    print(f"[1/2] 분석 대상: {len(uni)}종목 (시총 {MIN_MCAP_ACCUM/1e8:,.0f}억↑)")

    out = []
    for i, (t, row) in enumerate(uni.iterrows(), 1):
        try:
            px, flow, sb = load(t, start, end)
            r = analyze_accumulation(px, flow, row["상장주식수"], sb)
            if r.stage != "해당없음":
                out.append({
                    "code": t, "name": row["name"], "단계": r.stage, "점수": r.score,
                    "기간주가%": round(r.price_chg * 100, 1),
                    "누적매집%(상장주식)": round(r.cum_pct_float * 100, 2),
                    "순매수일비율": r.buy_day_ratio, "눌림흡수율": r.absorb_ratio,
                    "연기금·투신비중": r.long_term_share,
                    "AD다이버전스": r.ad_divergence, "변동성축소": r.contraction,
                    "메모": " / ".join(r.notes),
                })
        except Exception as e:
            print(f"  ! {t} 조회 실패: {e}")
        finally:
            time.sleep(0.3)
        if i % 50 == 0:
            print(f"  ... {i}/{len(uni)} 진행")

    res = pd.DataFrame(out)
    print(f"[2/2] 매집 후보: {len(res)}종목")
    if res.empty:
        return res
    order = {"점화": 0, "매집 후기(점화 대기)": 1, "매집 진행": 2}
    return res.sort_values(["단계", "점수"], key=lambda s: s.map(order) if s.name == "단계" else -s)


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    result = screen()
    print(result.to_string(index=False))
    if not result.empty:
        fname = f"kr_accumulation_{biz_date()}.csv"
        result.to_csv(fname, index=False, encoding="utf-8-sig")
        print(f"\n저장 완료: {fname}")
