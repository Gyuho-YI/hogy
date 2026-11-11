@echo off
REM ===================================================================
REM  장 마감 후 스크리닝 배치
REM    국내: run_batch.bat kr   (작업 스케줄러: 평일 18:35)
REM    해외: run_batch.bat us   (작업 스케줄러: 화~토 07:10)
REM  결과 output\plans_*.json → 웹앱이 자동 반영(재시작 불필요)
REM ===================================================================
chcp 65001 > nul
setlocal
set MARKET=%1
if "%MARKET%"=="" (echo 사용법: run_batch.bat kr^|us & exit /b 1)
cd /d "%~dp0..\.."
call scripts\windows\secrets.bat
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
cd screener

echo [%date% %time%] %MARKET% 배치 시작 >> ..\logs\batch.log
if /i "%MARKET%"=="kr" (
  if exist ..\output\journal_stats.csv (
    python plan_screener.py --account %ACCOUNT_KR% --stats ..\output\journal_stats.csv >> ..\logs\batch.log 2>&1
  ) else (
    python plan_screener.py --account %ACCOUNT_KR% >> ..\logs\batch.log 2>&1
  )
) else if /i "%MARKET%"=="us" (
  python us_screener.py >> ..\logs\batch.log 2>&1
) else (
  echo kr 또는 us 만 지원 & exit /b 1
)
echo [%date% %time%] %MARKET% 배치 종료(코드 %errorlevel%) >> ..\logs\batch.log
