!define APP_NAME "Recap Voice"
!define VERSION "1.822"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# 버전 정보 추가
VIProductVersion "1.8.2.2"
VIAddVersionKey "ProductName" "Recap Voice"
VIAddVersionKey "CompanyName" "Xpower Networks"
VIAddVersionKey "FileVersion" "1.822"
VIAddVersionKey "ProductVersion" "1.822"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2025"
VIAddVersionKey "FileDescription" "Recap Voice"
VIAddVersionKey "OriginalFilename" "Recap Voice.exe"

# MUI 설정
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinCore.nsh"
!include "WinMessages.nsh"
!include "StrFunc.nsh"

# MUI 설정
!define MUI_ABORTWARNING
!define MUI_ICON "images\recapvoice_squere.ico"
!define MUI_UNICON "images\recapvoice_squere.ico"

# MUI 페이지
!define MUI_WELCOMEPAGE_TITLE "Recap Voice 설치 프로그램"
!define MUI_WELCOMEPAGE_TEXT "이 프로그램은 음성 패킷을 캡처하고 녹음하는 프로그램입니다.$\n$\n계속하려면 다음을 클릭하세요."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENCE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

# 언어 설정
!insertmacro MUI_LANGUAGE "Korean"

# 매크로 정의
!macro ReplaceInFile SOURCE_FILE SEARCH_TEXT REPLACEMENT
  Push "${SOURCE_FILE}"
  Push "${SEARCH_TEXT}"
  Push "${REPLACEMENT}"
  Call ReplaceInFile
!macroend

!macro un.RemovePath PATH
  Push "${PATH}"
  Call un.RemoveFromPath
!macroend

Function .onInit
    # 관리자 권한 체크
    UserInfo::GetAccountType
    Pop $0
    ${If} $0 != "admin"
        MessageBox MB_ICONSTOP "관리자 권한으로 실행해주세요."
        Abort
    ${EndIf}

    # 32비트 레지스트리 뷰 설정
    SetRegView 32

    # 32비트 프로그램이므로 자동으로 적절한 Program Files 경로 사용
    StrCpy $INSTDIR "$PROGRAMFILES\${APP_NAME}"

    # 이전 설치 확인
    ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString"
    StrCmp $R0 "" done

    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
        "${APP_NAME}가 이미 설치되어 있습니다. 제거 후 다시 설치하시겠습니까?" \
        IDOK uninst
    Abort

    uninst:
        # 이전 버전 제거 (환경변수는 삭제 프로그램에서 정리됨)
        ExecWait '$R0 _?=$INSTDIR'

    done:
FunctionEnd

Section "Prerequisites"
   # prereq 폴더 생성 및 설정
   CreateDirectory "$INSTDIR\prereq"
   SetOutPath "$INSTDIR\prereq"

   # Wireshark & TShark 설치
   DetailPrint "Installing Wireshark and TShark..."
   File "prereq\Wireshark-4.4.2-x64.exe"
   ExecWait '"$INSTDIR\prereq\Wireshark-4.4.2-x64.exe" /desktopicon=no /D=C:\Program Files\Wireshark'

   # Node.js 설치
   DetailPrint "Installing Node.js..."
   File "prereq\node-v20.18.2-x64.msi"
   ExecWait '"msiexec" /i "$INSTDIR\prereq\node-v20.18.2-x64.msi" /quiet /norestart'

   # FFmpeg 설치 (64비트 버전)
   DetailPrint "Installing FFmpeg..."
   CreateDirectory "C:\Program Files\ffmpeg"
   SetOutPath "C:\Program Files\ffmpeg"
   File /r "prereq\ffmpeg\*.*"

   # 설치 경로를 다시 INSTDIR로 복귀
   SetOutPath "$INSTDIR"
SectionEnd

