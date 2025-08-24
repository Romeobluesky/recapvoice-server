!define APP_NAME "Recap Voice"
!define VERSION "1.822"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# ���� ���� �߰�
VIProductVersion "1.8.2.2"
VIAddVersionKey "ProductName" "Recap Voice"
VIAddVersionKey "CompanyName" "Xpower Networks"
VIAddVersionKey "FileVersion" "1.822"
VIAddVersionKey "ProductVersion" "1.822"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2025"
VIAddVersionKey "FileDescription" "Recap Voice"
VIAddVersionKey "OriginalFilename" "Recap Voice.exe"

# MUI ����
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinCore.nsh"
!include "WinMessages.nsh"
!include "StrFunc.nsh"

# MUI ����
!define MUI_ABORTWARNING
!define MUI_ICON "images\recapvoice_squere.ico"
!define MUI_UNICON "images\recapvoice_squere.ico"

# MUI ������
!define MUI_WELCOMEPAGE_TITLE "Recap Voice ��ġ ���α׷�"
!define MUI_WELCOMEPAGE_TEXT "�� ���α׷��� ���� ��Ŷ�� ĸó�ϰ� �����ϴ� ���α׷��Դϴ�.$\n$\n����Ϸ��� ������ Ŭ���ϼ���."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENCE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

# ��� ����
!insertmacro MUI_LANGUAGE "Korean"

# ��ũ�� ����
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
    # ������ ���� üũ
    UserInfo::GetAccountType
    Pop $0
    ${If} $0 != "admin"
        MessageBox MB_ICONSTOP "������ �������� �������ּ���."
        Abort
    ${EndIf}

    # 32��Ʈ ������Ʈ�� �� ����
    SetRegView 32

    # 32��Ʈ ���α׷��̹Ƿ� �ڵ����� ������ Program Files ��� ���
    StrCpy $INSTDIR "$PROGRAMFILES\${APP_NAME}"

    # ���� ��ġ Ȯ��
    ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString"
    StrCmp $R0 "" done

    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
        "${APP_NAME}�� �̹� ��ġ�Ǿ� �ֽ��ϴ�. ���� �� �ٽ� ��ġ�Ͻðڽ��ϱ�?" \
        IDOK uninst
    Abort

    uninst:
        # ���� ���� ���� (ȯ�溯���� ���� ���α׷����� ������)
        ExecWait '$R0 _?=$INSTDIR'

    done:
FunctionEnd

Section "Prerequisites"
   # prereq ���� ���� �� ����
   CreateDirectory "$INSTDIR\prereq"
   SetOutPath "$INSTDIR\prereq"

   # Wireshark & TShark ��ġ
   DetailPrint "Installing Wireshark and TShark..."
   File "prereq\Wireshark-4.4.2-x64.exe"
   ExecWait '"$INSTDIR\prereq\Wireshark-4.4.2-x64.exe" /desktopicon=no /D=C:\Program Files\Wireshark'

   # Node.js ��ġ
   DetailPrint "Installing Node.js..."
   File "prereq\node-v20.18.2-x64.msi"
   ExecWait '"msiexec" /i "$INSTDIR\prereq\node-v20.18.2-x64.msi" /quiet /norestart'

   # FFmpeg ��ġ (64��Ʈ ����)
   DetailPrint "Installing FFmpeg..."
   CreateDirectory "C:\Program Files\ffmpeg"
   SetOutPath "C:\Program Files\ffmpeg"
   File /r "prereq\ffmpeg\*.*"

   # ��ġ ��θ� �ٽ� INSTDIR�� ����
   SetOutPath "$INSTDIR"
SectionEnd

