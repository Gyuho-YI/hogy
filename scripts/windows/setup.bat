@echo off
REM ===================================================================
REM  최초 1회 설치: Python 가상환경 + 패키지 + 웹앱 빌드
REM  사전 설치: Python 3.11+, JDK 17+ (Temurin), Git
REM  실행: 저장소 폴더에서 scripts\windows\setup.bat 더블클릭
REM ===================================================================
chcp 65001 > nul
setlocal
cd /d "%~dp0..\.."

echo [1/3] Python 가상환경 생성
if not exist .venv python -m venv .venv || goto :fail
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip > nul
pip install -r requirements.txt || goto :fail

echo [2/3] 웹앱 빌드 (Maven 설치 불필요: mvnw 사용)
cd web
call mvnw.cmd -B -q -DskipTests package || goto :fail
cd ..

echo [3/3] 폴더 준비
if not exist output mkdir output
if not exist data mkdir data
if not exist logs mkdir logs
if not exist scripts\windows\secrets.bat copy scripts\windows\secrets.example.bat scripts\windows\secrets.bat > nul

echo.
echo 완료. scripts\windows\secrets.bat 를 열어 비밀번호와 계좌 금액을 수정하세요.
pause
exit /b 0

:fail
echo 설치 실패. 위 오류 메시지를 확인하세요.
pause
exit /b 1
