#ifndef AppSource
  #error AppSource must point to the frozen PikeCountyWC directory
#endif
#ifndef OutputFolder
  #define OutputFolder "."
#endif

[Setup]
AppId={{F5044538-CC2F-4F1C-BB2E-719E75AF0131}
AppName=Pike County Worthless Check Unit - Server Evaluation
AppVersion=1.0.0-rc63
AppVerName=Pike County Worthless Check Unit 1.0.0-rc63
AppPublisher=Pike County Worthless Check Unit
DefaultDirName={autopf}\Pike County Worthless Check Unit
DefaultGroupName=Pike County Worthless Check Unit
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
SetupArchitecture=x64
MinVersion=10.0.20348
OutputDir={#OutputFolder}
OutputBaseFilename=WC-Server2022-Setup-rc63
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=INSTALLER-SCOPE.txt
UninstallDisplayIcon={app}\PikeCountyWC.exe
Uninstallable=not IsExtractOnly
UsePreviousAppDir=not IsExtractOnly
CloseApplications=yes
RestartApplications=no
AppMutex=PikeCountyWCInstallerEvaluation
VersionInfoVersion=1.0.0.63
VersionInfoDescription=Pike County Worthless Check Unit Server Evaluation Setup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked; Check: not IsExtractOnly

[Dirs]
Name: "{commonappdata}\PikeCountyWC-ServerEvaluation\Data"; Flags: uninsneveruninstall; Check: not IsExtractOnly

Name: "{commonappdata}\PikeCountyWC-ServerEvaluation\EnterpriseData"; Flags: uninsneveruninstall; Check: not IsExtractOnly

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "DEPLOYMENT-READ-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "returned-check.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\DA12th Worthless Check"; Filename: "{app}\PikeCountyWC.exe"; WorkingDir: "{app}"; IconFilename: "{app}\returned-check.ico"; Check: not IsExtractOnly
Name: "{group}\Deployment Notes"; Filename: "{app}\DEPLOYMENT-READ-ME.txt"; Check: not IsExtractOnly
Name: "{autodesktop}\DA12th Worthless Check"; Filename: "{app}\PikeCountyWC.exe"; WorkingDir: "{app}"; IconFilename: "{app}\returned-check.ico"; Check: ShouldCreateDesktopShortcut

[Run]
Filename: "{app}\PikeCountyWC.exe"; Description: "Open Pike County Worthless Check Unit"; Flags: postinstall nowait skipifsilent unchecked; Check: not IsExtractOnly

[Code]
function IsExtractOnly: Boolean;
begin
  Result := ExpandConstant('{param:EXTRACTONLY|0}') = '1';
end;

function OldDesktopShortcut: String;
begin
  Result := ExpandConstant('{autodesktop}\Pike County Worthless Check Unit.lnk');
end;

function ShouldCreateDesktopShortcut: Boolean;
begin
  Result := not IsExtractOnly and
    (WizardIsTaskSelected('desktopicon') or FileExists(OldDesktopShortcut));
end;

function EnsureGroup(GroupName: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if not Exec(ExpandConstant('{sys}\net.exe'), 'localgroup ' + GroupName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then Exit;
  if ResultCode = 0 then begin
    Result := True;
    Exit;
  end;
  Result := Exec(ExpandConstant('{sys}\net.exe'), 'localgroup ' + GroupName + ' /add', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if IsExtractOnly then Exit;
  if not IsAdmin then begin
    Result := 'Run this installer as a server Administrator.';
    Exit;
  end;
  if not EnsureGroup('PikeCountyWCUsers') then
    Result := 'Could not configure the PikeCountyWCUsers local group.'
  else if not EnsureGroup('EnterpriseWCUsers') then
    Result := 'Could not configure the EnterpriseWCUsers local group.';
end;

procedure ProtectDivision(Folder, GroupName: String);
var
  Parameters: String;
  ResultCode: Integer;
begin
  Parameters := '"' + Folder + '" /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "' +
    ExpandConstant('{computername}') + '\' + GroupName + ':(OI)(CI)M"';
  if (not Exec(ExpandConstant('{sys}\icacls.exe'), Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    RaiseException('Could not configure data folder permissions for ' + GroupName + '.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not IsExtractOnly then begin
    ProtectDivision(ExpandConstant('{commonappdata}\PikeCountyWC-ServerEvaluation\Data'), 'PikeCountyWCUsers');
    ProtectDivision(ExpandConstant('{commonappdata}\PikeCountyWC-ServerEvaluation\EnterpriseData'), 'EnterpriseWCUsers');
    if FileExists(ExpandConstant('{autodesktop}\DA12th Worthless Check.lnk')) and
      FileExists(OldDesktopShortcut) then
      DeleteFile(OldDesktopShortcut);
    if FileExists(ExpandConstant('{group}\DA12th Worthless Check.lnk')) then
      DeleteFile(ExpandConstant('{group}\Pike County Worthless Check Unit.lnk'));
  end;
end;
