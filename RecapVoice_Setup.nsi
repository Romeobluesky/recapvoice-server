!define APP_NAME "Recap Voice"
!define VERSION "1.103"
!define INSTALL_DIR "$PROGRAMFILES64\${APP_NAME}"

Name "${APP_NAME}"
OutFile "RecapVoice_Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

# ���� ���� �߰�
VIProductVersion "1.1.0.3"
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
!include "nsisunz.nsh"

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
   # Wireshark & TShark ��ġ
   DetailPrint "Installing Wireshark and TShark..."
   File "prereq\Wireshark-4.4.2-x64.exe"
   ExecWait '"$INSTDIR\prereq\Wireshark-4.4.2-x64.exe" /S /componentstrue=TShark'
   
   # Npcap ��ġ
   DetailPrint "Installing Npcap..."
   File "prereq\npcap-1.80.exe"
   ExecWait '"$INSTDIR\prereq\npcap-1.80.exe" /S'
   
   # FFmpeg ��ġ
   DetailPrint "Installing FFmpeg..."
   CreateDirectory "C:\Program Files\ffmpeg"
   SetOutPath "C:\Program Files\ffmpeg"
   File /r "prereq\ffmpeg\*.*"
   
   # FFmpeg bin ������ �ִ��� Ȯ��
   ${If} ${FileExists} "C:\Program Files\ffmpeg\bin\ffmpeg.exe"
       Push "C:\Program Files\ffmpeg\bin"
       Call AddToPath
   ${EndIf}
   
   # WIRESHARK_PATH ���� �ڵ� ����
SectionEnd

Section "MainSection"
   SetOutPath "$INSTDIR"
   
   # ���� ���α׷� ���� ����
   File /r "dist\Recap Voice\*.*"
   File /r "mongodb"
   File /r "nginx"
   
   # settings.ini ���� �� ����
   File "settings.ini"
   # ��� ����
   !define SAVE_PATH_FIND "D:/PacketWaveRecord"
   !define SAVE_PATH_REPLACE "$DOCUMENTS\RecapVoiceRecord"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "${SAVE_PATH_FIND}" "${SAVE_PATH_REPLACE}"
   # Extension ���� ��ҹ��� ����
   !define SECTION_FIND "[Extension]"
   !define SECTION_REPLACE "[extension]"
   !insertmacro ReplaceInFile "$INSTDIR\settings.ini" "${SECTION_FIND}" "${SECTION_REPLACE}"
   
   File "start.bat"
   
   # packetwave_client ���� ����
   DetailPrint "Copying packetwave_client..."
   RMDir /r "$INSTDIR\packetwave_client"    # ���� ���� ����
   CreateDirectory "$INSTDIR\packetwave_client"
   SetOutPath "$INSTDIR\packetwave_client"   # ��� ������ ����
   File /r "packetwave_client\*.*"          # ���� ���� ����
   SetOutPath "$INSTDIR"                    # ���� ��η� ����
   
   # ȯ�溯�� ����
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
   
   # �ٷΰ��� ����
   CreateDirectory "$SMPROGRAMS\${APP_NAME}"
   CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe" "" "$INSTDIR\Recap Voice.exe" 0 SW_SHOWNORMAL "" "Recap Voice Application"
   CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Recap Voice.exe" "" "$INSTDIR\Recap Voice.exe" 0

   # ������ ������ ���� ���丮 ����
   SetShellVarContext current
   CreateDirectory "$DOCUMENTS\RecapVoiceRecord"
   ExecWait 'cmd.exe /C icacls "$DOCUMENTS\RecapVoiceRecord" /grant Everyone:(OI)(CI)F'
   
   WriteUninstaller "$INSTDIR\uninstall.exe"
   
   # ������ ���α׷� ��Ͽ� �߰�
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
   # �������� �����ݷ��� ������ �߰�
   ${If} $1 != ""
       StrCpy $3 $1 1 -1
       ${If} $3 != ";"
           StrCpy $1 "$1;"
       ${EndIf}
   ${EndIf}
   
   # �� ��� �߰�
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
   
   # ������ ������ RecapVoiceRecord ���� ���� Ȯ��
   MessageBox MB_YESNO "���� ���� ������ ����� ������ �����Ͻðڽ��ϱ�?" IDNO skip_delete_records
   SetShellVarContext current
   RMDir /r "$DOCUMENTS\RecapVoiceRecord"
   skip_delete_records:
   
   # �����ǿ��� ���α׷� ����
   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
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