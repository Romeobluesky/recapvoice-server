@echo off

:: Nginx 시작
echo Starting Nginx...
packet_wave\nginx\nginx.exe -c packet_wave\nginx\conf\nginx.conf
if %ERRORLEVEL% neq 0 (
    echo Failed to start Nginx.
    exit /b
)

:: MongoDB 시작
echo Starting MongoDB...
packet_wave\mongodb\bin\mongod.exe --dbpath packet_wave\mongodb\data --logpath packet_wave\mongodb\log\mongodb.log --port 27017 --bind_ip 127.0.0.1 --fork
if %ERRORLEVEL% neq 0 (
    echo Failed to start MongoDB.
    exit /b
)

:: Python 스키마 초기화 및 프로그램 실행
echo Initializing MongoDB schemas...
python packet_wave\apply_schemas.py
if %ERRORLEVEL% neq 0 (
    echo Failed to initialize schemas.
    exit /b
)

echo Starting Python program...
python packet_wave\dashboard.py
