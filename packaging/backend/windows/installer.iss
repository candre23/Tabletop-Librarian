#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceExe
  #error SourceExe must point to TTL-AI-Backend.exe.
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
AppId={{75CA1E85-839D-45C7-B034-299984D4A62C}
AppName=TTL Local AI Backend
AppVersion={#AppVersion}
AppPublisher=Tabletop Librarian
DefaultDirName={autopf64}\TTL AI Backend
DefaultGroupName=Tabletop Librarian
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=TTL-AI-Windows-x64-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\TTL-AI-Backend.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile={#RepoRoot}\LICENSE
CloseApplications=yes
RestartApplications=no

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "TTL-AI-Backend.exe"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\README.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\INSTALLATION.md"; DestDir: "{app}\documentation"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\AI_BACKEND.md"; DestDir: "{app}\documentation"; Flags: ignoreversion


[Tasks]
Name: "firewall"; Description: "Allow Tabletop Librarian machines on my local network to reach this backend"; GroupDescription: "Network access:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Icons]
Name: "{group}\TTL AI Backend"; Filename: "{app}\TTL-AI-Backend.exe"
Name: "{autodesktop}\TTL AI Backend"; Filename: "{app}\TTL-AI-Backend.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TTL-AI-Backend.exe"; Description: "Launch TTL AI Backend"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TTL-AI-Backend.exe"; Flags: runhidden waituntilterminated; RunOnceId: StopTTLBackend
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TTL AI Backend"""; Flags: runhidden waituntilterminated; RunOnceId: RemoveTTLBackendFirewall

[Code]
var
  PortPage: TInputQueryWizardPage;
  ExistingInstall: Boolean;
  SelectedPort: Integer;

function BackendSettingsPath(): String;
begin
  Result := ExpandConstant('{userappdata}\Tabletop Librarian\AI Backend\settings.json');
end;

function DetectExistingInstall(): Boolean;
begin
  // Do not expand the application-directory constant here.
  // InitializeWizard runs before Inno Setup has initialized that directory.
  // Persistent backend settings are safe to query during wizard initialization.
  Result := FileExists(BackendSettingsPath());
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
  SelectedPort := 8081;
  PortPage := CreateInputQueryPage(wpSelectDir,
    'AI Backend Port',
    'Choose the TCP port for the local AI backend.',
    '8081 is the default. Change it if another service already uses that port.');
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

procedure ConfigureBackendPort();
var
  ResultCode: Integer;
begin
  if not ExistingInstall then
    ExecAsOriginalUser(ExpandConstant('{app}\TTL-AI-Backend.exe'), '--set-port ' + IntToStr(SelectedPort), '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
end;

procedure ConfigureFirewall();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="TTL AI Backend"', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  if WizardIsTaskSelected('firewall') then
    Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall add rule name="TTL AI Backend" dir=in action=allow protocol=TCP localport=' + IntToStr(SelectedPort), '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    ConfigureBackendPort();
    if not ExistingInstall then
      ConfigureFirewall();
  end;
end;
