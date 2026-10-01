# hogy — AI 보조 주식 스크리너

| 파일 | 대상 | 1차 필터 철학 |
|---|---|---|
| `screener/us_screener.py` | 미국 | 펀더멘털(분기 매출 YoY) + 미너비니 트렌드 템플릿 + RS Rating + VCP |
| `screener/kr_screener.py` | 국내 | 거래대금 폭발 + 외국인·기관 수급 + 20/60/120 정배열 + 과열 배제 + VCP |
| `screener/kr_accumulation.py` | 국내 | 눌림 매집 탐지: 주가 정체 + 기관·외국인 누적 순매수(상장주식 대비) + 숏커버 배제 → 점화 신호 |
| `screener/accumulation.py` | 공통 | 매집 단계 판정 순수 로직(매집 진행 / 점화 대기 / 점화) |
| `screener/entry_backtest.py` | 국내 | 진입 시점 비교 백테스트: 선진입 vs 점화진입 vs 분할진입(1/3+2/3), 동일 청산 규칙 |
| `screener/support.py` | 공통 | 지지 구간 산출(돌파피벗·AVWAP·매물대·점화봉·20일선 병합) + 추격매수 판정·포지션 사이징 |
| `screener/common.py` | 공통 | YoY 예외 처리(분모 0·적자 전환), 트렌드 템플릿, VCP 탐지 |

```bash
pip install -r requirements.txt
cd screener && python us_screener.py   # 또는 python kr_screener.py (장 마감 후 실행 권장)
```

## 국내 2단계: LLM 테마 태깅 프롬프트

`kr_candidates_YYYYMMDD.csv` 와 최근 3일 뉴스/공시(DART) 헤드라인을 함께 붙여 넣습니다.

```
너는 국내 증시 테마 애널리스트다. 아래 후보 종목 각각에 대해
1) 상승 재료(테마명) 2) 재료 유형(실적/정책/수주/임상/단순 기대감) 3) 동일 테마 내 대장주 여부
4) 재료 지속성(1~5점, 근거 1줄) 5) 이미 노출된 악재(유상증자·CB 전환·대주주 매도)를 표로 정리하라.
뉴스 근거가 없는 항목은 '확인 불가'로 표기하고 추정하지 마라.
```

> 본 코드는 학습·연구용이며 투자 권유가 아닙니다.
