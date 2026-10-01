# 개인용 트레이딩 콕핏 A–Z 가이드

> 목표: **나 혼자** 매일 저녁 스크리닝 결과를 보고, 다음 날 주문을 내고, 실제 매매를 기록해 전략을 개선하는 루프를 만듭니다.
> 공개 서비스가 아니므로 "외부에 노출하지 않는 것"이 가장 강력한 보안입니다.

---

## A. 전체 구조

```
┌──────────── 집 PC / 미니PC (한국 IP, 24시간 가동) ────────────┐
│                                                               │
│  [cron] 18:35 평일 ─▶ scripts/run_batch.sh kr                  │
│  [cron] 07:10 화~토 ─▶ scripts/run_batch.sh us                 │
│        └─ Python 스크리너 ─▶ output/plans_kr.json, plans_us.json│
│                                   │ (파일 변경 자동 감지)      │
│  [systemd] Spring Boot 웹앱 ◀─────┘                            │
│        ├─ 대시보드: KPI 5 + 매매 계획표 + 차트                 │
│        └─ 매매일지(H2 파일 DB) ─▶ 켈리용 CSV ─▶ 다음 배치 입력  │
└───────────────────────────────▲───────────────────────────────┘
                                │ Tailscale(사설 VPN) — 포트 개방 없음
                       스마트폰 / 회사 노트북
```

| 계층 | 기술 | 역할 |
|---|---|---|
| 분석 | Python 3.11, pandas, pykrx, yfinance | 스크리닝·매매 계획·하프켈리 |
| 연동 | JSON 파일 (`output/`) | 두 언어를 느슨하게 연결. DB 불필요 |
| 서비스 | Java 17, Spring Boot 3.5, Thymeleaf, Spring Security | 화면·로그인·일지 |
| 시각화 | Chart.js 4 (앱에 내장, CDN 의존 없음) | 가격+매수구간 차트, 산점도, 월별 손익 |
| 저장 | H2 파일 DB (`data/journal.mv.db`) | 매매일지. 백업은 파일 복사 |
| 접속 | Tailscale | 외부 공개 없이 모바일 접속 |

## B. 왜 이 구조인가 (의사결정 근거)

- **배치 위치 = 한국 IP**: KRX 데이터 서버는 해외 클라우드 IP 를 차단하는 경우가 있습니다. 집 PC/미니PC 가 가장 안정적이고 비용 0원입니다.
- **Python ↔ Java 를 JSON 파일로 분리**: 분석 로직은 Python 생태계가 압도적이고, 웹은 익숙한 Spring 으로. 한쪽을 고쳐도 다른 쪽에 영향이 없습니다.
- **H2 파일 DB**: 1인 사용·수천 건 규모에서는 MySQL/PostgreSQL 서버 운영이 과잉입니다.
- **Tailscale**: 도메인·HTTPS 인증서·방화벽 설정 없이 내 기기끼리만 접속. 로그인은 2차 방어선입니다.

## C. 디렉터리

```
hogy/
├── screener/        Python 스크리너 (common, accumulation, support, trade_plan, export ...)
├── web/             Spring Boot 웹앱
│   └── src/main/java/com/hogy/cockpit/
│       ├── config/      AppProperties, SecurityConfig (1인 로그인)
│       ├── plan/        PlanItem, PlanSnapshot, PlanRepository (JSON 로더, 변경 감지)
│       ├── dashboard/   Kpi, KpiService (총 위험·현금 비중·손익비)
│       ├── journal/     Trade(엔티티), JournalService, JournalStats(하프켈리)
│       ├── web/         PageController(화면), ApiController(차트 JSON)
│       └── util/        SafeMath (0 나누기·적자 전환 처리)
├── scripts/run_batch.sh   배치 실행
├── deploy/                systemd 서비스, 환경변수 예시
├── output/                배치 결과 JSON (git 제외)
└── data/                  매매일지 DB (git 제외, 백업 대상)
```

## D. 설치 (최초 1회, 우분투 미니PC 기준 — 윈도우는 WSL2 로 동일)