Section "MainSection"
   SetOutPath "$INSTDIR"

   # ��ġ ���丮 ���� ���� ���� ���� ���丮 ����
   SetShellVarContext all
   CreateDirectory "$INSTDIR\RecapVoiceRecord"
   nsExec::ExecToStack 'icacls "$INSTDIR\RecapVoiceRecord" /grant Everyone:(OI)(CI)F'

   # ���α׷� ���� ���Ͽ� ���� ���� ����
   nsExec::ExecToStack 'icacls "$INSTDIR" /grant Everyone:(OI)(CI)RX'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.exe" /grant Everyone:(OI)(CI)F'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.ini" /grant Everyone:(OI)(CI)F'
   nsExec::ExecToStack 'icacls "$INSTDIR\*.log" /grant Everyone:(OI)(CI)F'

   # dist ������ settings.ini ������ ���� ����
   File "dist\Recap Voice\settings.ini"

   # settings.ini ���� ���� 2025-01-07 �ּ�ó��
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave\PacketWaveRecord" "$INSTDIR\RecapVoiceRecord"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave" "$INSTDIR"

   # nginx.conf ������ ��ε� ����
   !insertmacro ReplaceInFile "$INSTDIR\nginx\conf\nginx.conf" "D:\Work_state\packet_wave" "$INSTDIR"

   # ������ ���ϵ� ����
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"

   # packetwave_client �ܺ� �������� ����
   DetailPrint "Copying packetwave_client from external folder..."

   ; ��ġ ���ϰ� ���� ��ġ�� packetwave_client ���� Ȯ��
   StrCpy $R0 "$EXEDIR\packetwave_client"
   ${If} ${FileExists} "$R0"
      DetailPrint "Found packetwave_client folder at: $R0"
      CreateDirectory "$INSTDIR\packetwave_client"

      ; xcopy�� ����� ��ü ���� ����
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

   # �׻� ���� ȯ�溯���� ������ �� ���� ���� (�� ����)
   DetailPrint "Cleaning existing RecapVoice environment variables..."
   Call CleanupRecapVoiceEnvironment

   DetailPrint "Setting up RecapVoice environment with new variable system..."
   Call SetupRecapVoiceEnvironment

   # ���� PATH Ȯ�� �� �α� ���
   ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Final PATH configured with variables: $0"

   # �ٷΰ��� ����
   CreateDirectory "$SMPROGRAMS\${APP_NAME}"
   CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"
   CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe"

   WriteUninstaller "$INSTDIR\uninstall.exe"

   # ������ ���
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$INSTDIR\uninstall.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\Recap Voice.exe"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "Xpower Networks"
   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${VERSION}"

   # ��ġ �Ϸ� �� ���� PATH ���
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

   # PATH���� RecapVoice ���� ��� ��� �� ���� ���� ����
   Call RemoveRecapVoiceFromPath

   # ���� ȯ�溯�� ���� ���� ȣ��
   Call DeleteRecapVoiceEnvironmentVariables

   Pop $1
   Pop $0
FunctionEnd

Function DeleteRecapVoiceEnvironmentVariables
   DetailPrint "Removing individual RecapVoice environment variables..."

   # RecapVoice ���� ������ ����
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

   # �ܺ� ������ ������ ���� (RecapVoice�� ��ġ�� �͵�)
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

   # ������� ����
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment variables cleaned successfully"
FunctionEnd

Function RemoveRecapVoiceFromPath
   Push $0
   Push $1

   # ���� PATH �б�
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Removing RecapVoice paths from PATH..."

   # ������ PATH���� ����
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

   # �⺻ RecapVoice ��� ���� ����
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME" "$INSTDIR"
   DetailPrint "Set RECAPVOICE_HOME=$INSTDIR"

   # RecapVoice ���� ��ε� ����
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX" "%RECAPVOICE_HOME%\nginx"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB" "%RECAPVOICE_HOME%\mongodb\bin"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT" "%RECAPVOICE_HOME%\packetwave_client"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES" "%RECAPVOICE_CLIENT%\node_modules"

   DetailPrint "Set RecapVoice internal path variables"

   # �ܺ� ������ ��ε� ����
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME" "C:\Program Files\nodejs"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME" "C:\Program Files\Npcap"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME" "C:\Program Files\Wireshark"
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME" "C:\Program Files\ffmpeg"

   DetailPrint "Set external dependency path variables"

   # PATH�� ���� ���� ������� �߰�
   Call AddRecapVoiceVariablesToPath

   # ������� ����
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment setup completed"

   Pop $0
