; Remote Server — Windows installer (Inno Setup 6).
; Qurish:  ISCC.exe installer\RemoteServer.iss   ->  dist\RemoteServer-Setup.exe
; Avval exe: pyinstaller RemoteServer.spec  ->  dist\RemoteServer.exe
;
; Nima qiladi: Program Files'ga o'rnatadi, Start menyu (Windows qidiruvida chiqadi) va ish stoli yorlig'i,
; Windows bilan birga ishga tushish (shell:startup), Firewall ruxsati (barcha tarmoq turlari — telefon
; Wi-Fi / USB modem orqali ulanishi uchun), ochiq dasturni yopib yangilaydi, uninstall.

#define AppName "Remote Server"
#define AppExe "RemoteServer.exe"
#define AppVersion "1.1.0"

[Setup]
AppId={{6C0E5B7A-2F4D-4B8E-9D3A-7E1F2C5B8A90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
UsedUserAreasWarning=no
OutputDir=..\dist
OutputBaseFilename=RemoteServer-Setup
SetupIconFile=..\server-win\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Ish stolida yorliq yaratish"
Name: "autostart"; Description: "Windows bilan birga ishga tushsin (masofadan ulanish uchun tavsiya etiladi)"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; avvalgi qo'lda o'rnatilgan nusxa va uning yorliqlari
Type: files; Name: "{userdesktop}\RemoteServer - ilova.lnk"
Type: files; Name: "{userprograms}\RemoteServer.lnk"
Type: filesandordirs; Name: "{localappdata}\Programs\RemoteServer"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; dastur ham shu yorliqni o'zi yangilab turadi (sozlamalardagi "Windows bilan birga ishga tushsin")
Name: "{userstartup}\RemoteServer"; Filename: "{app}\{#AppExe}"; Parameters: "--autostart"; Tasks: autostart

[Run]
; Firewall: telefon lokal tarmoqdan ulanishi uchun (Domain + Private + Public). Faqat administrator o'rnatmasida.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=any"; Flags: runhidden; Check: IsAdminInstallMode
Filename: "{app}\{#AppExe}"; Description: "{#AppName}'ni ishga tushirish"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "DelFirewall"

[UninstallDelete]
Type: files; Name: "{userstartup}\RemoteServer.lnk"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  // ochiq dastur fayllarni band qiladi — yangilashdan oldin yopamiz
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
