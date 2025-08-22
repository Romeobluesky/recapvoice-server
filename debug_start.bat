@echo off
setlocal enabledelayedexpansion

echo Starting debug version of start.bat...

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

echo Work directory: !WORK_DIR!

:: nginx.exe 존재 여부 확인
echo Checking nginx.exe at: !WORK_DIR!\nginx\nginx.exe
if not exist "!WORK_DIR!\nginx\nginx.exe" (
	echo Error: nginx.exe not found at !WORK_DIR!\nginx\nginx.exe
	pause
	exit /b 1
)
echo nginx.exe found!

:: Nginx 설정 테스트
echo Testing nginx configuration...
"!WORK_DIR!\nginx\nginx.exe" -t -c "!WORK_DIR!\nginx\conf\nginx.conf"
if !ERRORLEVEL! neq 0 (
	echo nginx configuration test failed!
	pause
	exit /b 1
)
echo nginx configuration OK!

:: MongoDB 존재 여부 확인
echo Checking MongoDB at: !WORK_DIR!\mongodb\bin\mongod.exe
if not exist "!WORK_DIR!\mongodb\bin\mongod.exe" (
	echo Error: mongod.exe not found at !WORK_DIR!\mongodb\bin\mongod.exe
	pause
	exit /b 1
)
echo mongod.exe found!

:: NestJS 프로젝트 확인
echo Checking NestJS project at: !WORK_DIR!\packetwave_client
if not exist "!WORK_DIR!\packetwave_client\package.json" (
	echo Error: package.json not found at !WORK_DIR!\packetwave_client\package.json
	pause
	exit /b 1
)
echo NestJS project found!

:: 디렉토리 생성
if not exist "!WORK_DIR!\logs" mkdir "!WORK_DIR!\logs"
if not exist "!WORK_DIR!\temp" mkdir "!WORK_DIR!\temp"
if not exist "!WORK_DIR!\temp\client_body_temp" mkdir "!WORK_DIR!\temp\client_body_temp"

echo All checks passed. Starting services...

:: Nginx 시작
echo Starting Nginx...
start "" "!WORK_DIR!\nginx\nginx.exe" -c "!WORK_DIR!\nginx\conf\nginx.conf"
if !ERRORLEVEL! neq 0 (
	echo Failed to start Nginx.
	pause
	exit /b 1
)
echo Nginx started successfully!

:: 잠시 대기
timeout /t 2

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
	pause
	exit /b 1
)
echo MongoDB started successfully!

:: 잠시 대기
timeout /t 3

:: NPM 확인
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
	echo npm is not installed.
	pause
	exit /b 1
)
echo npm found!

:: NestJS 시작
echo Starting NestJS...
echo Changing to directory: !WORK_DIR!\packetwave_client
cd /d "!WORK_DIR!\packetwave_client"

if "!env_mode!"=="development" (
	echo Running: npm run start:dev
	npm run start:dev
) else (
	echo Running: npm run start
	npm run start
)

if %ERRORLEVEL% neq 0 (
	echo Failed to start NestJS
	pause
	exit /b 1
)

echo All services started successfully!
pause