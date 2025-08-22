@echo off
REM MongoDB 백업 스크립트 - PacketWave 시스템
REM 사용법: backup_mongodb.bat

echo ================================
echo MongoDB 백업 시스템 시작
echo ================================

REM 현재 시간을 파일명에 사용
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do if not "%%I"=="" set datetime=%%I
set backuptime=%datetime:~0,8%_%datetime:~8,6%

echo [INFO] 백업 시작 시간: %date% %time%
echo [INFO] Python 백업 스크립트 실행 중...

python mongodb_backup.py

if %errorlevel% equ 0 (
    echo.
    echo ================================
    echo ✓ 백업 성공적으로 완료!
    echo ================================
    echo [INFO] 백업 파일 위치: backup\mongodb_backup_%backuptime%
    echo [INFO] 복원 방법: python backup\mongodb_backup_%backuptime%\restore.py
    echo.
    pause
) else (
    echo.
    echo ================================
    echo ✗ 백업 실패!
    echo ================================
    echo [ERROR] 오류가 발생했습니다. 로그를 확인하세요.
    echo.
    pause
)