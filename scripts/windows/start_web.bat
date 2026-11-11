@echo off
REM ===================================================================
REM  웹앱 실행 → 브라우저에서 http://localhost:8080
REM  로그온 시 자동 실행: 작업 스케줄러 '로그온할 때' 트리거로 등록
REM ===================================================================
chcp 65001 > nul
setlocal
cd /d "%~dp0..\.."
call scripts\windows\secrets.bat || (echo secrets.bat 가 없습니다. setup.bat 먼저 실행 & pause & exit /b 1)

set APP_DATA_DIR=%CD%\output
set APP_DB_PATH=%CD%\data\journal
REM 127.0.0.1 에만 바인딩: 같은 네트워크의 다른 PC 에서 접근 불가
java -Xmx384m -jar web\target\cockpit-0.1.0.jar --server.address=127.0.0.1 >> logs\web.log 2>&1