FunctionEnd

Function AddRecapVoiceVariablesToPath
   Push $0
   Push $1
   Push $2

   # ���� PATH �б�
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Adding RecapVoice variables to PATH..."

   # ���ο� ��ε��� ���� ���� ������� �߰�
   StrCpy $2 "%NODEJS_HOME%;%NPCAP_HOME%;%WIRESHARK_HOME%;%FFMPEG_HOME%\bin;%RECAPVOICE_NGINX%;%RECAPVOICE_MONGODB%;%RECAPVOICE_NODEMODULES%"

   # ���� PATH�� ������� ������ �����ݷ����� ����
   ${If} $1 != ""
      StrCpy $0 $1 1 -1  # ������ ���� Ȯ��
      ${If} $0 != ";"
         StrCpy $1 "$1;"  # �����ݷ� �߰�
      ${EndIf}
      StrCpy $1 "$1$2"  # �� ��ε� �߰�
   ${Else}
      StrCpy $1 "$2"
   ${EndIf}

   # PATH ���� üũ
   StrLen $0 $1
   ${If} $0 > 8000
      MessageBox MB_OK|MB_ICONEXCLAMATION "PATH ȯ�溯���� �ʹ� ��ϴ�. �Ϻ� ����� ���ѵ� �� �ֽ��ϴ�."
   ${EndIf}

   # PATH ������Ʈ
   WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $1
   DetailPrint "Added RecapVoice variables to PATH: $2"

   Pop $2
   Pop $1
   Pop $0
FunctionEnd

Function RemoveFromPathInstall
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

Section "Uninstall"
   # ������ ���� ���� ó�� ���μ��� (���� ���� ����)
   Call un.HandleRecordingFilesAdvanced

   # ���� ���� ���μ��� ����
   DetailPrint "Terminating running processes..."
   ExecWait 'taskkill /f /im "Recap Voice.exe" /t'
   ExecWait 'taskkill /f /im "nginx.exe" /t'
   ExecWait 'taskkill /f /im "mongod.exe" /t'
   ExecWait 'taskkill /f /im "node.exe" /t'
   ExecWait 'taskkill /f /im "Dumpcap.exe" /t'

   Sleep 2000  # ���μ����� ������ ����Ǳ� ��ٸ�

   # RecapVoice ȯ�溯�� ���� ����
   DetailPrint "Cleaning up RecapVoice environment variables..."
   Call un.CleanupRecapVoiceEnvironment

   # ����ȭ�� ������ ����
   SetShellVarContext all
   Delete "$DESKTOP\${APP_NAME}.lnk"
   Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
   RMDir "$SMPROGRAMS\${APP_NAME}"

   # ��� ���� ���� �õ�
   DetailPrint "Removing installation directory..."
   Delete "$INSTDIR\uninstall.exe"
   RMDir /r /REBOOTOK "$INSTDIR"


   # �����ǿ��� ���α׷� ����
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

   # ������ ������ �����ϴ��� Ȯ��
   ${If} ${FileExists} "$INSTDIR"
       MessageBox MB_OK|MB_ICONINFORMATION "�Ϻ� ������ ��� ���̾ ������ ���ŵ��� �ʾҽ��ϴ�.$\n�ý��� ����� �� �ڵ����� ���ŵ˴ϴ�."
   ${EndIf}
SectionEnd

