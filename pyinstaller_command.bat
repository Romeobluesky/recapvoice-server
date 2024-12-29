@echo off
REM PowerShell에서도 실행되도록 cmd.exe를 통해 실행
cmd.exe /c pyinstaller --noconfirm --onedir --windowed --clean ^
    --name "Recap Voice" ^
    --icon="images\recapvoice_ico.ico" ^
    --uac-admin ^
    --add-data "settings.ini;." ^
    --add-data "start.bat;." ^
    --add-data "LICENCE.txt;." ^
    --add-data "version.txt;." ^
    --add-data "docs;docs" ^
    --add-data "apply_schemas.py;." ^
    --add-data "config_loader.py;." ^
    --add-data "packet_monitor.py;." ^
    --add-data "settings_popup.py;." ^
    --add-data "voip_monitor.py;." ^
    --add-data "wav_chat_extractor.py;." ^
    --add-data "wav_merger.py;." ^
    --add-data "styles\styles.qss;styles" ^
    --add-data "images;images" ^
    --version-file "version.txt" ^
    --hidden-import "pymongo" ^
    --hidden-import "numpy" ^
    --hidden-import "pydub" ^
    --hidden-import "speech_recognition" ^
    --hidden-import "ffmpeg" ^
    --hidden-import "mysql.connector" ^
    --hidden-import "psutil" ^
    --collect-all "PySide6" ^
    --collect-all "google.cloud.speech" ^
    --collect-all "pyshark" ^
    --collect-all "scapy" ^
    dashboard.py

REM 빌드 완료 후 settings.ini 파일 복사
if not exist "dist\Recap Voice" mkdir "dist\Recap Voice"
echo Copying settings.ini to dist folder...
copy /Y "settings.ini" "dist\Recap Voice\settings.ini"
echo Build completed!