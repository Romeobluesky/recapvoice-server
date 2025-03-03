!define APP_NAME "Recap Voice"
!define VERSION "1.702"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# 버전 정보 추가
VIProductVersion "1.7.0.2"
VIAddVersionKey "ProductName" "Recap Voice"
VIAddVersionKey "CompanyName" "Xpower Networks"
VIAddVersionKey "FileVersion" "1.702"
VIAddVersionKey "ProductVersion" "1.702"
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
        # 이전 버전 제거
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
   
   # dist 폴더의 settings.ini 파일을 먼저 복사
   File "dist\Recap Voice\settings.ini"
   
   # settings.ini 내용 수정 2025-01-07 주석처리
   #!insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave\PacketWaveRecord" "$INSTDIR\RecapVoiceRecord"
   #!insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave" "$INSTDIR"
   
   # nginx.conf 파일의 경로도 수정
   !insertmacro ReplaceInFile "$INSTDIR\nginx\conf\nginx.conf" "D:\Work_state\packet_wave" "$INSTDIR"
   
   # 나머지 파일들 복사
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"
   
   # packetwave_client 폴더 복사
   DetailPrint "Copying packetwave_client..."
   CreateDirectory "$INSTDIR\packetwave_client"
   SetOutPath "$INSTDIR\packetwave_client"
   File /r /x "models" "packetwave_client\*.*"
   
   # 설치 프로그램과 같은 위치의 models 폴더를 복사
   DetailPrint "Copying whispermodels folder..."
   CopyFiles "$EXEDIR\models\*.*" "$INSTDIR\packetwave_client\models"
   
   SetOutPath "$INSTDIR"
   
   # 기존 PATH 값 보존하면서 새로운 경로 추가
   Push "C:\Program Files\nodejs"
   Call AddToPath
   Push "C:\Program Files\Npcap"
   Call AddToPath
   Push "C:\Program Files\Wireshark"
   Call AddToPath
   Push "C:\Program Files\ffmpeg\bin"
   Call AddToPath
   Push "$INSTDIR\nginx"
   Call AddToPath
   Push "$INSTDIR\mongodb\bin"
   Call AddToPath
   Push "$INSTDIR\packetwave_client\node_modules"
   Call AddToPath
   
   # 환경변수 설정 후 로그 출력
   ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Updated PATH: $0"
   
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

Function AddToPath
   Exch $0  ; 추가할 경로
   Push $1  ; 현재 PATH 값
   Push $2  ; 임시 변수
   Push $3  ; 문자열 길이 저장용
   
   # 현재 시스템의 PATH 값을 가져옴
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   
   # 이미 경로가 존재하는지 확인
   Push $1
   Push "$0"
   Call StrStr
   Pop $2
   StrCmp $2 "" NotFound Found
   
   Found:
      DetailPrint "'$0' 경로가 이미 PATH에 존재합니다."
      Goto done
      
   NotFound:
      # 새로운 PATH 길이 계산
      StrLen $3 $1
      StrLen $2 $0
      IntOp $3 $3 + $2
      IntOp $3 $3 + 1  # 세미콜론 길이 추가
      
      # PATH 길이 체크 (8000자 제한, 여유 공간 확보)
      ${If} $3 > 8000
         MessageBox MB_OK|MB_ICONEXCLAMATION "PATH 환경변수가 너무 깁니다. 새로운 경로를 추가할 수 없습니다."
         Goto done
      ${EndIf}
      
      # 새 경로 추가 (기존 PATH 유지)
      ${If} $1 != ""
         StrCpy $2 $1 1 -1  # 마지막 문자 확인
         ${If} $2 != ";"
            StrCpy $1 "$1;"  # 세미콜론 추가
         ${EndIf}
         StrCpy $1 "$1$0"  # 새 경로 추가
      ${Else}
         StrCpy $1 "$0"
      ${EndIf}
      
      # PATH 환경 변수 업데이트
      WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $1
      SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
      DetailPrint "'$0' 경로가 PATH에 추가되었습니다."

