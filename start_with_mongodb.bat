@echo off
echo ===== 시스템 초기화 중... =====
echo MongoDB 서버 확인 및 시작...

python ensure_mongodb.py --wait 20
if %ERRORLEVEL% NEQ 0 (
    echo MongoDB 서버 시작 실패! 
    echo 수동으로 MongoDB 서버를 시작하고 다시 시도하세요.
    pause
    exit /b 1
)

echo ===== 메인 프로그램 시작 =====
python dashboard.py
if %ERRORLEVEL% NEQ 0 (
    echo 프로그램 실행 중 오류가 발생했습니다.
    pause
) 