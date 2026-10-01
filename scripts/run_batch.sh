#!/usr/bin/env bash
# 장 마감 후 스크리닝 배치. cron 예시(평일, KST 서버 기준):
#   35 18 * * 1-5  /home/<user>/hogy/scripts/run_batch.sh kr >> /home/<user>/hogy/logs/batch.log 2>&1
#   10 7  * * 2-6  /home/<user>/hogy/scripts/run_batch.sh us >> /home/<user>/hogy/logs/batch.log 2>&1
# 결과: output/plans_{kr,us}.json → 웹앱이 파일 변경을 감지해 자동 반영(재기동 불필요)
set -euo pipefail

MARKET="${1:?사용법: run_batch.sh kr|us}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT_KR="${ACCOUNT_KR:-30000000}"     # 국내 계좌 평가금액(원)
ACCOUNT_US="${ACCOUNT_US:-20000}"        # 해외 계좌 평가금액(USD)

cd "$ROOT/screener"
source "$ROOT/.venv/bin/activate"
echo "[$(date '+%F %T')] $MARKET 배치 시작"

case "$MARKET" in
  kr)
    # 실전 일지 CSV(웹앱 '켈리용 CSV 내보내기')가 있으면 켈리 사이징에 사용
    STATS="$ROOT/output/journal_stats.csv"
    if [[ -f "$STATS" ]]; then
      python plan_screener.py --account "$ACCOUNT_KR" --stats "$STATS"
    else
      python plan_screener.py --account "$ACCOUNT_KR"
    fi
    ;;
  us)
    ACCOUNT_US="$ACCOUNT_US" python us_screener.py
    ;;
  *) echo "kr 또는 us 만 지원"; exit 1 ;;
esac
echo "[$(date '+%F %T')] $MARKET 배치 완료"
