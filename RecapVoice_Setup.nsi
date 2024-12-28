!define APP_NAME "Recap Voice"
!define VERSION "1.103"
!define INSTALL_DIR "$PROGRAMFILES64\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# 버전 정보 추가
VIProductVersion "1.1.0.3"
VIAddVersionKey "ProductName" "Recap Voice"
VIAddVersionKey "CompanyName" "Xpower Networks"
VIAddVersionKey "FileVersion" "1.103"
VIAddVersionKey "ProductVersion" "1.103"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2024"
VIAddVersionKey "FileDescription" "Recap Voice Application"
VIAddVersionKey "OriginalFilename" "Recap Voice.exe"

# MUI 설정
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinCore.nsh"
!include "nsisunz.nsh"

# MUI 설정
!define MUI_ABORTWARNING
!define MUI_ICON "images\recapvoice_ico.ico"
!define MUI_UNICON "images\recapvoice_ico.ico"

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
   # Wireshark & TShark 설치
   DetailPrint "Installing Wireshark and TShark..."
   File "prereq\Wireshark-4.4.2-x64.exe"
   ExecWait '"$INSTDIR\prereq\Wireshark-4.4.2-x64.exe" /S /componentstrue=TShark'
   
   # Npcap 설치
   DetailPrint "Installing Npcap..."
   File "prereq\npcap-1.80.exe"
   ExecWait '"$INSTDIR\prereq\npcap-1.80.exe" /S'
   
   # FFmpeg 설치
   DetailPrint "Installing FFmpeg..."
   CreateDirectory "C:\Program Files\ffmpeg"
   SetOutPath "C:\Program Files\ffmpeg"
   File /r "prereq\ffmpeg\*.*"
   
   # FFmpeg bin 폴더가 있는지 확인
   ${If} ${FileExists} "C:\Program Files\ffmpeg\bin\ffmpeg.exe"
       Push "C:\Program Files\ffmpeg\bin"
       Call AddToPath
   ${EndIf}
   
   # WIRESHARK_PATH 관련 코드 제거
SectionEnd

Section "MainSection"
   SetOutPath "$INSTDIR"
   
   # 메인 프로그램 파일 복사
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"
   
   # settings.ini 복사 및 수정
   File "settings.ini"
   # 경로 수정
   !define SAVE_PATH_FIND "D:/PacketWaveRecord"
   !define SAVE_PATH_REPLACE "$DOCUMENTS\RecapVoiceRecord"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "${SAVE_PATH_FIND}" "${SAVE_PATH_REPLACE}"
   # Extension 섹션 대소문자 수정
   !define SECTION_FIND "[Extension]"
   !define SECTION_REPLACE "[extension]"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "${SECTION_FIND}" "${SECTION_REPLACE}"
   
   File "start.bat"
   
   # packetwave_client 폴더 복사
   DetailPrint "Copying packetwave_client..."
   RMDir /r "$INSTDIR\packetwave_client"    # 기존 폴더 제거
   CreateDirectory "$INSTDIR\packetwave_client"
   SetOutPath "$INSTDIR\packetwave_client"   # 대상 폴더로 변경
   File /r "packetwave_client\*.*"          # 폴더 내용 복사
   SetOutPath "$INSTDIR"                    # 원래 경로로 복귀
   
   # 환경변수 설정
   Push "PATH"
   Push "System"
   Push "$INSTDIR\nginx"
   Call AddToPath
   Push "$INSTDIR\mongodb\bin"
   Call AddToPath
   Push "C:\Program Files\Npcap"
   Call AddToPath
   Push "C:\Program Files\Wireshark"
   Call AddToPath
   Push "C:\Program Files\ffmpeg\bin"
   Call AddToPath
   
   # 바로가기 생성
   CreateDirectory "$SMPROGRAMS\${APP_NAME}"
   CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe" "" "$INSTDIR\Recap Voice.exe" 0 SW_SHOWNORMAL "" "Recap Voice Application"
   CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe" "" "$INSTDIR\Recap Voice.exe" 0

   # 내문서 폴더에 저장 디렉토리 생성
   SetShellVarContext current
   CreateDirectory "$DOCUMENTS\RecapVoiceRecord"
   ExecWait 'cmd.exe /C icacls "$DOCUMENTS\RecapVoiceRecord" /grant Everyone:(OI)(CI)F'
   
   WriteUninstaller "$INSTDIR\uninstall.exe"
   
   # 제어판 프로그램 목록에 추가
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$INSTDIR\uninstall.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\Recap Voice.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "Xpower Networks"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${VERSION}"
   WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" 1
   WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" 1
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
   Exch $0
   Push $1
   Push $2
   Push $3
   
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   # 마지막에 세미콜론이 없으면 추가
   ${If} $1 != ""
       StrCpy $3 $1 1 -1
       ${If} $3 != ";"
           StrCpy $1 "$1;"
       ${EndIf}
   ${EndIf}
   
   # 새 경로 추가
   StrCpy $3 "$1$0;"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $3
   
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
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   !insertmacro un.RemovePath "$INSTDIR\nginx"
   !insertmacro un.RemovePath "$INSTDIR\mongodb\bin"
   !insertmacro un.RemovePath "C:\Program Files\Npcap"
   !insertmacro un.RemovePath "C:\Program Files\Wireshark"
   !insertmacro un.RemovePath "C:\Program Files\ffmpeg\bin"
   
   Delete "$INSTDIR\uninstall.exe"
   RMDir /r "$INSTDIR"
   RMDir /r "$SMPROGRAMS\${APP_NAME}"
   
   # 내문서 폴더의 RecapVoiceRecord 삭제 여부 확인
   MessageBox MB_YESNO "음성 녹음 파일이 저장된 폴더를 삭제하시겠습니까?" IDNO skip_delete_records
   SetShellVarContext current
   RMDir /r "$DOCUMENTS\RecapVoiceRecord"
   skip_delete_records:
   
   # 제어판에서 프로그램 제거
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
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