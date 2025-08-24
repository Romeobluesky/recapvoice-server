  # RecapVoice ȯ�溯�� �׽�Ʈ ���� ��ũ��Ʈ
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

# StrRep �Լ� ��� ����
${Using:StrFunc} StrRep
  !define MUI_ABORTWARNING
  !define MUI_WELCOMEPAGE_TITLE "RecapVoice ȯ�溯�� �׽�Ʈ"
  !define MUI_WELCOMEPAGE_TEXT "ȯ�溯�� �Լ����� �׽�Ʈ�մϴ�.$\n$\n���� ��ġ�� ���� �ʽ��ϴ�."

  !insertmacro MUI_PAGE_WELCOME
  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_PAGE_FINISH
  !insertmacro MUI_LANGUAGE "Korean"


	# settings.ini���� Record.save_path �о���� �Լ�
  Function ReadRecordSavePath
     Push $0
     Push $1
     Push $2

     StrCpy $0 ""  # ����� ������ ���� �ʱ�ȭ

     # settings.ini ���� ���� Ȯ��
     ${If} ${FileExists} "settings.ini"
        DetailPrint "Found settings.ini file"

        # INI ���Ͽ��� Recording ������ save_path �� �б�
        ReadINIStr $1 "settings.ini" "Recording" "save_path"

        ${If} $1 != ""
           # / �� \ �� ����
           StrCpy $2 $1
           ${StrRep} $0 $2 "/" "\"
           DetailPrint "Record save path from settings.ini: $0"
        ${Else}
           DetailPrint "save_path not found in settings.ini"
           StrCpy $0 "D:\PacketWaveRecord"  # �⺻��
           DetailPrint "Using default path: $0"
        ${EndIf}
     ${Else}
        DetailPrint "settings.ini file not found"
        StrCpy $0 "D:\PacketWaveRecord"  # �⺻��
        DetailPrint "Using default path: $0"
     ${EndIf}

     # ���ÿ��� ��� ��ȯ
     Pop $2
     Pop $1
     Exch $0
  FunctionEnd

	# �������� ������ ȯ�溯�� ���� �Լ���
  Function DeleteRecapVoiceEnvironmentVariables
     DetailPrint "Removing individual RecapVoice environment variables..."

     # RecapVoice ���� ������ ����
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

     # �ܺ� ������ ������ ����
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
     DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

     # ������� ����
     SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
     DetailPrint "RecapVoice environment variables cleaned successfully"
  FunctionEnd

	Function RemoveStringFromPath
     Exch $0  # ������ ���ڿ�
     Push $1  # ���� PATH
     Push $2  # ���ο� PATH
     Push $3  # �ӽ� ��ū
     Push $4  # ���� ī����
     Push $5  # ��ū ����

     ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
     StrCpy $2 ""  # ���ο� PATH �ʱ�ȭ
     StrCpy $4 0   # ī���� �ʱ�ȭ

     # PATH�� �����ݷ����� �и��ؼ� ó��
     parse_loop:
        # ���� �����ݷ� ��ġ ã��
        StrCpy $5 0
        search_semicolon:
           StrCpy $3 $1 1 $5
           StrCmp $3 "" token_end
           StrCmp $3 ";" token_found
           IntOp $5 $5 + 1
           Goto search_semicolon

        token_found:
           StrCpy $3 $1 $5  # ��ū ����
           IntOp $5 $5 + 1
           StrCpy $1 $1 "" $5  # ������ ���ڿ�
           Goto check_token

        token_end:
           StrCpy $3 $1  # ������ ��ū
           StrCpy $1 ""

        check_token:
           # ���� ��ū�� ������ ���ڿ��� ������ Ȯ��
           StrCmp $3 "$0" skip_token
           StrCmp $3 "" skip_token  # �� ��ū �ǳʶٱ�

           # ��ū�� ���ο� PATH�� �߰�
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
        # ���ο� PATH ����
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

     # ������ PATH���� ����
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

     # settings.ini���� Record.save_path �о����
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

  # �׽�Ʈ ����
  Section "Environment Variables Test"
     DetailPrint "Starting RecapVoice Environment Variables Test..."

     MessageBox MB_YESNO "0�ܰ�: settings.ini ���� �б� �׽�Ʈ�� �Ͻðڽ��ϱ�?" IDYES step0 IDNO step1
  step0:
     DetailPrint "=== Testing settings.ini file reading ==="
     Call ReadRecordSavePath
     Pop $0
     MessageBox MB_YESNO "settings.ini���� �о�� Record save path:$\n$0$\n$\n������ ����ðڽ��ϱ�?" IDYES open_folder IDNO step1

  open_folder:
     DetailPrint "Opening folder: $0"
     # ������ �������� ������ ����
     CreateDirectory "$0"
     # Ž����� ���� ����
     ExecShell "open" "$0"

  step1:
     MessageBox MB_YESNO "1�ܰ�: ���� ȯ�溯�� ���¸� Ȯ���Ͻðڽ��ϱ�?" IDYES step1_run IDNO step2
  step1_run:
     Call ShowCurrentEnvironmentVariables

  step2:
     MessageBox MB_YESNO "2�ܰ�: ȯ�溯�� ������ �׽�Ʈ�Ͻðڽ��ϱ�?" IDYES cleanup IDNO step3
  cleanup:
     Call CleanupRecapVoiceEnvironment
     MessageBox MB_OK "ȯ�溯�� ���� �Ϸ�!"

  step3:
     MessageBox MB_YESNO "3�ܰ�: ȯ�溯�� ������ �׽�Ʈ�Ͻðڽ��ϱ�?" IDYES setup IDNO step4
  setup:
     Call SetupRecapVoiceEnvironment
     MessageBox MB_OK "ȯ�溯�� ���� �Ϸ�!"

  step4:
     MessageBox MB_YESNO "4�ܰ�: ���� ���¸� Ȯ���Ͻðڽ��ϱ�?" IDYES final IDNO done
  final:
     Call ShowCurrentEnvironmentVariables

     done:
     MessageBox MB_OK "ȯ�溯�� �׽�Ʈ�� ��� �Ϸ�Ǿ����ϴ�!$\n$\n��ġ �α׸� Ȯ���Ͽ� ���� ������ ���� �� �ֽ��ϴ�."

     DetailPrint "RecapVoice Environment Variables Test completed successfully!"
  SectionEnd