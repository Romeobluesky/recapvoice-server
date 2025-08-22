@echo off
setlocal enabledelayedexpansion

:: 환경 모드 확인
for /f "tokens=1,2 delims==" %%A in ('findstr /b "mode" "%~dp0settings.ini"') do (
	set "env_mode=%%B"
	set "env_mode=!env_mode: =!"
	echo Mode is: !env_mode!
)

:: 경로 설정
if "!env_mode!"=="development" (
	:: 개발 환경 경로 - settings.ini에서 직접 경로 읽기
	for /f "tokens=1,2 delims==" %%A in ('findstr /b "dir_path" "%~dp0settings.ini"') do (
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
echo Nginx started successfully.

:: 잠시 대기 (2초)
ping -n 3 127.0.0.1 >nul

:: MongoDB 설정 읽기
for /f "tokens=1,2 delims==" %%A in ('findstr /b "host" "%~dp0settings.ini"') do (
	set "mongodb_host=%%B"
	set "mongodb_host=!mongodb_host: =!"
	echo Found MongoDB host: !mongodb_host!
)

:: MongoDB 시작
echo Starting MongoDB...

start "" /b "!WORK_DIR!\mongodb\bin\mongod.exe" ^
  --dbpath "!WORK_DIR!\mongodb\data\db" ^
  --logpath "!WORK_DIR!\mongodb\log\mongodb.log" ^
  --logappend ^
  --port 27017 ^
  --bind_ip 0.0.0.0,!mongodb_host!

if %ERRORLEVEL% neq 0 (
	echo Failed to start MongoDB.
	goto error
)
echo MongoDB started successfully.

:: 잠시 대기 (3초)
ping -n 4 127.0.0.1 >nul

:: NestJS 시작
echo Starting NestJS...
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
	echo npm is not installed.
	goto error
)

:: NestJS 로그를 파일로 출력하면서 백그라운드 실행
cd /d "!WORK_DIR!\packetwave_client"
if "!env_mode!"=="development" (
	start /b cmd /c "npm run start:dev > !WORK_DIR!\logs\nestjs.log 2>&1"
) else (
	start /b cmd /c "npm run start > !WORK_DIR!\logs\nestjs.log 2>&1"
)
echo NestJS started in background with logging.
timeout /t 3 /nobreak >nul

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