@echo off

:: 필요한 디렉토리 생성
if not exist "D:\Work_state\packet_wave\logs" mkdir "D:\Work_state\packet_wave\logs"
if not exist "D:\Work_state\packet_wave\temp" mkdir "D:\Work_state\packet_wave\temp"
if not exist "D:\Work_state\packet_wave\temp\client_body_temp" mkdir "D:\Work_state\packet_wave\temp\client_body_temp"

:: Nginx 시작
echo Starting Nginx...
start "" "D:\Work_state\packet_wave\nginx\nginx.exe" -c "D:\Work_state\packet_wave\nginx\conf\nginx.conf"
if %ERRORLEVEL% neq 0 (
    echo Failed to start Nginx.
    exit /b
)

:: MongoDB 독립 실행
echo Starting MongoDB...
start "" /b "D:\Work_state\packet_wave\mongodb\bin\mongod.exe" --dbpath "D:\Work_state\packet_wave\mongodb\data\db" --logpath "D:\Work_state\packet_wave\mongodb\log\mongodb.log" --logappend
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
cd /d D:\Work_state\packetwave_client
npm run start:dev
if %ERRORLEVEL% neq 0 (
    echo Failed to start NestJS
    exit /b
)

exit
