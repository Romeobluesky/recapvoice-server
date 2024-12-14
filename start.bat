@echo off

:: settings.ini에서 경로 읽기
setlocal enabledelayedexpansion
for /f "tokens=1,2 delims== " %%A in ('findstr "dir_path" settings.ini') do (
    set "%%A=%%B"
)

:: 읽은 값 확인
echo Work directory is: %dir_path%
::pause

:: 필요한 디렉토리 생성
if not exist "%dir_path%\packet_wave\logs" mkdir "%dir_path%\packet_wave\logs"
if not exist "%dir_path%\packet_wave\temp" mkdir "%dir_path%\packet_wave\temp"
if not exist "%dir_path%\packet_wave\temp\client_body_temp" mkdir "%dir_path%\packet_wave\temp\client_body_temp"

:: Nginx 시작
echo Starting Nginx...
start "" "%dir_path%\packet_wave\nginx\nginx.exe" -c "%dir_path%\packet_wave\nginx\conf\nginx.conf"
if %ERRORLEVEL% neq 0 (
    echo Failed to start Nginx.
    exit /b
)

:: MongoDB 독립 실행
echo Starting MongoDB...
start "" /b "%dir_path%\packet_wave\mongodb\bin\mongod.exe" --dbpath "%dir_path%\packet_wave\mongodb\data\db" --logpath "%dir_path%\packet_wave\mongodb\log\mongodb.log" --logappend
if %ERRORLEVEL% neq 0 (
    echo Failed to start MongoDB.
    exit /b
)

:: NestJS npm 시작
echo Starting NestJS...
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo npm is not installed.
    exit /b
)
cd /d %dir_path%\packetwave_client
npm run start:dev
if %ERRORLEVEL% neq 0 (
    echo Failed to start NestJS
    exit /b
)

exit