Section "MainSection"
   SetOutPath "$INSTDIR"

   # 설치 디렉토리 내에 녹음 파일 저장 디렉토리 생성
   SetShellVarContext all
   CreateDirectory "$INSTDIR\RecapVoiceRecord"
   nsExec::ExecToStack 'icacls "$INSTDIR\RecapVoiceRecord" /grant Everyone:(OI)(CI)F'

   # 프로그램 실행 파일에 대한 권한 설정
   nsExec::ExecToStack 'icacls "$INSTDIR" /grant Everyone:(OI)(CI)RX'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.exe" /grant Everyone:(OI)(CI)F'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.ini" /grant Everyone:(OI)(CI)F'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.log" /grant Everyone:(OI)(CI)F'

   # dist 폴더의 settings.ini 파일을 먼저 복사
   File "dist\Recap Voice\settings.ini"

   # settings.ini 내용 수정 2025-01-07 주석처리
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave\PacketWaveRecord" "$INSTDIR\RecapVoiceRecord"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave" "$INSTDIR"

   # nginx.conf 파일의 경로도 수정
   !insertmacro ReplaceInFile "$INSTDIR\nginx\conf\nginx.conf" "D:\Work_state\packet_wave" "$INSTDIR"

   # 나머지 파일들 복사
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"

   # packetwave_client 외부 폴더에서 복사
   DetailPrint "Copying packetwave_client from external folder..."

   ; 설치 파일과 같은 위치의 packetwave_client 폴더 확인
   StrCpy $R0 "$EXEDIR\packetwave_client"
   ${If} ${FileExists} "$R0"
      DetailPrint "Found packetwave_client folder at: $R0"
      CreateDirectory "$INSTDIR\packetwave_client"

      ; xcopy를 사용한 전체 폴더 복사
      nsExec::ExecToStack 'xcopy "$R0" "$INSTDIR\packetwave_client" /E /I /H /Y'
      Pop $R1
      Pop $R2

      ${If} $R1 == 0
            DetailPrint "packetwave_client copied successfully"
      ${Else}
            DetailPrint "Error copying packetwave_client: $R2"
            MessageBox MB_OK|MB_ICONSTOP "packetwave_client folder copy failed."
            Abort
      ${EndIf}
   ${Else}
      MessageBox MB_OK|MB_ICONSTOP "packetwave_client folder not found."
      Abort
   ${EndIf}

   SetOutPath "$INSTDIR"

   # 항상 기존 환경변수를 정리한 후 새로 설정 (멱등성 보장)
   DetailPrint "Cleaning existing RecapVoice environment variables..."
   Call CleanupRecapVoiceEnvironment

   DetailPrint "Setting up RecapVoice environment with new variable system..."
   Call SetupRecapVoiceEnvironment

   # 최종 PATH 확인 및 로그 출력
   ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Final PATH configured with variables: $0"

   # 바로가기 생성
   CreateDirectory "$SMPROGRAMS\${APP_NAME}"
   CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"
   CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"

   WriteUninstaller "$INSTDIR\uninstall.exe"

   # 제어판 등록
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$INSTDIR\uninstall.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\Recap Voice.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "Xpower Networks"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${VERSION}"

   # 설치 완료 후 최종 PATH 기록
   ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   FileWrite $9 "Final PATH: $0$\r$\n"
   FileClose $9
SectionEnd

Function ReplaceInFile
  Exch $0 ;REPLACEMENT
  Exch
  Exch $1 ;SEARCH_TEXT
  Exch
  Exch 2
  Exch $2 ;SOURCE_FILE
  Push $R0
  Push $R1
  Push $R2
  Push $R3

  FileOpen $R0 $2 "r"
  GetTempFileName $R2
  FileOpen $R1 $R2 "w"

  loop:
    FileRead $R0 $R3
    IfErrors done
    Push $R3
    Push $1
    Call StrStr
    Pop $R4
    StrCmp $R4 "" +3
    StrCpy $R3 $0
    Goto +2
    StrCpy $R3 $R3
    FileWrite $R1 $R3
    Goto loop

  done:
    FileClose $R0
    FileClose $R1
    Delete $2
    CopyFiles /SILENT $R2 $2
    Delete $R2

  Pop $R3
  Pop $R2
  Pop $R1
  Pop $R0
  Pop $2
  Pop $1
  Pop $0
FunctionEnd

Function StrStr
   Exch $R1
   Exch
   Exch $R2
   Push $R3
   Push $R4
   Push $R5
   StrLen $R3 $R1
   StrLen $R4 $R2
   StrCpy $R5 0
   loop:
       StrCpy $R1 $R2 $R3 $R5
       StrCmp $R1 $R4 done
       StrCmp $R1 "" done
       IntOp $R5 $R5 + 1
       Goto loop
   done:
   Pop $R5
   Pop $R4
   Pop $R3
   Pop $R2
   Exch $R1
