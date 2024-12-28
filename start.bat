@echo off
setlocal enabledelayedexpansion

:: 환경 모드 확인
for /f "tokens=1,2 delims==" %%A in ('findstr /b "mode" settings.ini') do (
    set "env_mode=%%B"
    set "env_mode=!env_mode: =!"
    echo Mode is: !env_mode!
)

:: 경로 설정
if "!env_mode!"=="development" (
    :: 개발 환경 경로 - settings.ini에서 직접 경로 읽기
    for /f "tokens=1,2 delims==" %%A in ('findstr /b "dir_path" settings.ini') do (
        set "dir_path=%%B"
        set "dir_path=!dir_path: =!"
        echo Found dir_path: !dir_path!
    )
    set "WORK_DIR=!dir_path!"
) else (
    :: 배포 환경 경로
    set "WORK_DIR=%ProgramFiles%\Recap Voice"
)

:: nginx.exe 존재 여부 확인
if not exist "!WORK_DIR!\nginx\nginx.exe" (
    echo Error: nginx.exe not found at !WORK_DIR!\nginx\nginx.exe
    goto error
)

:: 작업 디렉토리 생성
if not exist "!WORK_DIR!\logs" mkdir "!WORK_DIR!\logs"
if not exist "!WORK_DIR!\temp" mkdir "!WORK_DIR!\temp"
if not exist "!WORK_DIR!\temp\client_body_temp" mkdir "!WORK_DIR!\temp\client_body_temp"

:: Nginx 시작
echo Starting Nginx from: !WORK_DIR!\nginx\nginx.exe
start "" "!WORK_DIR!\nginx\nginx.exe" -c "!WORK_DIR!\nginx\conf\nginx.conf"
if !ERRORLEVEL! neq 0 (
    echo Failed to start Nginx.
    goto error
)

:: MongoDB 시작
echo Starting MongoDB...
start "" /b "!WORK_DIR!\mongodb\bin\mongod.exe" --dbpath "!WORK_DIR!\mongodb\data\db" --logpath "!WORK_DIR!\mongodb\log\mongodb.log" --logappend
if %ERRORLEVEL% neq 0 (
    echo Failed to start MongoDB.
    goto error
)

:: NestJS 시작
echo Starting NestJS...
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo npm is not installed.
    goto error
)

cd /d "!WORK_DIR!\packetwave_client"
npm run start:dev
if %ERRORLEVEL% neq 0 (
    echo Failed to start NestJS
    goto error
)

goto :end

:error
echo Error occurred. Check the logs for details.
pause
exit /b 1

:end
echo All services started successfully.
if "!env_mode!"=="development" (
    echo Running in development mode
    echo Work directory is: !WORK_DIR!
) else (
    echo Running in production mode
)
exit /b 0
