"""
매매 계획 스크리너 (국내): 매집/점화 후보 → 종목별 [매수 구간 · 손절 · 1·2차 익절 · 트레일링 · 하프켈리 수량]

흐름
1) kr_accumulation.screen() 으로 매집/점화 후보 추출
2) 종목별 최근 10영업일 내 점화일 탐색 → 피벗(점화 직전 20일 고가)·앵커드 VWAP 기준점 확정
3) entry_backtest 결과 CSV(있으면)로 단계별 승률·손익비 → 하프 켈리 위험 비율 산출
4) trade_plan.build_plan() 으로 매매 계획 생성(매물 저항 2R 미만 → 진입 보류)
5) 일봉 시뮬레이션(simulate.py)으로 기대값이 명백히 음수인 계획 제외
6) 리스크 게이트(risk_gate.py): 매집 점수 순으로 총 위험 6%·동시 6종목·동일 업종 2종목 한도

실행 예
  python plan_screener.py --account 30000000
  python plan_screener.py --account 30000000 --stats entry_backtest_20261001.csv   # 켈리 적용
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta

import pandas as pd

from accumulation import analyze_accumulation
from kr_accumulation import load
from kr_accumulation import screen as accumulation_screen
from kr_screener import biz_date
from events import kr_earnings_season, today_kst
from export import export_plans, plan_record
from risk_gate import Candidate, apply_gate
from simulate import sim_verdict, simulate_plan
from trade_plan import block_entry, build_plan, edge_from_returns

IGNITION_LOOKBACK = 10  # 최근 10영업일 내 점화면 '점화' 단계로 계획 수립


def load_edges(stats_csv: str | None) -> dict:
    """백테스트 거래 내역 → 단계별 Edge. 파일이 없으면 고정 위험 1%."""
    if not stats_csv:
        e = edge_from_returns(pd.Series(dtype=float), "백테스트 없음")
        return {"pre": e, "ign": e}
    tr = pd.read_csv(stats_csv)
    return {
        "pre": edge_from_returns(tr.loc[tr["strategy"] == "A.선진입", "ret"], "A.선진입"),
        "ign": edge_from_returns(tr.loc[tr["strategy"] == "B.점화진입", "ret"], "B.점화진입"),
    }


def load_sector_map(date: str) -> dict[str, str]:
    """종목코드 → KRX 업종명(리스크 게이트의 업종 집중 한도용). 조회 실패 시 빈 맵(한도 미적용)."""
    from pykrx import stock
    out: dict[str, str] = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        try:
            sc = stock.get_market_sector_classifications(date, mkt)
            out.update({str(k): str(v) for k, v in sc["업종명"].items()})
        except Exception as e:
            print(f"  ! 업종 분류 조회 실패({mkt}): {e}")
    return out


def find_ignition(px, flow, shares_out, sb) -> int | None:
    """최근 IGNITION_LOOKBACK 일 중 가장 최근 점화일 인덱스(그날까지의 데이터로만 판정)."""
    for k in range(len(px) - 1, max(len(px) - 1 - IGNITION_LOOKBACK, 61), -1):
        sbk = sb.loc[: px.index[k]] if sb is not None else None
        if analyze_accumulation(px.iloc[: k + 1], flow, shares_out, sbk).stage == "점화":
            return k
    return None


def main(account: float, stats_csv: str | None) -> tuple[pd.DataFrame, list[dict], dict]:
    edges = load_edges(stats_csv)
    for k, e in edges.items():
        print(f"[Edge:{k}] 승률(하한) {e.p} / 손익비 {e.b} / 풀켈리 {e.kelly} / 적용 위험 {e.risk:.2%} — {e.source}")

    cands = accumulation_screen()
    import kr_accumulation
    stats = {"scanned": kr_accumulation.LAST_SCANNED, "candidates": len(cands), "setup": 0}
    if cands.empty:
        return cands, [], stats
    end = biz_date()
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=420)).strftime("%Y%m%d")
    from pykrx import stock  # 상장주식수 조회

    shares_out = stock.get_market_cap(end, market="ALL")["상장주식수"]
    sector_of = load_sector_map(end)
    season = kr_earnings_season(today_kst())

    rows, plans, web, pending = [], [], [], []
    for _, c in cands.iterrows():
        t = c["code"]
        try:
            px, flow, sb = load(t, start, end)
            so = float(shares_out.get(t, 0))
            ign = find_ignition(px, flow, so, sb)
            stage = "점화" if ign is not None else c["단계"]
            ref = ign if ign is not None else len(px) - 1
            pivot = float(px["High"].iloc[ref - 20: ref].max())
            accum_start = max(0, ref - 40)

            edge = edges["ign"] if stage == "점화" else edges["pre"]
            p = build_plan(px, stage, edge, account, pivot=pivot,
                           ignition_idx=ign, accum_start_idx=accum_start)
            if season and p.action != "관망":
                p.notes.append("실적 시즌: 잠정실적 공시 일정 확인 후 진입(DART)")
            sim = None
            if p.buy_high == p.buy_high and p.stop == p.stop and p.t1 == p.t1:
                s_res = simulate_plan(px, p.buy_high, p.stop, p.t1)
                blk, note = sim_verdict(s_res)
                if blk:
                    block_entry(p, "sim", note)
                elif s_res.ok:
                    p.notes.append(note)
                sim = s_res.to_record() if s_res.ok else None
            plans.append(p)
            pending.append({"code": t, "name": c["name"], "stage": stage, "plan": p, "px": px,
                            "score": float(c["점수"]), "sector": sector_of.get(t),
                            "extra": {"score": float(c["점수"]), "sector": sector_of.get(t), "sim": sim,
                                      "earningsSeason": season}})
            rows.append({
                "code": t, "name": c["name"], "단계": stage, "판단": p.action,
                "현재가": float(px["Close"].iloc[-1]),
                "매수구간": f"{p.buy_low:,.0f} ~ {p.buy_high:,.0f}",
                "손절가": p.stop, "손절폭%": round(p.risk_pct * 100, 1),
                "1차익절(1/3)": p.t1, "2차익절(1/3)": p.t2,
                "추가매수트리거": p.add_trigger,
                "비중%": round(p.weight * 100, 1),
                "지금수량": p.shares_now, "점화시추가": p.shares_add,
                "투입금액": round(p.shares_now * p.buy_high) if p.buy_high == p.buy_high else 0,
                "메모": " / ".join(p.notes),
            })
        except Exception as e:
            print(f"  ! {t} 계획 실패: {e}")
        finally:
            time.sleep(0.3)

    gate = apply_gate([Candidate(x["code"], x["plan"], x["score"], x["sector"]) for x in pending])
    print(f"리스크 게이트: 총 위험 {gate['heatUsed']:.1%} / 한도 {gate['heatLimit']:.0%} · 보류 {gate['gated']}종목")
    for x in pending:
        web.append(plan_record(x["code"], x["name"], x["stage"], x["plan"], x["px"], extra=x["extra"]))
    by_code = {x["code"]: x for x in pending}
    rows = [r for r in rows if r["code"] in by_code]
    for r in rows:                    # 게이트 반영 후 판단·수량 갱신
        x = by_code[r["code"]]
        r["판단"], r["지금수량"] = x["plan"].action, x["plan"].shares_now
        r["투입금액"] = round(x["plan"].shares_now * x["plan"].buy_high) if x["plan"].buy_high == x["plan"].buy_high else 0
        r["메모"] = " / ".join(x["plan"].notes)
    order = {"지금 매수 가능": 0, "지정가 대기": 1, "관망": 2}
    stats["setup"] = sum(1 for p in plans if p.action != "관망")
    stats.update({"gated": gate["gated"], "heatUsed": gate["heatUsed"]})
    res = pd.DataFrame(rows)
    return (res.sort_values("판단", key=lambda s: s.map(order)) if not res.empty else res), web, stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=float, default=10_000_000, help="계좌 평가금액(원)")
    ap.add_argument("--stats", default=None, help="entry_backtest.py 결과 CSV (켈리 산출용)")
    a = ap.parse_args()

    pd.set_option("display.width", 260)
    res, web, stats = main(a.account, a.stats)
    print("웹앱 계획 JSON:", export_plans("kr", web, a.account, stats))
    print(res.to_string(index=False))
    if not res.empty:
        fname = f"trade_plan_{biz_date()}.csv"
        res.to_csv(fname, index=False, encoding="utf-8-sig")
        print(f"\n저장 완료: {fname}")
        from export import export_json
        print("웹앱용 JSON:", export_json(res, "kr"))
