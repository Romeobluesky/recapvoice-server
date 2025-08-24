  # RecapVoice 환경변수 테스트 전용 스크립트
  !define APP_NAME "RecapVoice Environment Test"
  !define TEST_INSTDIR "C:\Program Files (x86)\Recap Voice"

  Name "${APP_NAME}"
  OutFile "RecapVoice_EnvTest.exe"
  RequestExecutionLevel admin

  !include "MUI2.nsh"
  !include "LogicLib.nsh"
  !include "WinCore.nsh"
  !include "WinMessages.nsh"
	!include "StrFunc.nsh"
!include "FileFunc.nsh"

# StrRep 함수 사용 선언
${Using:StrFunc} StrRep
  !define MUI_ABORTWARNING
  !define MUI_WELCOMEPAGE_TITLE "RecapVoice 환경변수 테스트"
  !define MUI_WELCOMEPAGE_TEXT "환경변수 함수들을 테스트합니다.$\n$\n실제 설치는 하지 않습니다."

  !insertmacro MUI_PAGE_WELCOME
  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_PAGE_FINISH
  !insertmacro MUI_LANGUAGE "Korean"


	# settings.ini에서 Record.save_path 읽어오는 함수
  Function ReadRecordSavePath
     Push $0
     Push $1
     Push $2

     StrCpy $0 ""  # 결과를 저장할 변수 초기화

     # settings.ini 파일 존재 확인
     ${If} ${FileExists} "settings.ini"
        DetailPrint "Found settings.ini file"

        # INI 파일에서 Recording 섹션의 save_path 값 읽기
        ReadINIStr $1 "settings.ini" "Recording" "save_path"

        ${If} $1 != ""
           # / 를 \ 로 변경
           StrCpy $2 $1
           ${StrRep} $0 $2 "/" "\"
           DetailPrint "Record save path from settings.ini: $0"
        ${Else}
           DetailPrint "save_path not found in settings.ini"
           StrCpy $0 "D:\PacketWaveRecord"  # 기본값
           DetailPrint "Using default path: $0"
        ${EndIf}
     ${Else}
        DetailPrint "settings.ini file not found"
        StrCpy $0 "D:\PacketWaveRecord"  # 기본값
        DetailPrint "Using default path: $0"
     ${EndIf}

     # 스택에서 결과 반환
     Pop $2
     Pop $1
     Exch $0
  FunctionEnd

	# 원본에서 복사한 환경변수 관련 함수들
  Function DeleteRecapVoiceEnvironmentVariables
     DetailPrint "Removing individual RecapVoice environment variables..."

     # RecapVoice 관련 변수들 삭제
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

     # 외부 의존성 변수들 삭제
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

     # 변경사항 적용
     SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
     DetailPrint "RecapVoice environment variables cleaned successfully"
  FunctionEnd

	Function RemoveStringFromPath
     Exch $0  # 제거할 문자열
     Push $1  # 현재 PATH
     Push $2  # 새로운 PATH
     Push $3  # 임시 토큰
     Push $4  # 루프 카운터
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
        # 새로운 PATH 저장
        WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $2
        DetailPrint "Updated PATH (removed '$0')"

     Pop $5
     Pop $4
     Pop $3
     Pop $2
     Pop $1
     Pop $0
  FunctionEnd

  Function RemoveRecapVoiceFromPath
     Push $0
     Push $1

     ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
     DetailPrint "Removing RecapVoice paths from PATH..."

     # 실제로 PATH에서 제거
     Push "%RECAPVOICE_NGINX%"
     Call RemoveStringFromPath
     Push "%RECAPVOICE_MONGODB%"
     Call RemoveStringFromPath
     Push "%RECAPVOICE_NODEMODULES%"
     Call RemoveStringFromPath
     Push "%NODEJS_HOME%"
     Call RemoveStringFromPath
     Push "%NPCAP_HOME%"
     Call RemoveStringFromPath
     Push "%WIRESHARK_HOME%"
     Call RemoveStringFromPath
     Push "%FFMPEG_HOME%"
     Call RemoveStringFromPath

     DetailPrint "RecapVoice paths removed from PATH"

     Pop $1
     Pop $0
  FunctionEnd

  Function CleanupRecapVoiceEnvironment
     Push $0
     Push $1

     DetailPrint "=== Cleaning up RecapVoice environment variables ==="
     Call RemoveRecapVoiceFromPath
     Call DeleteRecapVoiceEnvironmentVariables

     Pop $1
     Pop $0
  FunctionEnd

  Function AddRecapVoiceVariablesToPath
     Push $0
     Push $1
     Push $2

     ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
     DetailPrint "Adding RecapVoice variables to PATH..."

     StrCpy $2 "%NODEJS_HOME%;%NPCAP_HOME%;%WIRESHARK_HOME%;%FFMPEG_HOME%;%RECAPVOICE_NGINX%;%RECAPVOICE_MONGODB%;%RECAPVOICE_NODEMODULES%"

     ${If} $1 != ""
        StrCpy $0 $1 1 -1
        ${If} $0 != ";"
           StrCpy $1 "$1;"
        ${EndIf}
        StrCpy $1 "$1$2"
     ${Else}
        StrCpy $1 "$2"
     ${EndIf}

     StrLen $0 $1
     DetailPrint "New PATH length would be: $0 characters"
     ${If} $0 > 8000
        MessageBox MB_OK|MB_ICONEXCLAMATION "Warning: PATH would be too long ($0 characters)"
     ${Else}
        WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $1
        DetailPrint "Added RecapVoice variables to PATH: $2"
     ${EndIf}

     Pop $2
     Pop $1
     Pop $0
  FunctionEnd

  Function SetupRecapVoiceEnvironment
     Push $0
     Push $1

     DetailPrint "=== Setting up RecapVoice environment variables ==="

     # settings.ini에서 Record.save_path 읽어오기
     Call ReadRecordSavePath
     Pop $1
     DetailPrint "Using Record save path: $1"

     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME" "${TEST_INSTDIR}"
     DetailPrint "Set RECAPVOICE_HOME=${TEST_INSTDIR}"

     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX" "%RECAPVOICE_HOME%\nginx"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB" "%RECAPVOICE_HOME%\mongodb\bin"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT" "%RECAPVOICE_HOME%\packetwave_client"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES" "%RECAPVOICE_CLIENT%\node_modules"
     DetailPrint "Set RecapVoice internal path variables"

     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME" "C:\Program Files\nodejs"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME" "C:\Program Files\Npcap"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME" "C:\Program Files\Wireshark"
     WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME" "C:\Program Files\ffmpeg\bin"
     DetailPrint "Set external dependency path variables"

     Call AddRecapVoiceVariablesToPath

     SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
     DetailPrint "RecapVoice environment setup completed"

     Pop $1
     Pop $0
  FunctionEnd

  Function ShowCurrentEnvironmentVariables
     Push $0
     Push $1

     DetailPrint "=== Current Environment Variables Status ==="

     ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
     DetailPrint "RECAPVOICE_HOME: $0"

     ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
     DetailPrint "RECAPVOICE_NGINX: $0"


     ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
     DetailPrint "NODEJS_HOME: $0"

     ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
     StrLen $1 $0
     DetailPrint "PATH length: $1 characters"
     DetailPrint "PATH (first 200 chars): "
     StrCpy $1 $0 200
     DetailPrint "$1..."

     Pop $1
     Pop $0
  FunctionEnd

  # 테스트 섹션
  Section "Environment Variables Test"
     DetailPrint "Starting RecapVoice Environment Variables Test..."

     MessageBox MB_YESNO "0단계: settings.ini 파일 읽기 테스트를 하시겠습니까?" IDYES step0 IDNO step1
  step0:
     DetailPrint "=== Testing settings.ini file reading ==="
     Call ReadRecordSavePath
     Pop $0
     MessageBox MB_YESNO "settings.ini에서 읽어온 Record save path:$\n$0$\n$\n폴더를 열어보시겠습니까?" IDYES open_folder IDNO step1

  open_folder:
     DetailPrint "Opening folder: $0"
     # 폴더가 존재하지 않으면 생성
     CreateDirectory "$0"
     # 탐색기로 폴더 열기
     ExecShell "open" "$0"

  step1:
     MessageBox MB_YESNO "1단계: 현재 환경변수 상태를 확인하시겠습니까?" IDYES step1_run IDNO step2
  step1_run:
     Call ShowCurrentEnvironmentVariables

  step2:
     MessageBox MB_YESNO "2단계: 환경변수 정리를 테스트하시겠습니까?" IDYES cleanup IDNO step3
  cleanup:
     Call CleanupRecapVoiceEnvironment
     MessageBox MB_OK "환경변수 정리 완료!"

  step3:
     MessageBox MB_YESNO "3단계: 환경변수 설정을 테스트하시겠습니까?" IDYES setup IDNO step4
  setup:
     Call SetupRecapVoiceEnvironment
     MessageBox MB_OK "환경변수 설정 완료!"

  step4:
     MessageBox MB_YESNO "4단계: 최종 상태를 확인하시겠습니까?" IDYES final IDNO done
  final:
     Call ShowCurrentEnvironmentVariables

     done:
     MessageBox MB_OK "환경변수 테스트가 모두 완료되었습니다!$\n$\n설치 로그를 확인하여 세부 내용을 보실 수 있습니다."

     DetailPrint "RecapVoice Environment Variables Test completed successfully!"
  SectionEnd