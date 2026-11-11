"""섹터·테마 레이더 계산 로직 검증(네트워크 없이 가상 데이터)."""
import json
import types

import numpy as np
import pandas as pd
import pytest

import sector_data
import sector_radar as sr


def make_daily(days=21, surge_sector="전기전자"):
    """섹터 3개 × 종목 4개. 마지막 날 surge_sector 거래대금만 4배, 상승."""
    rows = []
    dates = [f"202609{d:02d}" for d in range(1, days + 1)]
    for di, d in enumerate(dates):
        last = di == days - 1
        for sec in ["전기전자", "화학", "운수장비"]:
            for k in range(4):
                v = 100e8 * (4 if (last and sec == surge_sector) else 1)
                ch = 3.0 if (last and sec == surge_sector) else (-1.0 if k % 2 else 0.5)
                rows.append({"date": d, "code": f"{sec}{k}", "name": f"{sec}종목{k}", "sector": sec,
                             "change": ch, "value": v * (1 + 0.1 * k)})
    return pd.DataFrame(rows)


def test_쏠림_섹터가_1위_비중기준_배수():
    out = sr.sector_flow(make_daily())
    top = out.iloc[0]
    assert top["sector"] == "전기전자"
    # 비중 1/3 → 4/6 = 2/3 이므로 배수 2.0 (금액 4배가 아니라 '비중' 2배)
    assert top["ratio"] == pytest.approx(2.0, rel=1e-6)
    assert top["breadth"] == 1.0
    assert top["flag"] in ("유입", "신규 유입")
    assert top["leaders"][0]["code"] == "전기전자3"   # 거래대금 최대 종목
    assert out.iloc[-1]["ratio"] < 1                  # 나머지 섹터는 비중 감소


def test_데이터_1일뿐이면_오류():
    d = make_daily()
    with pytest.raises(ValueError):
        sr.sector_flow(d[d["date"] == d["date"].max()])


def test_분모0_섹터는_배수_None():
    d = make_daily()
    new = {"date": d["date"].max(), "code": "N1", "name": "신규", "sector": "신규업종", "change": 1.0, "value": 50e8}
    out = sr.sector_flow(pd.concat([d, pd.DataFrame([new])], ignore_index=True))
    row = out[out["sector"] == "신규업종"].iloc[0]
    assert row["ratio"] is None or (isinstance(row["ratio"], float) and np.isnan(row["ratio"]))


def test_테마_매칭과_집계():
    surge = pd.DataFrame([
        {"code": "A", "name": "에이", "change": 12.0, "value": 900e8, "value_ratio": 5.0},
        {"code": "B", "name": "비", "change": 8.0, "value": 300e8, "value_ratio": 3.0},
        {"code": "C", "name": "씨", "change": 2.0, "value": 200e8, "value_ratio": 2.0},
    ])
    heads = {
        "A": ["에이, SMR 수주 기대", "원전 수출 확대 수혜", "에이 실적"],
        "B": ["비, 원자력 협력 MOU", "SMR 부품 공급"],
        "C": ["씨, 신작 게임 출시"],            # 1건 → min_hits(2) 미달로 제외
    }
    out = sr.theme_flow(surge, heads, sr.DEFAULT_THEMES)
    assert list(out["theme"]) == ["원전·SMR"]
    assert out.iloc[0]["stocks"] == 2
    assert out.iloc[0]["members"][0]["code"] == "A"
    assert "SMR" in out.iloc[0]["members"][0]["headline"] or "원전" in out.iloc[0]["members"][0]["headline"]


def test_사용자_테마사전_병합(tmp_path):
    p = tmp_path / "themes.json"
    p.write_text(json.dumps({"유리기판": ["유리기판", "글라스기판"]}, ensure_ascii=False), encoding="utf-8")
    themes = sr.load_themes(p)
    assert "유리기판" in themes and "방산" in themes
    p.write_text("{깨진 json", encoding="utf-8")
    assert sr.load_themes(p) == sr.DEFAULT_THEMES


