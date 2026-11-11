"""해외 유니버스 수집: 위키백과 표 파싱, 표기 변환, 실패 시 캐시·기본 목록 폴백(네트워크 없이)."""
import json

import us_universe as uu


def wiki_table(symbols, col="Symbol"):
    rows = "".join(f"<tr><td>{s}</td><td>Co {i}</td><td>Information Technology</td></tr>" for i, s in enumerate(symbols))
    return (f"<html><body><table class='wikitable'><tr><th>{col}</th><th>Security</th><th>GICS Sector</th></tr>"
            f"{rows}</table></body></html>")


def test_표_파싱과_표기변환():
    syms = ["AAPL", "BRK.B", "BF.B", " msft ", "123BAD"] + [f"Z{i}" for i in range(60)]
    out = uu.parse_symbols(wiki_table(syms))
    assert out[:4] == ["AAPL", "BRK-B", "BF-B", "MSFT"]   # yfinance 표기
    assert "123BAD" not in out
    assert uu.parse_symbols(wiki_table([f"T{i}" for i in range(60)], col="Ticker"))[0] == "T0"


def test_실시간_성공시_캐시_저장(tmp_path, monkeypatch):
    big = [f"S{i}" for i in range(1300)]
    monkeypatch.setattr(uu, "fetch_live", lambda: (big, {"S&P500": 500, "S&P400": 400, "S&P600": 400, "NASDAQ100": 0}))
    tickers, src = uu.load_universe(tmp_path, extras=["PLTR", "S1"])
    assert len(tickers) == 1301 and tickers[-1] == "PLTR"     # 중복 제거 + 성장주 추가
    assert src.startswith("실시간")
    assert json.loads((tmp_path / uu.CACHE_NAME).read_text(encoding="utf-8"))["tickers"][:2] == ["S0", "S1"]


def test_실패시_캐시_그다음_기본목록(tmp_path, monkeypatch):
    monkeypatch.setattr(uu, "fetch_live", lambda: ([], {}))
    tickers, src = uu.load_universe(tmp_path, extras=["AAPL"])
    assert tickers == ["AAPL"] and src == "내장 기본 목록"
    (tmp_path / uu.CACHE_NAME).write_text(json.dumps({"date": "2026-10-01", "tickers": ["X", "Y"]}), encoding="utf-8")
    tickers, src = uu.load_universe(tmp_path, extras=["AAPL"])
    assert tickers == ["X", "Y", "AAPL"] and src.startswith("캐시")


def test_일부_지수만_수집되면_실패로_간주(tmp_path, monkeypatch):
    monkeypatch.setattr(uu, "fetch_live", lambda: ([f"S{i}" for i in range(500)], {"S&P500": 500}))
    tickers, src = uu.load_universe(tmp_path, extras=["AAPL"])
    assert src == "내장 기본 목록"            # 500개만으로는 S&P1500 기대치 미달