```bash
sudo apt install -y openjdk-17-jdk maven python3-venv git
git clone <저장소> ~/hogy && cd ~/hogy

# Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 웹앱 빌드
cd web && mvn -B package && cd ..

# 비밀값
cp deploy/cockpit.env.example deploy/cockpit.env && chmod 600 deploy/cockpit.env
vi deploy/cockpit.env      # APP_PASSWORD, APP_REMEMBER_KEY 를 긴 임의 문자열로
```

## E. 첫 실행 확인

```bash
# 1) 배치 수동 실행 (장 마감 후)
ACCOUNT_KR=30000000 scripts/run_batch.sh kr
ls output/              # plans_kr.json 생성 확인

# 2) 웹앱 실행
cd web && APP_DATA_DIR=../output APP_PASSWORD=임시비번 java -jar target/cockpit-0.1.0.jar
# 브라우저: http://localhost:8080  (ID: owner)
```

## F. 상시 운영 (자동화)

```bash
# 웹앱: 부팅 시 자동 실행 (deploy/cockpit.service 의 경로·User 를 본인 환경으로 수정)
sudo cp deploy/cockpit.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now cockpit
journalctl -u cockpit -f        # 로그

# 배치: crontab -e  (서버 시간대가 KST 인지 먼저 확인: timedatectl)
35 18 * * 1-5  /home/hogy/hogy/scripts/run_batch.sh kr >> /home/hogy/hogy/logs/batch.log 2>&1
10 7  * * 2-6  /home/hogy/hogy/scripts/run_batch.sh us >> /home/hogy/hogy/logs/batch.log 2>&1
```

- 국내: 투자자별 수급이 확정되는 18시 이후.
- 해외: 미국 장 마감(KST 05:00/06:00, 서머타임에 따라) 이후 07시대. 화~토 실행 = 미국 월~금.

## G. 모바일 접속 (Tailscale)

1. 서버와 스마트폰에 Tailscale 설치 → 같은 계정 로그인
2. 서버의 Tailscale 주소 확인: `tailscale ip -4` (예: 100.x.y.z)
3. 스마트폰 브라우저: `http://100.x.y.z:8080` → 홈 화면에 추가
4. (선택) HTTPS: `sudo tailscale serve --bg 8080` → `https://<기기명>.<tailnet>.ts.net`

> 개인 도메인으로 붙이고 싶다면 Cloudflare Tunnel + Cloudflare Access(이메일 OTP) 조합을 권장합니다.
> 공유기 포트포워딩으로 8080 을 직접 여는 방식은 권장하지 않습니다.

## H. 하루 사용 루틴 (5분)

| 시각 | 화면 | 할 일 |
|---|---|---|
| 18:40 | 대시보드 KPI | **총 위험 ≤ 6%, 현금 비중 ≥ 0%** 확인. 초과면 손익비 낮은 종목부터 제외 |
| 18:42 | 매매 계획표 | '매수 가능' → 다음 날 지정가 / '돌파 대기' → Buy Stop / '지정가 대기' → 눌림 지정가 |
| 18:45 | 종목 차트 | 매수 구간 밴드·손절선·목표선 눈으로 확인, 메모(손절 근거) 확인 |
| 체결 후 | 일지 | 계획표의 '일지 기록' → 값이 자동 채워짐 → 실제 체결가로 수정 후 저장 |
| 청산 시 | 일지 | 청산일·청산가 입력 |
| 월 1회 | 일지 | '켈리용 CSV 내보내기' → `output/journal_stats.csv` 로 저장 → 다음 배치부터 실전 승률로 사이징 |

## I. 화면 설계 원칙 (SD-ADP)

- **5초의 법칙**: 최상단 KPI 5개만 보고 "오늘 몇 종목을, 얼마의 위험으로" 판단
  1. 오늘 주문 대상 / 전체 후보
  2. 총 위험(Heat) — 아이콘+라벨(✓ 안전 / ⚠ 주의 / ⛔ 위험)
  3. 평균 손익비(2차 목표 기준)
  4. 체결 후 현금 비중 — 음수면 계좌 초과 경고
  5. 실전 기대값(일지)