FunctionEnd

Function CleanupRecapVoiceEnvironment
   Push $0
   Push $1

   DetailPrint "Cleaning up all RecapVoice environment variables..."

   # PATH에서 RecapVoice 관련 모든 경로 및 변수 참조 제거
   Call RemoveRecapVoiceFromPath

   # 공통 환경변수 삭제 로직 호출
   Call DeleteRecapVoiceEnvironmentVariables

   Pop $1
   Pop $0
FunctionEnd

Function DeleteRecapVoiceEnvironmentVariables
   DetailPrint "Removing individual RecapVoice environment variables..."

   # RecapVoice 관련 변수들 삭제
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

   # 외부 의존성 변수들 삭제 (RecapVoice가 설치한 것들)
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

   # 변경사항 적용
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment variables cleaned successfully"
FunctionEnd

Function RemoveRecapVoiceFromPath
   Push $0
   Push $1

   # 현재 PATH 읽기
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Removing RecapVoice paths from PATH..."

   # 실제로 PATH에서 제거
   Push "%RECAPVOICE_NGINX%"
   Call RemoveFromPathInstall
   Push "%RECAPVOICE_MONGODB%"
   Call RemoveFromPathInstall
   Push "%RECAPVOICE_NODEMODULES%"
   Call RemoveFromPathInstall
   Push "%NODEJS_HOME%"
   Call RemoveFromPathInstall
   Push "%NPCAP_HOME%"
   Call RemoveFromPathInstall
   Push "%WIRESHARK_HOME%"
   Call RemoveFromPathInstall
   Push "%FFMPEG_HOME%\bin"
   Call RemoveFromPathInstall

   DetailPrint "RecapVoice paths removed from PATH"

   Pop $1
   Pop $0
FunctionEnd

Function SetupRecapVoiceEnvironment
   Push $0

   DetailPrint "Setting up RecapVoice environment variables..."

   # 기본 RecapVoice 경로 변수 설정
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME" "$INSTDIR"
   DetailPrint "Set RECAPVOICE_HOME=$INSTDIR"

   # RecapVoice 내부 경로들 설정
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX" "%RECAPVOICE_HOME%\nginx"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB" "%RECAPVOICE_HOME%\mongodb\bin"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT" "%RECAPVOICE_HOME%\packetwave_client"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES" "%RECAPVOICE_CLIENT%\node_modules"

   DetailPrint "Set RecapVoice internal path variables"

   # 외부 의존성 경로들 설정
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME" "C:\Program Files\nodejs"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME" "C:\Program Files\Npcap"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME" "C:\Program Files\Wireshark"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME" "C:\Program Files\ffmpeg"

   DetailPrint "Set external dependency path variables"

   # PATH에 변수 참조 방식으로 추가
   Call AddRecapVoiceVariablesToPath

   # 변경사항 적용
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment setup completed"

   Pop $0
FunctionEnd

Function AddRecapVoiceVariablesToPath
   Push $0
   Push $1
   Push $2

   # 현재 PATH 읽기
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Adding RecapVoice variables to PATH..."

   # 새로운 경로들을 변수 참조 방식으로 추가
   StrCpy $2 "%NODEJS_HOME%;%NPCAP_HOME%;%WIRESHARK_HOME%;%FFMPEG_HOME%\bin;%RECAPVOICE_NGINX%;%RECAPVOICE_MONGODB%;%RECAPVOICE_NODEMODULES%"

   # 기존 PATH가 비어있지 않으면 세미콜론으로 연결
   ${If} $1 != ""
      StrCpy $0 $1 1 -1  # 마지막 문자 확인
      ${If} $0 != ";"
         StrCpy $1 "$1;"  # 세미콜론 추가
      ${EndIf}
      StrCpy $1 "$1$2"  # 새 경로들 추가
   ${Else}
      StrCpy $1 "$2"
   ${EndIf}

   # PATH 길이 체크
   StrLen $0 $1
   ${If} $0 > 8000
      MessageBox MB_OK|MB_ICONEXCLAMATION "PATH 환경변수가 너무 깁니다. 일부 기능이 제한될 수 있습니다."
   ${EndIf}

   # PATH 업데이트
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $1
   DetailPrint "Added RecapVoice variables to PATH: $2"

   Pop $2
   Pop $1
   Pop $0
