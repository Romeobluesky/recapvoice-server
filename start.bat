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
    :: 배포 환경 경로 (x86)
    set "WORK_DIR=%ProgramFiles(x86)%\Recap Voice"
)

:: nginx.exe 존재 여부 확인
if not exist "!WORK_DIR!\nginx\nginx.exe" (
    echo Error: nginx.exe not found at !WORK_DIR!\nginx\nginx.exe
    goto error
)

:: Nginx 방화벽 허용 설정 (기존 규칙 삭제 후 재등록)
echo Configuring Windows Firewall for Nginx...

:: 기존 방화벽 규칙 삭제
netsh advfirewall firewall delete rule name="Nginx HTTP" >nul 2>&1
netsh advfirewall firewall delete rule name="Nginx HTTPS" >nul 2>&1

:: 방화벽 인바운드 규칙 추가
netsh advfirewall firewall add rule name="Nginx HTTP" dir=in action=allow program="!WORK_DIR!\nginx\nginx.exe" enable=yes
netsh advfirewall firewall add rule name="Nginx HTTPS" dir=in action=allow protocol=TCP localport=443 action=allow program="!WORK_DIR!\nginx\nginx.exe" enable=yes

:: 방화벽 아웃바운드 규칙 추가
netsh advfirewall firewall add rule name="Nginx HTTP" dir=out action=allow program="!WORK_DIR!\nginx\nginx.exe" enable=yes
netsh advfirewall firewall add rule name="Nginx HTTPS" dir=out action=allow protocol=TCP localport=443 action=allow program="!WORK_DIR!\nginx\nginx.exe" enable=yes

echo Windows Firewall configuration completed.

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
if "!env_mode!"=="development" (
    npm run start:dev
) else (
    npm run start
)
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
