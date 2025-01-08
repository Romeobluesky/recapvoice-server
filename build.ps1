# PowerShell 스크립트
$pyinstaller_cmd = "pyinstaller --noconfirm --onedir --windowed --clean " + `
    "--name `"Recap Voice`" " + `
    "--icon=`"images\recapvoice_ico.ico`" " + `
    "--uac-admin " + `
    "--add-data `"settings.ini;.`" " + `
    "--add-data `"start.bat;.`" " + `
    "--add-data `"LICENCE.txt;.`" " + `
    "--add-data `"version.txt;.`" " + `
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
    "--collect-all `"PySide6`" " + `
    "--collect-all `"pyshark`" " + `
    "--collect-all `"scapy`" " + `
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

Write-Host "Build completed!" 