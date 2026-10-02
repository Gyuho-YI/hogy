"""
스크리너 통합 실행기(데스크톱 프로그램이 호출하는 단일 진입점).

  python cli.py kr --account 30000000 [--stats journal_stats.csv] [--out 출력폴더]
  python cli.py us --account 20000 [--universe NVDA,AAPL,...] [--out 출력폴더]
  python cli.py check        # 설치 자가 진단

- PyInstaller 로 screener.exe 하나로 묶여 웹앱의 '지금 스크리닝 실행' 버튼/자동 스케줄에서 호출됩니다.
- 종료 코드: 0 성공, 1 실행 오류, 2 인자 오류
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="screener", description="국내/해외 매매 계획 스크리너")
    sub = ap.add_subparsers(dest="market", required=True)

    kr = sub.add_parser("kr", help="국내: 매집/점화 후보 → 매매 계획")
    kr.add_argument("--account", type=float, required=True, help="계좌 평가금액(원)")
    kr.add_argument("--stats", default=None, help="실전 일지/백테스트 CSV(strategy,ret) → 하프켈리")

    us = sub.add_parser("us", help="해외: VCP 후보 → 매매 계획")
    us.add_argument("--account", type=float, required=True, help="계좌 평가금액(USD)")
    us.add_argument("--universe", default=None, help="쉼표 구분 티커(미지정 시 기본 유니버스)")

    for p in (kr, us):
        p.add_argument("--out", default=None, help="출력 폴더(plans_*.json)")

    sub.add_parser("check", help="실행 파일 자가 진단(모든 모듈 로드 확인)")
    return ap.parse_args(argv)


def self_check() -> int:
    """패키징(PyInstaller) 누락 모듈 검출용: 실제 실행 경로의 모든 모듈을 import."""
    import importlib
    mods = ["pandas", "numpy", "pykrx", "yfinance", "common", "accumulation", "support",
            "trade_plan", "export", "kr_screener", "kr_accumulation", "plan_screener", "us_screener"]
    for m in mods:
        mod = importlib.import_module(m)
        print(f"OK {m} {getattr(mod, '__version__', '')}".rstrip())
    return 0


def run(argv: list[str]) -> int:
    a = _parse(argv)
    if a.market == "check":
        return self_check()
    if a.account <= 0:
        print("계좌 금액은 0보다 커야 합니다", file=sys.stderr)
        return 2
    if a.out:
        out = Path(a.out).resolve()
        out.mkdir(parents=True, exist_ok=True)
        os.environ["COCKPIT_OUTPUT_DIR"] = str(out)
        os.chdir(out)  # 부수 CSV(trade_plan_*.csv 등)도 같은 폴더에 저장

    # 출력 폴더 설정 후 import 해야 export.OUT_DIR 에 반영됨
    import pandas as pd
    from export import export_plans

    pd.set_option("display.width", 220)
    if a.market == "kr":
        import plan_screener
        stats = a.stats if a.stats and Path(a.stats).exists() else None
        res, web = plan_screener.main(a.account, stats)
        path = export_plans("kr", web, a.account)
    else:
        import us_screener
        universe = [t.strip().upper() for t in a.universe.split(",")] if a.universe else us_screener.DEFAULT_UNIVERSE
        res, web = us_screener.screen(universe, account=a.account)
        path = export_plans("us", web, a.account)

    print(res.to_string(index=False) if not res.empty else "후보 없음")
    print(f"PLANS_JSON={path}")
    return 0


if __name__ == "__main__":
    # Windows 콘솔/파이프에서 한글 깨짐 방지
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        sys.exit(run(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