done:
   Pop $3
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

Section "Uninstall"
   # 실행 중인 프로세스 종료
   DetailPrint "Terminating running processes..."
   ExecWait 'taskkill /f /im "Recap Voice.exe" /t'
   ExecWait 'taskkill /f /im "nginx.exe" /t'
   ExecWait 'taskkill /f /im "mongod.exe" /t'
   ExecWait 'taskkill /f /im "node.exe" /t'
   ExecWait 'taskkill /f /im "Dumpcap.exe" /t'

   Sleep 2000  # 프로세스가 완전히 종료되길 기다림

   # 환경 변수 제거
   DetailPrint "Removing environment variables..."
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   !insertmacro un.RemovePath "$INSTDIR\nginx"
   !insertmacro un.RemovePath "$INSTDIR\mongodb\bin"
   !insertmacro un.RemovePath "$INSTDIR\packetwave_client\node_modules"
   !insertmacro un.RemovePath "C:\Program Files\nodejs"
   !insertmacro un.RemovePath "C:\Program Files\Npcap"
   !insertmacro un.RemovePath "C:\Program Files\Wireshark"
   !insertmacro un.RemovePath "C:\Program Files\ffmpeg\bin"
   
   # 환경 변수 변경사항 적용
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "Environment variables removed successfully"
   
   # 바탕화면 아이콘 제거
   SetShellVarContext all
   Delete "$DESKTOP\${APP_NAME}.lnk"
   Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
   RMDir "$SMPROGRAMS\${APP_NAME}"
   
   # 모든 파일 삭제 시도
   DetailPrint "Removing installation directory..."
   Delete "$INSTDIR\uninstall.exe"
   RMDir /r /REBOOTOK "$INSTDIR"
   
   # 녹음 파일 폴더 삭제 여부 확인
   MessageBox MB_YESNO "음성 녹음 파일이 저장된 폴더를 삭제하시겠습니까?" IDNO skip_delete_records
   SetShellVarContext all
   RMDir /r "$INSTDIR\RecapVoiceRecord"
   Goto records_deletion_done
   
   skip_delete_records:
   DetailPrint "음성 녹음 파일을 보존합니다."
   
   records_deletion_done:
   
   # 제어판에서 프로그램 제거
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
   
   # 폴더가 여전히 존재하는지 확인
   ${If} ${FileExists} "$INSTDIR"
       MessageBox MB_OK|MB_ICONINFORMATION "일부 파일이 사용 중이어서 완전히 제거되지 않았습니다.$\n시스템 재시작 후 자동으로 제거됩니다."
   ${EndIf}
SectionEnd

Function un.RemoveFromPath
   Exch $0
   Push $1
   Push $2
   Push $3
   Push $4
   
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   StrCpy $5 $1 1 -1 # 마지막 문자 가져오기
   
   ${If} $5 != ";"
      StrCpy $1 "$1;" # 마지막에 세미콜론 추가
   ${EndIf}
   
   Push $1
   Push "$0;"
   Call un.StrStr
   Pop $2
   StrCmp $2 "" done
   
   StrLen $3 "$0;"
   StrLen $4 $2
   StrCpy $5 $1 -$4 # 제거할 부분 이전까지
   StrCpy $6 $2 "" $3 # 제거할 부분 이후부터
   StrCpy $3 "$5$6"
   
   StrCpy $5 $3 1 -1 # 마지막 문자 확인
   ${If} $5 == ";"
      StrCpy $3 $3 -1 # 마지막 세미콜론 제거
   ${EndIf}
   
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $3
   
   done:
      Pop $6
      Pop $5
      Pop $4
      Pop $3
      Pop $2
      Pop $1
      Pop $0
FunctionEnd

Function un.StrStr
   Exch $R1 ; st=haystack, $R1=needle
   Exch     ; st=needle, $R1=haystack
   Exch $R2 ; $R2=needle, $R1=haystack
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