- **F-pattern**: 좌측 계획표(실행 순 정렬) → 우측 선택 종목 차트 → 하단 후보 분포
- **반응형**: 고정 폭 없음. KPI 2열(모바일) → 3열(태블릿) → 5열(데스크톱), 본문 1단 → 2단(1024px↑). 모바일에선 보조 열 숨김
- **다크모드**: OS 설정 자동 대응

## J. 데이터 계약 (JSON 스키마)

`output/plans_{kr|us}.json` — Python `export.plan_record()` ↔ Java `PlanItem` 1:1

```json
{ "market": "KR", "generatedAt": "2026-10-01T18:36:02", "account": 30000000,
  "items": [{ "code": "000660", "name": "SK하이닉스", "stage": "점화", "action": "지금 매수 가능",
              "close": 214500, "buyLow": 204000, "buyHigh": 214000, "stop": 197400, "riskPct": 0.078,
              "t1": 247500, "t2": 264500, "addTrigger": null, "weightPct": 25.0,
              "sharesNow": 35, "sharesAdd": 0, "edgeSource": "...", "notes": ["..."],
              "history": [{"d": "2026-05-01", "c": 198000}] }] }
```

- 계산 불가 값은 `null` (NaN/Infinity 금지 → Jackson 파싱 오류 방지)
- 필드 추가는 자유(Java 쪽 `@JsonIgnoreProperties(ignoreUnknown = true)`), 이름 변경은 양쪽 동시 수정

## K. 예외 처리 규칙

- 0 나누기: 계좌 0/미기재 → 비율 KPI 는 `-` 표시
- 전월 대비 손익: 전월 손실 → `|전월|` 로 나누고 흑자전환/적자축소/적자확대, 이익→손실은 적자전환 (`SafeMath.growth`, Python `safe_yoy` 와 동일)
- 손익비: 평균손실 0 이면 계산 불가 → 켈리 미적용
- 시장 코드: `kr`/`us` 외 404 (파일 경로 조작 방지)

## L. 보안 체크리스트

- [ ] `APP_PASSWORD`, `APP_REMEMBER_KEY` 환경변수 설정 (미설정 시 기동마다 임시 비밀번호 생성)
- [ ] `deploy/cockpit.env` 권한 600, git 제외 확인
- [ ] 외부 포트 개방 없음 (Tailscale/Cloudflare Access 만)
- [ ] 증권사 계정·API 키는 이 앱에 저장하지 않음 (주문은 HTS/MTS 에서 수동)

## M. 백업

```bash
# 매주: 일지 DB + 배치 결과
tar czf ~/backup/cockpit_$(date +%F).tgz -C ~/hogy data output
```

H2 파일은 웹앱 실행 중에도 복사 가능하지만, 안전하게는 `systemctl stop cockpit` 후 복사.

## N. 테스트

```bash
cd web && mvn test        # 16건: SafeMath, 하프켈리 통계, KPI 계산, 로그인/대시보드/일지 흐름
```

## O. 장애 대응

| 증상 | 원인 | 조치 |
|---|---|---|
| 대시보드 "아직 스크리닝 결과가 없습니다" | 배치 미실행/실패 | `logs/batch.log` 확인, 수동 실행 |
| KRX 403/접속 실패 | 해외 IP·KRX 점검 | 한국 IP 서버에서 실행, 시간 변경 후 재시도 |
| 로그인 불가 | 비밀번호 미설정 → 임시 비밀번호 | `journalctl -u cockpit` 에서 임시 비밀번호 확인 후 env 설정 |
| 차트 미표시 | JS 오류 | 브라우저 개발자도구 콘솔 확인 |

## P. 확장 로드맵 (필요해질 때만)

1. **텔레그램 알림**: 배치 완료 시 "매수 가능 N종목, Heat X%" 푸시 (Python `requests` 로 Bot API 호출)
2. **보유 종목 손절 경보**: 배치에서 일지 보유 종목의 종가 ≤ 손절가면 알림
3. **증권사 Open API 시세 연동**(한국투자증권 KIS 등): 장중 현재가 반영. 주문 자동화는 실수 비용이 크므로 마지막 단계에서 검토
4. **해외 백테스트**: `entry_backtest.py` 를 yfinance 데이터로 확장해 해외도 켈리 사이징