FunctionEnd

Function RemoveFromPathInstall
   Exch $0  # 제거할 문자열
   Push $1  # 현재 PATH
   Push $2  # 새로운 PATH
   Push $3  # 임시 토큰
   Push $4  # 현재 카운터
   Push $5  # 토큰 길이

   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   StrCpy $2 ""  # 새로운 PATH 초기화
   StrCpy $4 0   # 카운터 초기화

   # PATH를 세미콜론으로 분리해서 처리
   parse_loop:
      # 다음 세미콜론 위치 찾기
      StrCpy $5 0
      search_semicolon:
         StrCpy $3 $1 1 $5
         StrCmp $3 "" token_end
         StrCmp $3 ";" token_found
         IntOp $5 $5 + 1
         Goto search_semicolon

      token_found:
         StrCpy $3 $1 $5  # 토큰 추출
         IntOp $5 $5 + 1
         StrCpy $1 $1 "" $5  # 나머지 문자열
         Goto check_token

      token_end:
         StrCpy $3 $1  # 마지막 토큰
         StrCpy $1 ""

      check_token:
         # 현재 토큰이 제거할 문자열과 같은지 확인
         StrCmp $3 "$0" skip_token
         StrCmp $3 "" skip_token  # 빈 토큰 건너뛰기

         # 토큰을 새로운 PATH에 추가
         StrCmp $2 "" first_token
         StrCpy $2 "$2;$3"
         Goto continue_loop

         first_token:
         StrCpy $2 "$3"
         Goto continue_loop

      skip_token:
         DetailPrint "Removing token: '$3'"

      continue_loop:
         StrCmp $1 "" done_parsing
         Goto parse_loop

   done_parsing:
      # 새로운 PATH 설정
      WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $2
      DetailPrint "Updated PATH (removed '$0')"

   Pop $5
   Pop $4
   Pop $3
   Pop $2
   Pop $1
   Pop $0
FunctionEnd

Section "Uninstall"
   # 개선된 녹음 파일 처리 프로세스 (가장 먼저 실행)
   Call un.HandleRecordingFilesAdvanced

   # 실행 중인 프로세스 종료
   DetailPrint "Terminating running processes..."
   ExecWait 'taskkill /f /im "Recap Voice.exe" /t'
   ExecWait 'taskkill /f /im "nginx.exe" /t'
   ExecWait 'taskkill /f /im "mongod.exe" /t'
   ExecWait 'taskkill /f /im "node.exe" /t'
   ExecWait 'taskkill /f /im "Dumpcap.exe" /t'

   Sleep 2000  # 프로세스가 완전히 종료되길 기다림

   # RecapVoice 환경변수 완전 정리
   DetailPrint "Cleaning up RecapVoice environment variables..."
   Call un.CleanupRecapVoiceEnvironment

   # 바탕화면 아이콘 제거
   SetShellVarContext all
   Delete "$DESKTOP\${APP_NAME}.lnk"
   Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
   RMDir "$SMPROGRAMS\${APP_NAME}"

   # 모든 파일 삭제 시도
   DetailPrint "Removing installation directory..."
   Delete "$INSTDIR\uninstall.exe"
   RMDir /r /REBOOTOK "$INSTDIR"


   # 제어판에서 프로그램 제거
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

   # 폴더가 여전히 존재하는지 확인
   ${If} ${FileExists} "$INSTDIR"
       MessageBox MB_OK|MB_ICONINFORMATION "일부 파일이 사용 중이어서 완전히 제거되지 않았습니다.$\n시스템 재시작 후 자동으로 제거됩니다."
   ${EndIf}
SectionEnd

