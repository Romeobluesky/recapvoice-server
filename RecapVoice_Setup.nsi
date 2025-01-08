!define APP_NAME "Recap Voice"
!define VERSION "1.203"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# ���� ���� �߰�
VIProductVersion "1.2.0.3"
VIAddVersionKey "ProductName" "Recap Voice"
VIAddVersionKey "CompanyName" "Xpower Networks"
VIAddVersionKey "FileVersion" "1.103"
VIAddVersionKey "ProductVersion" "1.103"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2024"
VIAddVersionKey "FileDescription" "Recap Voice Application"
VIAddVersionKey "OriginalFilename" "Recap Voice.exe"

# MUI ����
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinCore.nsh"
!include "WinMessages.nsh"
!include "nsisunz.nsh"
!include "StrFunc.nsh"

# ���ڿ� �Լ� �ʱ�ȭ
${StrRep}

# MUI ����
!define MUI_ABORTWARNING
!define MUI_ICON "images\recapvoice_ico.ico"
!define MUI_UNICON "images\recapvoice_ico.ico"

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
        # ���� ���� ����
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
   File "prereq\node-v20.11.1-x64.msi"
   ExecWait '"msiexec" /i "$INSTDIR\prereq\node-v20.11.1-x64.msi" /quiet /norestart'
   
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
   ExecWait 'cmd.exe /C icacls "$INSTDIR\RecapVoiceRecord" /grant Everyone:(OI)(CI)F'
   
   # dist ������ settings.ini ������ ���� ����
   File "dist\Recap Voice\settings.ini"
   
   # settings.ini ���� ���� 2025-01-07 �ּ�ó��
   #!insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave\PacketWaveRecord" "$INSTDIR\RecapVoiceRecord"
   #!insertmacro ReplaceInFile "$INSTDIR\settings.ini" "D:\Work_state\packet_wave" "$INSTDIR"
   
   # nginx.conf ������ ��ε� ����
   !insertmacro ReplaceInFile "$INSTDIR\nginx\conf\nginx.conf" "D:\Work_state\packet_wave" "$INSTDIR"
   
   # ������ ���ϵ� ����
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"
   
   # packetwave_client ���� ����
   DetailPrint "Copying packetwave_client..."
   CreateDirectory "$INSTDIR\packetwave_client"
   SetOutPath "$INSTDIR\packetwave_client"
   File /r "packetwave_client\*.*"
   SetOutPath "$INSTDIR"
   
   # ȯ�溯�� ���� (�߿䵵 �������)
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
   # Node.js ��� �߰�
   Push "C:\Program Files\nodejs\"
   Call AddToPath
   # Node.js ��� ��� �߰�
   Push "$INSTDIR\packetwave_client\node_modules"
   Call AddToPath
   
   # ȯ�溯�� ���� �� �α� ���
   ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   DetailPrint "Updated PATH: $0"
   
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

