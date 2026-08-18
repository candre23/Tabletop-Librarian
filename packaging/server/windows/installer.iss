#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #error SourceDir must point to the PyInstaller Server output directory.
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef IconFile
  #define IconFile "..\..\windows\ttl.ico"
#endif
#ifndef RepoRoot
  #define RepoRoot "..\..\.."
#endif

[Setup]
AppId={{8D0D1D1E-32E9-4C2A-BDC4-48B31A2C538A}
AppName=Tabletop Librarian Server
AppVersion={#AppVersion}
AppPublisher=Tabletop Librarian
DefaultDirName={autopf64}\Tabletop Librarian Server
DefaultGroupName=Tabletop Librarian
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=TTL-Server-Windows-x64-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\TTL-Server-Manager.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile={#RepoRoot}\LICENSE
CloseApplications=yes
RestartApplications=no

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\README.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\INSTALLATION.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\USER_GUIDE.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\SYSTEM_PACKS.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\OCR.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\PIPELINES.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\reference\*"; DestDir: "{app}\documentation\reference"; Flags: ignoreversion recursesubdirs createallsubdirs


[Dirs]
Name: "{commonappdata}\Tabletop Librarian"; Permissions: users-modify
Name: "{commonappdata}\Tabletop Librarian\data"; Permissions: users-modify
Name: "{commonappdata}\Tabletop Librarian\cache"; Permissions: users-modify
Name: "{commonappdata}\Tabletop Librarian\logs"; Permissions: users-modify

[Tasks]
Name: "autostart"; Description: "Start the TTL Server automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "firewall"; Description: "Allow other computers on my local network to access TTL"; GroupDescription: "Network access:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\TTL Server Manager"; Filename: "{app}\TTL-Server-Manager.exe"
Name: "{group}\Open Tabletop Librarian"; Filename: "http://127.0.0.1:{code:GetSelectedPort}"
Name: "{group}\TTL Server Log"; Filename: "{sys}\notepad.exe"; Parameters: """{commonappdata}\Tabletop Librarian\logs\server.log"""
Name: "{autodesktop}\TTL Server Manager"; Filename: "{app}\TTL-Server-Manager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TTL-Server-Manager.exe"; Parameters: "--start"; Description: "Launch TTL Server Manager"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Tabletop-Librarian-Server.exe"; Flags: runhidden waituntilterminated; RunOnceId: StopTTLServer
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TTL-Server-Manager.exe"; Flags: runhidden waituntilterminated; RunOnceId: StopTTLManager
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Tabletop Librarian Server"" /F"; Flags: runhidden waituntilterminated; RunOnceId: RemoveTTLTask
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tabletop Librarian Server"""; Flags: runhidden waituntilterminated; RunOnceId: RemoveTTLFirewall

[Code]
var
  PortPage: TInputQueryWizardPage;
  ExistingInstall: Boolean;
  SelectedPort: Integer;

function ConfigPath(): String;
begin
  Result := ExpandConstant('{commonappdata}\Tabletop Librarian\server.ini');
end;

function DetectExistingInstall(): Boolean;
begin
  // Do not expand the application-directory constant here.
  // InitializeWizard runs before Inno Setup has initialized that directory.
  // The persistent server config is safe to query during wizard initialization.
  Result := FileExists(ConfigPath());
end;

function ReadExistingPort(): Integer;
begin
  Result := StrToIntDef(GetIniString('server', 'port', '8080', ConfigPath()), 8080);
  if (Result < 1) or (Result > 65535) then Result := 8080;
end;

function GetSelectedPort(Param: String): String;
begin
  Result := IntToStr(SelectedPort);
end;

function PortAvailable(Port: Integer): Boolean;
var
  ResultCode: Integer;
  Params: String;
begin
  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"if (Get-NetTCPConnection -State Listen -LocalPort ' + IntToStr(Port) +
    ' -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"';
  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode = 0
  else
    Result := True;
end;

procedure InitializeWizard();
begin
  ExistingInstall := DetectExistingInstall();
  SelectedPort := ReadExistingPort();
  PortPage := CreateInputQueryPage(wpSelectDir,
    'Server Port',
    'Choose the TCP port for Tabletop Librarian.',
    '8080 is the default. Change it if another service already uses that port.');
  PortPage.Add('Port:', False);
  PortPage.Values[0] := IntToStr(SelectedPort);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ExistingInstall and (PageID = PortPage.ID);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  P: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then begin
    P := StrToIntDef(Trim(PortPage.Values[0]), 0);
    if (P < 1) or (P > 65535) then begin
      MsgBox('Enter a TCP port from 1 through 65535.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if not PortAvailable(P) then begin
      MsgBox('Port ' + IntToStr(P) + ' is already in use. Choose another port.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    SelectedPort := P;
  end;
end;

procedure StopExistingServer();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Tabletop Librarian Server"', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Tabletop-Librarian-Server.exe', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM TTL-Server-Manager.exe', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
end;

procedure ConfigureStartupTask();
var
  ResultCode: Integer;
  Params: String;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN "Tabletop Librarian Server" /F', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  if WizardIsTaskSelected('autostart') then begin
    Params := '/Create /SC ONLOGON /TN "Tabletop Librarian Server" /TR """' +
      ExpandConstant('{app}\TTL-Server-Manager.exe') + '"" --start --minimized" /F';
    Exec(ExpandConstant('{sys}\schtasks.exe'), Params, '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure ConfigureFirewall();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="Tabletop Librarian Server"', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  if WizardIsTaskSelected('firewall') then
    Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall add rule name="Tabletop Librarian Server" dir=in action=allow protocol=TCP localport=' + IntToStr(SelectedPort), '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopExistingServer();
  if CurStep = ssPostInstall then begin
    ForceDirectories(ExpandConstant('{commonappdata}\Tabletop Librarian'));
    SetIniString('server', 'host', '0.0.0.0', ConfigPath());
    SetIniString('server', 'port', IntToStr(SelectedPort), ConfigPath());
    ConfigureStartupTask();
    ConfigureFirewall();
  end;
end;
