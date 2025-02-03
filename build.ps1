# PowerShell 스크립트
$pyinstaller_cmd = "pyinstaller --noconfirm --onedir --windowed --clean " + `
    "--name `"Recap Voice`" " + `
    "--icon=`"images\recapvoice_squere.ico`" " + `
    "--uac-admin " + `
    "--add-data `"settings.ini;.`" " + `
    "--add-data `"start.bat;.`" " + `
    "--add-data `"LICENCE.txt;.`" " + `
    "--add-data `"version.txt;.`" " + `
    "--add-data `"voip_monitor.log;.`" " + `
    "--add-data `"crash.log;.`" " + `
    "--add-data `"docs;docs`" " + `
    "--add-data `"apply_schemas.py;.`" " + `
    "--add-data `"config_loader.py;.`" " + `
    "--add-data `"packet_monitor.py;.`" " + `
    "--add-data `"settings_popup.py;.`" " + `
    "--add-data `"voip_monitor.py;.`" " + `
    "--add-data `"wav_chat_extractor.py;.`" " + `
    "--add-data `"wav_merger.py;.`" " + `
    "--add-data `"styles\styles.qss;styles`" " + `
    "--add-data `"images;images`" " + `
    "--add-data `"sounds;sounds`" " + `
    "--version-file `"version.txt`" " + `
    "--hidden-import `"pymongo`" " + `
    "--hidden-import `"pydub`" " + `
    "--hidden-import `"speech_recognition`" " + `
    "--hidden-import `"ffmpeg`" " + `
    "--hidden-import `"mysql.connector`" " + `
    "--hidden-import `"psutil`" " + `
    "--hidden-import `"google.cloud.speech`" " + `
    "--hidden-import `"grpc`" " + `
    "--hidden-import `"termcolor`" " + `
    "--hidden-import `"PySide6.QtMultimedia`" " + `
    "--hidden-import `"PySide6.QtMultimediaWidgets`" " + `
    "--hidden-import `"PySide6.QtNetwork`" " + `
    "--hidden-import `"requests`" " + `
    "--hidden-import `"audioop`" " + `
    "--hidden-import `"wave`" " + `
    "--hidden-import `"asyncio`" " + `
    "--hidden-import `"atexit`" " + `
    "--hidden-import `"platform`" " + `
    "--collect-all `"PySide6`" " + `
    "--collect-all `"pyshark`" " + `
    "--collect-all `"scapy`" " + `
    "--collect-all `"requests`" " + `
    "--collect-all `"pydub`" " + `
    "--hidden-import `"win32process`" " + `
    "--hidden-import `"win32api`" " + `
    "--hidden-import `"win32gui`" " + `
    "--hidden-import `"win32con`" " + `
    "--hidden-import `"win32com`" " + `
    "dashboard.py"

# 명령어 실행
Write-Host "Executing PyInstaller command..."
Invoke-Expression $pyinstaller_cmd

# 빌드 완료 후 파일 복사
$distPath = "dist\Recap Voice"
if (-not (Test-Path $distPath)) {
    New-Item -ItemType Directory -Path $distPath -Force
}

Write-Host "Copying files to dist folder..."

# settings.ini 복사
if (Test-Path "settings.ini") {
    Copy-Item "settings.ini" -Destination "$distPath\settings.ini" -Force
    Write-Host "settings.ini copied successfully"
    
    # settings.ini 수정
    $settingsPath = "$distPath\settings.ini"
    Write-Host "Modifying settings.ini for production..."
    $content = Get-Content $settingsPath -Raw
    $installPath = "C:\Program Files (x86)\Recap Voice"
    $content = $content -replace "D:\\Work_state\\packet_wave\\PacketWaveRecord", "$installPath\RecapVoiceRecord"
    $content = $content -replace "mode = development", "mode = production"
    $content = $content -replace "D:\\Work_state\\packet_wave", "$installPath"
    Set-Content $settingsPath $content -Force
    Write-Host "settings.ini modified successfully for production environment"
} else {
    Write-Host "settings.ini not found"
}

# start.bat 복사
if (Test-Path "start.bat") {
    Copy-Item "start.bat" -Destination "$distPath\start.bat" -Force
    Write-Host "start.bat copied successfully"
} else {
    Write-Host "start.bat not found"
}

# Qt 멀티미디어 DLL 파일들 복사
Write-Host "Copying Qt DLL files..."

# 가상환경의 정확한 site-packages 경로 설정
$venvPath = "myenv\Lib\site-packages\PySide6"
$qtBinPath = $venvPath

# Qt DLL 파일 목록
$requiredDlls = @(
    "Qt6Multimedia.dll",
    "Qt6MultimediaWidgets.dll",
    "Qt6OpenGL.dll",
    "Qt6OpenGLWidgets.dll"
)

# DLL 파일 복사
foreach ($dll in $requiredDlls) {
    $sourcePath = Join-Path $qtBinPath $dll
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath -Destination $distPath -Force
        Write-Host "$dll copied successfully"
    } else {
        Write-Host "Warning: $dll not found in $qtBinPath"
    }
}

Write-Host "Build completed!" 