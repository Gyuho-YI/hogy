@echo off
REM ===================================================================
REM  작업 스케줄러 일괄 등록 (현재 사용자 권한, 관리자 권한 불필요)
REM  - 웹앱: 로그온 시 자동 실행(시작프로그램 폴더)
REM  - 국내 배치: 평일 18:35 / 해외 배치: 화~토 07:10
REM  삭제: schtasks /Delete /TN Cockpit_Batch_KR /F (US 동일), 시작프로그램의 cockpit_web.bat 삭제
REM ===================================================================
chcp 65001 > nul
set ROOT=%~dp0
REM 웹앱: 시작프로그램 폴더에 등록(관리자 권한 불필요, 로그온 시 최소화 창으로 실행)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
> "%STARTUP%\cockpit_web.bat" echo @start "" /min "%ROOT%start_web.bat"
schtasks /Create /F /TN "Cockpit_Batch_KR" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:35 /TR "\"%ROOT%run_batch.bat\" kr"
schtasks /Create /F /TN "Cockpit_Batch_US" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 07:10 /TR "\"%ROOT%run_batch.bat\" us"
echo.
echo 등록 완료. 확인: 작업 스케줄러에서 Cockpit_Batch_*, 시작프로그램 폴더에서 cockpit_web.bat
pause