Function AddToPath
   Exch $0  ; �߰��� ���
   Push $1  ; ���� PATH ��
   Push $2  ; �ӽ� ����
   Push $3  ; ��ü PATH ����
   
   # ���� PATH �� �б�
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   
   # �ߺ� ��� ���Ÿ� ���� ����
   ${StrRep} $1 $1 ";%SystemRoot%\system32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SYSTEMROOT%\System32\WindowsPowerShell\v1.0\;%SYSTEMROOT%\System32\OpenSSH\;" ";"
   ${StrRep} $1 $1 ";;;" ";"
   ${StrRep} $1 $1 ";;" ";"
   
   # �̹� ��ΰ� �����ϴ��� Ȯ��
   Push $1
   Push "$0"
   Call StrStr
   Pop $2
   StrCmp $2 "" NotFound Found
   
   Found:
      DetailPrint "'$0' ��ΰ� �̹� PATH�� �����մϴ�."
      Goto done
      
   NotFound:
      # ������ ���ڰ� �����ݷ����� Ȯ��
      ${If} $1 != ""
         StrCpy $2 $1 1 -1
         ${If} $2 != ";"
            StrCpy $1 "$1;"
         ${EndIf}
      ${EndIf}
      
      # �� ��� �߰� �� ���� üũ
      StrLen $3 "$1$0;"
      ${If} $3 > 2047
         DetailPrint "PATH�� �ʹ� ��ϴ�. ���� ��θ� �����մϴ�."
         # ���ʿ��� �ߺ� ��� ����
         ${StrRep} $1 $1 "C:\Program Files\Common Files\;" ""
         ${StrRep} $1 $1 "C:\Program Files (x86)\Common Files\;" ""
      ${EndIf}
      
      # �� ��� �߰�
      StrCpy $1 "$1$0;"
      # ���� ���� �ٽ� üũ
      StrLen $3 $1
      ${If} $3 > 2047
         MessageBox MB_OK|MB_ICONEXCLAMATION "���: PATH ȯ�溯���� �ʹ� ��ϴ�. �Ϻ� ��ΰ� �߰����� ���� �� �ֽ��ϴ�."
         DetailPrint "PATH ���� �ʰ�: $3 characters"
         Goto done
      ${EndIf}
      
      WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH" $1
      SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
      DetailPrint "'$0' ��ΰ� PATH�� �߰��Ǿ����ϴ�."

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
   # ���� ���� ���μ��� ����
   DetailPrint "Terminating running processes..."
   ExecWait 'taskkill /f /im "Recap Voice.exe" /t'
   ExecWait 'taskkill /f /im "nginx.exe" /t'
   ExecWait 'taskkill /f /im "mongod.exe" /t'
   ExecWait 'taskkill /f /im "node.exe" /t'
   Sleep 2000  # ���μ����� ������ ����Ǳ� ��ٸ�

   # ȯ�� ���� ����
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   !insertmacro un.RemovePath "$INSTDIR\nginx"
   !insertmacro un.RemovePath "$INSTDIR\mongodb\bin"
   !insertmacro un.RemovePath "C:\Program Files\Npcap"
   !insertmacro un.RemovePath "C:\Program Files\Wireshark"
   !insertmacro un.RemovePath "C:\Program Files\ffmpeg\bin"
   
   # ����ȭ�� ������ ����
   SetShellVarContext all
   Delete "$DESKTOP\${APP_NAME}.lnk"
   Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
   RMDir "$SMPROGRAMS\${APP_NAME}"
   
   # ��� ���� ���� �õ�
   DetailPrint "Removing installation directory..."
   Delete "$INSTDIR\uninstall.exe"
   RMDir /r /REBOOTOK "$INSTDIR"
   
   # ���� ���� ���� ���� ���� Ȯ��
   MessageBox MB_YESNO "���� ���� ������ ����� ������ �����Ͻðڽ��ϱ�?" IDNO skip_delete_records
   SetShellVarContext all
   RMDir /r "$INSTDIR\RecapVoiceRecord"
   skip_delete_records:
   
   # �����ǿ��� ���α׷� ����
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
   
   # ������ ������ �����ϴ��� Ȯ��
   ${If} ${FileExists} "$INSTDIR"
       MessageBox MB_OK|MB_ICONINFORMATION "�Ϻ� ������ ��� ���̾ ������ ���ŵ��� �ʾҽ��ϴ�.$\n�ý��� ����� �� �ڵ����� ���ŵ˴ϴ�."
   ${EndIf}
SectionEnd

Function un.RemoveFromPath
   Exch $0
   Push $1
   Push $2
   Push $3
   Push $4
   
   ReadRegStr $1 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "PATH"
   StrCpy $5 $1 1 -1 # ������ ���� ��������
   
   ${If} $5 != ";"
      StrCpy $1 "$1;" # �������� �����ݷ� �߰�
   ${EndIf}
   
   Push $1
   Push "$0;"
   Call un.StrStr
   Pop $2
   StrCmp $2 "" done
   
   StrLen $3 "$0;"
   StrLen $4 $2
   StrCpy $5 $1 -$4 # ������ �κ� ��������
   StrCpy $6 $2 "" $3 # ������ �κ� ���ĺ���
   StrCpy $3 "$5$6"
   
   StrCpy $5 $3 1 -1 # ������ ���� Ȯ��
   ${If} $5 == ";"
      StrCpy $3 $3 -1 # ������ �����ݷ� ����
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