Function un.RemoveFromPath
   Exch $0  # 제거할 문자열
   Push $1  # 현재 PATH
   Push $2  # 새로운 PATH
   Push $3  # 임시 토큰
   Push $4  # 현재 카운터
   Push $5  # 토큰 길이

   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   StrCpy $2 ""  # 새로운 PATH 초기화
   StrCpy $4 0   # 카운터 초기화

   # PATH를 세미콜론으로 분리해서 처리
   parse_loop:
      # 다음 세미콜론 위치 찾기
      StrCpy $5 0
      search_semicolon:
         StrCpy $3 $1 1 $5
         StrCmp $3 "" token_end
         StrCmp $3 ";" token_found
         IntOp $5 $5 + 1
         Goto search_semicolon

      token_found:
         StrCpy $3 $1 $5  # 토큰 추출
         IntOp $5 $5 + 1
         StrCpy $1 $1 "" $5  # 나머지 문자열
         Goto check_token

      token_end:
         StrCpy $3 $1  # 마지막 토큰
         StrCpy $1 ""

      check_token:
         # 현재 토큰이 제거할 문자열과 같은지 확인
         StrCmp $3 "$0" skip_token
         StrCmp $3 "" skip_token  # 빈 토큰 건너뛰기

         # 토큰을 새로운 PATH에 추가
         StrCmp $2 "" first_token
         StrCpy $2 "$2;$3"
         Goto continue_loop

         first_token:
         StrCpy $2 "$3"
         Goto continue_loop

      skip_token:
         DetailPrint "Removing token: '$3'"

      continue_loop:
         StrCmp $1 "" done_parsing
         Goto parse_loop

   done_parsing:
      # 새로운 PATH 설정
      WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $2
      DetailPrint "Updated PATH (removed '$0')"

   Pop $5
   Pop $4
   Pop $3
   Pop $2
   Pop $1
   Pop $0
FunctionEnd

Function un.StrReplace
   Exch $0 ; Replacement
   Exch
   Exch $1 ; Search
   Exch
   Exch 2
   Exch $2 ; Source
   Push $3
   Push $4
   Push $5
   Push $6
   Push $7
   Push $8
   Push $9

   StrCpy $3 ""
   StrLen $4 $1
   StrLen $6 $2
   StrCpy $7 0

   ${If} $4 == 0
     StrCpy $0 $2
     Goto done
   ${EndIf}

   loop:
     StrCpy $5 $2 $4 $7
     StrCmp $5 $1 found
     StrCmp $7 $6 done
     StrCpy $5 $2 1 $7
     StrCpy $3 "$3$5"
     IntOp $7 $7 + 1
     Goto loop

   found:
     StrCpy $3 "$3$0"
     IntOp $7 $7 + $4
     Goto loop

   done:
     StrCpy $5 $2 "" $7
     StrCpy $0 "$3$5"

   Pop $9
   Pop $8
   Pop $7
   Pop $6
   Pop $5
   Pop $4
   Pop $3
   Pop $2
   Pop $1
   Exch $0
FunctionEnd

