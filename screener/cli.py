"""
스크리너 통합 실행기(데스크톱 프로그램이 호출하는 단일 진입점).

  python cli.py kr --account 30000000 [--stats journal_stats.csv] [--out 출력폴더]
  python cli.py us --account 20000 [--universe NVDA,AAPL,...] [--out 출력폴더]
  python cli.py sectors kr   # 섹터·테마 레이더만(kr/us 실행 시 자동 포함)
  python cli.py check        # 설치 자가 진단

- PyInstaller 로 screener.exe 하나로 묶여 웹앱의 '지금 스크리닝 실행' 버튼/자동 스케줄에서 호출됩니다.
- 종료 코드: 0 성공, 1 실행 오류, 2 인자 오류, 3 KRX 로그인 필요/실패, 4 KRX 접속 실패
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

    sec = sub.add_parser("sectors", help="섹터·테마 레이더만 실행")
    sec.add_argument("which", choices=["kr", "us"])
    sec.add_argument("--out", default=None)
    sec.add_argument("--no-news", action="store_true", help="국내 뉴스 테마 분류 생략")

    for p in (kr, us):
        p.add_argument("--no-sectors", action="store_true", help="섹터·테마 레이더 생략")

    sub.add_parser("check", help="실행 파일 자가 진단(모든 모듈 로드 확인)")
    return ap.parse_args(argv)


EXIT_KRX_LOGIN = 3   # 웹앱 BatchService.exitMessage 와 약속된 종료 코드
EXIT_KRX_NETWORK = 4


def ensure_krx_login() -> int:
    """
    KRX 정보데이터시스템은 회원 로그인이 필요(pykrx 1.2+ 가 KRX_ID/KRX_PW 환경변수로 로그인).
    로그인 실패 상태로 진행하면 원인을 알기 어려운 빈 응답·컬럼 오류가 나므로 시작 전에 확인합니다.
    """
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        print("KRX 로그인 정보가 없습니다. 설정 화면에서 KRX 계정을 입력하세요"
              "(명령줄 실행 시 KRX_ID / KRX_PW 환경변수).", file=sys.stderr)
        return EXIT_KRX_LOGIN
    import requests
    try:
        # pykrx 는 패키지 import 시점에 로그인 세션을 만듦(네트워크 접속) → import 자체를 보호
        from pykrx.website.comm.auth import get_auth_session
        import pykrx.stock  # noqa: F401
        session = get_auth_session()
    except ImportError:          # 로그인 기능이 없는 구버전 pykrx
        print("경고: pykrx 버전이 낮아 KRX 로그인을 지원하지 않습니다(pip install -U pykrx)", file=sys.stderr)
        return 0
    except requests.RequestException as e:
        print(f"KRX 서버 접속 실패: 인터넷 연결·방화벽·회사망 차단 여부를 확인하세요. ({type(e).__name__})",
              file=sys.stderr)
        return EXIT_KRX_NETWORK
    if session is None:
        print("KRX 로그인 실패: 아이디/비밀번호를 확인하세요. 비밀번호 변경 요구 시 krx.co.kr 에서 변경 후 재입력.",
              file=sys.stderr)
        return EXIT_KRX_LOGIN
    return 0


def self_check() -> int:
    """패키징(PyInstaller) 누락 모듈 검출용: 실제 실행 경로의 모든 모듈을 import."""
    import importlib
    mods = ["pandas", "numpy", "requests", "lxml", "pykrx", "yfinance", "common", "accumulation", "support",
            "trade_plan", "export", "kr_screener", "kr_accumulation", "plan_screener", "us_screener",
            "sector_radar", "sector_data", "us_universe"]
    for m in mods:
        mod = importlib.import_module(m)
        print(f"OK {m} {getattr(mod, '__version__', '')}".rstrip())
    # 구성 종목 표 파싱 경로(pandas.read_html → lxml.html)가 패키징에 포함됐는지 실제 호출로 확인
    import us_universe
    html = "<table><tr><th>Symbol</th></tr>" + "".join(f"<tr><td>T{i}</td></tr>" for i in range(60)) + "</table>"
    assert len(us_universe.parse_symbols(html)) == 60
    print("OK read_html")
    return 0


def run(argv: list[str]) -> int:
    a = _parse(argv)
    if a.market == "check":
        return self_check()
    if a.market == "sectors":
        _set_out(a.out)
        if a.which == "kr" and (rc := ensure_krx_login()):
            return rc
        return run_sectors(a.which, news=not a.no_news)
    if a.account <= 0:
        print("계좌 금액은 0보다 커야 합니다", file=sys.stderr)
        return 2
    _set_out(a.out)

    # 출력 폴더 설정 후 import 해야 export.OUT_DIR 에 반영됨
    import pandas as pd
    from export import export_plans

    pd.set_option("display.width", 220)
    if a.market == "kr":
        if rc := ensure_krx_login():
            return rc
        import plan_screener
        stats = a.stats if a.stats and Path(a.stats).exists() else None
        res, web, funnel = plan_screener.main(a.account, stats)
        path = export_plans("kr", web, a.account, funnel)
    else:
        import us_screener
        res, web, stats = us_screener.screen(_us_universe(a.universe, us_screener.DEFAULT_UNIVERSE), account=a.account)
        path = export_plans("us", web, a.account, stats)

    print(res.to_string(index=False) if not res.empty else "후보 없음")
    print(f"PLANS_JSON={path}")

    # 섹터·테마 레이더: 실패해도 매매 계획 결과는 유지(종료 코드 0)
    if not a.no_sectors:
        try:
            run_sectors(a.market, news=True)
        except Exception as e:
            print(f"  ! 섹터 레이더 실패(매매 계획은 정상 저장됨): {e}")
    return 0


def _us_universe(arg: str | None, default: list[str]) -> list[str]:
    """
    해외 검사 대상: --universe > 출력 폴더의 us_universe.txt(한 줄에 티커 1개, # 주석)
                    > S&P 1500 + 나스닥100 자동 수집(실패 시 캐시 → 내장 기본 목록).
    """
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    from export import OUT_DIR
    f = Path(os.environ.get("COCKPIT_OUTPUT_DIR") or OUT_DIR) / "us_universe.txt"
    if f.exists():
        tickers = [ln.split("#")[0].strip().upper() for ln in f.read_text(encoding="utf-8").splitlines()]
        tickers = [t for t in tickers if t]
        if tickers:
            print(f"  사용자 유니버스 사용: {f.name} ({len(tickers)}종목)")
            return tickers
    import us_universe
    tickers, src = us_universe.load_universe(Path(os.environ.get("COCKPIT_OUTPUT_DIR") or OUT_DIR), default)
    print(f"  검사 대상: {len(tickers)}종목 · 출처 {src}")
    return tickers


def _set_out(out_dir: str | None) -> None:
    if out_dir:
        out = Path(out_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        os.environ["COCKPIT_OUTPUT_DIR"] = str(out)
        os.chdir(out)  # 부수 CSV(trade_plan_*.csv 등)도 같은 폴더에 저장


def run_sectors(market: str, news: bool = True) -> int:
    import sector_data
    from export import OUT_DIR
    out = Path(os.environ.get("COCKPIT_OUTPUT_DIR") or OUT_DIR)
    path = sector_data.run_kr(out, with_news=news) if market == "kr" else sector_data.run_us(out)
    print(f"SECTORS_JSON={path}")
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