def test_ETF_거래대금배수와_상대강도():
    idx = pd.bdate_range("2026-04-01", periods=80)
    def etf(last_mult, slope):
        c = pd.Series(np.linspace(100, 100 * (1 + slope), 80), index=idx)
        v = pd.Series(1e6, index=idx); v.iloc[-1] = 1e6 * last_mult
        return pd.DataFrame({"Close": c, "Volume": v})
    prices = {"SMH": etf(3.0, 0.3), "XLU": etf(1.0, 0.0)}
    out = sr.etf_flow(prices, {"SMH": "반도체", "XLU": "유틸리티"}, etf(1.0, 0.1))
    top = out.iloc[0]
    assert top["ticker"] == "SMH"
    assert top["ratio"] == pytest.approx(3.0, rel=0.05)
    assert top["rs_1m"] > 0 and out.iloc[1]["rs_1m"] < 0


def test_국내_실행흐름_가짜데이터(tmp_path, monkeypatch):
    """pykrx·뉴스 RSS 를 가짜로 대체해 수집 → 계산 → JSON 저장 전체 흐름 검증."""
    daily = make_daily()
    dates = sorted(daily["date"].unique())
    rss = ("<rss><channel>"
           "<item><title>전기전자3 HBM 공급 확대 - 한국경제</title></item>"
           "<item><title>전기전자3, 반도체 수주 - 매일경제</title></item>"
           "</channel></rss>").encode("utf-8")

    def fake_index(start, end, code):
        return pd.DataFrame(index=pd.to_datetime(dates))

    def fake_cls(date, mkt):
        t = daily[daily["date"] == date]
        if mkt == "KOSDAQ":
            return pd.DataFrame(columns=["종목명", "업종명"])
        return pd.DataFrame({"종목명": t["name"].values, "업종명": t["sector"].values}, index=t["code"].values)

    def fake_ohlcv(date, market):
        t = daily[daily["date"] == date]
        return pd.DataFrame({"거래대금": t["value"].values, "등락률": t["change"].values}, index=t["code"].values)

    fake_stock = types.SimpleNamespace(get_index_ohlcv=fake_index, get_market_sector_classifications=fake_cls,
                                       get_market_ohlcv=fake_ohlcv)
    monkeypatch.setitem(__import__("sys").modules, "pykrx", types.SimpleNamespace(stock=fake_stock))
    monkeypatch.setattr(sector_data.time, "sleep", lambda *_: None)

    class Resp:
        content = rss
        def raise_for_status(self): pass
    monkeypatch.setattr(sector_data.requests, "get", lambda *a, **k: Resp())

    path = sector_data.run_kr(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["market"] == "KR"
    assert data["sectors"][0]["sector"] == "전기전자"
    assert data["themes"][0]["theme"] == "반도체·HBM"
    assert data["themes"][0]["members"][0]["headline"].endswith("공급 확대")   # ' - 언론사' 제거
    assert data["hotCodes"]["전기전자3"].startswith("주도")
    assert "NaN" not in path.read_text(encoding="utf-8")


def test_뉴스_실패해도_빈목록(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("blocked")
    monkeypatch.setattr(sector_data.requests, "get", boom)
    assert sector_data.fetch_headlines("삼성전자") == []


def test_대형_섹터가_평소수준이면_상위에_오르지_않음():
    """비중이 큰 섹터(평소 수준)보다 비중이 작아도 자금이 몰린 섹터가 위."""
    d = make_daily(surge_sector="화학")
    big = d["sector"] == "전기전자"
    d.loc[big, "value"] *= 10          # 전기전자: 평소에도 비중이 압도적
    out = sr.sector_flow(d)
    assert out.iloc[0]["sector"] == "화학"
    assert out[out["sector"] == "전기전자"].iloc[0]["ratio"] < 1


def test_쏠림_배수는_크기로_반영():
    """거래대금 3배 몰린 ETF 가 상대강도만 좋은 ETF(1.2배)보다 위."""
    idx = pd.bdate_range("2026-04-01", periods=80)
    def etf(last_mult, slope):
        c = pd.Series(np.linspace(100, 100 * (1 + slope), 80), index=idx)
        v = pd.Series(1e6, index=idx); v.iloc[-1] = 1e6 * last_mult
        return pd.DataFrame({"Close": c, "Volume": v})
    prices = {"URA": etf(3.4, 0.05), "KWEB": etf(1.2, 0.15), "XLU": etf(1.0, 0.0)}
    out = sr.etf_flow(prices, {"URA": "우라늄", "KWEB": "중국 인터넷", "XLU": "유틸리티"}, etf(1.0, 0.02))
    assert out.iloc[0]["ticker"] == "URA"