Function un.HandleRecordingFilesAdvanced
   Push $0  ; Recording path from settings
   Push $1  ; User choice

   # 1단계: 초기 확인
   MessageBox MB_YESNO|MB_ICONQUESTION "음성 녹음 파일을 확인하고 처리하시겠습니까?$\n$\n'예'를 누르면 녹음 파일 폴더를 열어드립니다." IDNO skip_all_records

   # 2단계: settings.ini에서 실제 저장 경로 읽기 (ReadINIStr 사용)
   ${If} ${FileExists} "$INSTDIR\settings.ini"
      DetailPrint "Found settings.ini file"
      ReadINIStr $0 "$INSTDIR\settings.ini" "Recording" "save_path"

      ${If} $0 != ""
         # / 를 \ 로 변환
         Push $0
         Push "/"
         Push "\"
         Call un.StrReplace
         Pop $0
         DetailPrint "Found recording path in settings.ini: $0"
      ${Else}
         DetailPrint "save_path not found in settings.ini"
         StrCpy $0 "$INSTDIR\RecapVoiceRecord"  # 기본값
         DetailPrint "Using default recording path: $0"
      ${EndIf}
   ${Else}
      DetailPrint "settings.ini file not found"
      StrCpy $0 "$INSTDIR\RecapVoiceRecord"  # 기본값
      DetailPrint "Using default recording path: $0"
   ${EndIf}

   # 3단계: 폴더가 존재하는지 확인
   ${If} ${FileExists} "$0"
      # 4단계: 폴더 탐색기로 녹음 파일 경로 열기
      DetailPrint "Opening recording folder: $0"
      ExecShell "open" "$0"

      # 5단계: 사용자에게 백업 시간 제공
      MessageBox MB_OK|MB_ICONINFORMATION "녹음 파일 폴더가 열렸습니다.$\n$\n필요한 파일을 다른 위치로 백업하신 후 '확인'을 눌러주세요.$\n$\n시간 제한은 없으니 천천히 작업하세요."

      # 6단계: 최종 삭제 확인
      MessageBox MB_YESNO|MB_ICONEXCLAMATION "백업이 완료되었나요?$\n$\n'예'를 누르면 녹음 파일 폴더를 삭제합니다.$\n'아니오'를 누르면 폴더를 보존합니다." IDNO skip_deletion

      # 7단계: 실제 삭제 실행
      DetailPrint "Deleting recording folder: $0"
      SetShellVarContext all
      RMDir /r "$0"
      MessageBox MB_OK|MB_ICONINFORMATION "녹음 파일 폴더가 삭제되었습니다."
      Goto cleanup_done

   ${Else}
      MessageBox MB_OK|MB_ICONINFORMATION "녹음 파일 폴더를 찾을 수 없습니다.$\n경로: $0"
      Goto cleanup_done
   ${EndIf}

   skip_deletion:
   DetailPrint "User chose to preserve recording files at: $0"

   # 폴더를 다시 열어줄지 확인
   MessageBox MB_YESNO|MB_ICONQUESTION "폴더를 다시 열어서 추가 백업 작업을 하시겠습니까?$\n$\n'예': 폴더를 다시 엽니다$\n'아니오': 백업을 완료합니다" IDNO backup_complete

   # 폴더 다시 열기
   DetailPrint "Re-opening recording folder for additional backup: $0"
   ExecShell "open" "$0"
   MessageBox MB_OK|MB_ICONINFORMATION "추가 백업 작업을 완료하신 후 '확인'을 눌러주세요."

   backup_complete:
   MessageBox MB_OK|MB_ICONINFORMATION "녹음 파일을 보존합니다.$\n경로: $0"
   Goto cleanup_done

   skip_all_records:
   DetailPrint "User skipped recording file handling"

   cleanup_done:
   Pop $1
   Pop $0
FunctionEnd

Function un.CleanupRecapVoiceEnvironment
   Push $0
   Push $1

   DetailPrint "Cleaning up all RecapVoice environment variables..."

   # PATH에서 RecapVoice 관련 모든 경로 및 변수 참조 제거
   Call un.RemoveRecapVoiceFromPath

   # 공통 환경변수 삭제 로직 호출 (설치용 함수 재사용)
   Call un.DeleteRecapVoiceEnvironmentVariables

   Pop $1
   Pop $0
FunctionEnd

Function un.RemoveRecapVoiceFromPath
   Push $0
   Push $1

   # 현재 PATH 읽기
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Removing RecapVoice paths from PATH..."

   # 변수 참조들 제거
   Push "%RECAPVOICE_NGINX%"
   Call un.RemoveFromPath
   Push "%RECAPVOICE_MONGODB%"
   Call un.RemoveFromPath
   Push "%RECAPVOICE_NODEMODULES%"
   Call un.RemoveFromPath
   Push "%NODEJS_HOME%"
   Call un.RemoveFromPath
   Push "%NPCAP_HOME%"
   Call un.RemoveFromPath
   Push "%WIRESHARK_HOME%"
   Call un.RemoveFromPath
   Push "%FFMPEG_HOME%\bin"
   Call un.RemoveFromPath

   DetailPrint "RecapVoice paths removed from PATH"

   Pop $1
   Pop $0
FunctionEnd

Function un.DeleteRecapVoiceEnvironmentVariables
   DetailPrint "Removing individual RecapVoice environment variables..."

   # RecapVoice 관련 변수들 삭제
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

   # 외부 의존성 변수들 삭제 (RecapVoice가 설치한 것들)
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

   # 변경사항 적용
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment variables cleaned successfully"
FunctionEnd