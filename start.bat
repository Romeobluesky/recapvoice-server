@echo off

:: Nginx 시작
echo Starting Nginx...
nginx\nginx.exe -c nginx\conf\nginx.conf
if %ERRORLEVEL% neq 0 (
    echo Failed to start Nginx.
    exit /b
)

:: MongoDB 시작
echo Starting MongoDB...
mongodb\bin\mongod.exe --dbpath mongodb\data --logpath mongodb\log\mongodb.log --port 27017 --bind_ip 127.0.0.1 --fork
if %ERRORLEVEL% neq 0 (
    echo Failed to start MongoDB.
    exit /b
)

:: Python 스키마 초기화 및 프로그램 실행
echo Initializing MongoDB schemas...
python apply_schemas.py
if %ERRORLEVEL% neq 0 (
    echo Failed to initialize schemas.
    exit /b
)

echo Starting Python program...
python dashboard.py
