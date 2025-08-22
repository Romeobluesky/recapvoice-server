!define APP_NAME "Recap Voice"
!define VERSION "1.822"
!define INSTALL_DIR "$LOCALAPPDATA\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup_AppData.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel user  # 일반 사용자 권한으로 변경

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
!define MUI_WELCOMEPAGE_TEXT "이 프로그램은 음성 패킷을 캡처하고 녹음하는 프로그램입니다.$\n$\n사용자 폴더에 설치되어 권한 문제를 방지합니다.$\n$\n계속하려면 다음을 클릭하세요."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENCE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

# 언어 설정
!insertmacro MUI_LANGUAGE "Korean"

Function .onInit
    # AppData 기반 설치 경로
    StrCpy $INSTDIR "$LOCALAPPDATA\${APP_NAME}"
    
    # 이전 설치 확인
    ${If} ${FileExists} "$INSTDIR\uninstall.exe"
        MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
            "${APP_NAME}가 이미 설치되어 있습니다. 제거 후 다시 설치하시겠습니까?" \
            IDOK uninst
        Abort
        
        uninst:
            ExecWait '"$INSTDIR\uninstall.exe" _?=$INSTDIR'
    ${EndIf}
FunctionEnd

Section "Prerequisites"
   # 외부 도구들은 시스템 권한이 필요하므로 별도 처리
   MessageBox MB_YESNO "Wireshark, Node.js, FFmpeg 등 시스템 도구가 필요합니다.$\n관리자 권한으로 별도 설치하시겠습니까?" IDYES install_prereq IDNO skip_prereq
   
   install_prereq:
       # 별도 관리자 권한 설치 프로그램 실행
       ExecWait '"$EXEDIR\install_prerequisites_admin.exe"'
   
   skip_prereq:
       DetailPrint "Prerequisites installation skipped"
SectionEnd

Section "MainSection"
   SetOutPath "$INSTDIR"

   # AppData 기반 녹음 파일 저장 디렉토리 생성
   CreateDirectory "$INSTDIR\RecapVoiceRecord"
   
   # 권한 설정 불필요 (사용자 폴더이므로)
   
   # dist 폴더의 설정 파일 복사 및 수정
   File "dist\Recap Voice\settings.ini"
   
   # AppData 경로로 설정 수정
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "C:\Program Files (x86)\Recap Voice" "$INSTDIR"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave\PacketWaveRecord" "$INSTDIR\RecapVoiceRecord"
   
   # 나머지 파일들 복사
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"
   
   # packetwave_client 복사
   CreateDirectory "$INSTDIR\packetwave_client"
   File /r "packetwave_client\*.*"
   
   # 환경변수는 사용자별로 설정
   Push "$INSTDIR\nginx"
   Call AddToUserPath
   Push "$INSTDIR\mongodb\bin"  
   Call AddToUserPath
   
   # 바로가기 생성
   CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"
   CreateShortCut "$STARTMENU\Programs\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"
   
   WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Function AddToUserPath
   # 사용자별 PATH 환경변수에 추가
   Exch $0
   ReadRegStr $1 HKCU "Environment" "PATH"
   
   # 이미 존재하는지 확인
   Push $1
   Push "$0"
   Call StrStr
   Pop $2
   StrCmp $2 "" NotFound Found
   
   Found:
      DetailPrint "'$0' already in user PATH"
      Goto done
      
   NotFound:
      ${If} $1 != ""
         StrCpy $1 "$1;$0"
      ${Else}
         StrCpy $1 "$0"
      ${EndIf}
      
      WriteRegExpandStr HKCU "Environment" "PATH" $1
      SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
      DetailPrint "Added '$0' to user PATH"
      
   done:
      Pop $0
FunctionEnd

# ... (기타 필요한 함수들)