Function un.RemoveFromPath
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

   # 1�ܰ�: �ʱ� Ȯ��
   MessageBox MB_YESNO|MB_ICONQUESTION "���� ���� ������ Ȯ���ϰ� ó���Ͻðڽ��ϱ�?$\n$\n'��'�� ������ ���� ���� ������ ����帳�ϴ�." IDNO skip_all_records

   # 2�ܰ�: settings.ini���� ���� ���� ��� �б� (ReadINIStr ���)
   ${If} ${FileExists} "$INSTDIR\settings.ini"
      DetailPrint "Found settings.ini file"
      ReadINIStr $0 "$INSTDIR\settings.ini" "Recording" "save_path"

      ${If} $0 != ""
         # / �� \ �� ��ȯ
         Push $0
         Push "/"
         Push "\"
         Call un.StrReplace
         Pop $0
         DetailPrint "Found recording path in settings.ini: $0"
      ${Else}
         DetailPrint "save_path not found in settings.ini"
         StrCpy $0 "$INSTDIR\RecapVoiceRecord"  # �⺻��
         DetailPrint "Using default recording path: $0"
      ${EndIf}
   ${Else}
      DetailPrint "settings.ini file not found"
      StrCpy $0 "$INSTDIR\RecapVoiceRecord"  # �⺻��
      DetailPrint "Using default recording path: $0"
   ${EndIf}

   # 3�ܰ�: ������ �����ϴ��� Ȯ��
   ${If} ${FileExists} "$0"
      # 4�ܰ�: ���� Ž����� ���� ���� ��� ����
      DetailPrint "Opening recording folder: $0"
      ExecShell "open" "$0"

      # 5�ܰ�: ����ڿ��� ��� �ð� ����
      MessageBox MB_OK|MB_ICONINFORMATION "���� ���� ������ ���Ƚ��ϴ�.$\n$\n�ʿ��� ������ �ٸ� ��ġ�� ����Ͻ� �� 'Ȯ��'�� �����ּ���.$\n$\n�ð� ������ ������ õõ�� �۾��ϼ���."

      # 6�ܰ�: ���� ���� Ȯ��
      MessageBox MB_YESNO|MB_ICONEXCLAMATION "����� �Ϸ�Ǿ�����?$\n$\n'��'�� ������ ���� ���� ������ �����մϴ�.$\n'�ƴϿ�'�� ������ ������ �����մϴ�." IDNO skip_deletion

      # 7�ܰ�: ���� ���� ����
      DetailPrint "Deleting recording folder: $0"
      SetShellVarContext all
      RMDir /r "$0"
      MessageBox MB_OK|MB_ICONINFORMATION "���� ���� ������ �����Ǿ����ϴ�."
      Goto cleanup_done

   ${Else}
      MessageBox MB_OK|MB_ICONINFORMATION "���� ���� ������ ã�� �� �����ϴ�.$\n���: $0"
      Goto cleanup_done
   ${EndIf}

   skip_deletion:
   DetailPrint "User chose to preserve recording files at: $0"

   # ������ �ٽ� �������� Ȯ��
   MessageBox MB_YESNO|MB_ICONQUESTION "������ �ٽ� ��� �߰� ��� �۾��� �Ͻðڽ��ϱ�?$\n$\n'��': ������ �ٽ� ���ϴ�$\n'�ƴϿ�': ����� �Ϸ��մϴ�" IDNO backup_complete

   # ���� �ٽ� ����
   DetailPrint "Re-opening recording folder for additional backup: $0"
   ExecShell "open" "$0"
   MessageBox MB_OK|MB_ICONINFORMATION "�߰� ��� �۾��� �Ϸ��Ͻ� �� 'Ȯ��'�� �����ּ���."

   backup_complete:
   MessageBox MB_OK|MB_ICONINFORMATION "���� ������ �����մϴ�.$\n���: $0"
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

   # PATH���� RecapVoice ���� ��� ��� �� ���� ���� ����
   Call un.RemoveRecapVoiceFromPath

   # ���� ȯ�溯�� ���� ���� ȣ�� (��ġ�� �Լ� ����)
   Call un.DeleteRecapVoiceEnvironmentVariables

   Pop $1
   Pop $0
FunctionEnd

Function un.RemoveRecapVoiceFromPath
   Push $0
   Push $1

   # ���� PATH �б�
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Removing RecapVoice paths from PATH..."

   # ���� ������ ����
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

   # RecapVoice ���� ������ ����
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NGINX"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_MONGODB"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_CLIENT"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "RECAPVOICE_NODEMODULES"

   # �ܺ� ������ ������ ���� (RecapVoice�� ��ġ�� �͵�)
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NODEJS_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "NPCAP_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "WIRESHARK_HOME"
   DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FFMPEG_HOME"

   # ������� ����
   SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
   DetailPrint "RecapVoice environment variables cleaned successfully"
FunctionEnd