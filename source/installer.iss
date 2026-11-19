#ifndef AppSource
  #error AppSource must point to the frozen PikeCountyWC directory
#endif
#ifndef OutputFolder
  #define OutputFolder "."
#endif

[Setup]
AppId={{F5044538-CC2F-4F1C-BB2E-719E75AF0131}
AppName=Worthless Check
AppVersion=1.0.0-rc66
AppVerName=Worthless Check 1.0.0-rc66
AppPublisher=Worthless Check
DefaultDirName={autopf}\Worthless Check
DefaultGroupName=Worthless Check
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
SetupArchitecture=x64
MinVersion=10.0.20348
OutputDir={#OutputFolder}
OutputBaseFilename=Worthless-Check-Setup-rc66
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
VersionInfoVersion=1.0.0.66
VersionInfoDescription=Worthless Check Setup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked; Check: not IsExtractOnly

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "DEPLOYMENT-READ-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "returned-check.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Worthless Check"; Filename: "{app}\PikeCountyWC.exe"; WorkingDir: "{app}"; IconFilename: "{app}\returned-check.ico"; Check: not IsExtractOnly
Name: "{group}\Deployment Notes"; Filename: "{app}\DEPLOYMENT-READ-ME.txt"; Check: not IsExtractOnly
Name: "{autodesktop}\Worthless Check"; Filename: "{app}\PikeCountyWC.exe"; WorkingDir: "{app}"; IconFilename: "{app}\returned-check.ico"; Check: ShouldCreateDesktopShortcut

[Run]
Filename: "{app}\PikeCountyWC.exe"; Description: "Open Worthless Check"; Flags: postinstall nowait skipifsilent unchecked; Check: not IsExtractOnly

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
    (WizardIsTaskSelected('desktopicon') or FileExists(OldDesktopShortcut) or
     FileExists(ExpandConstant('{autodesktop}\Check Management.lnk')));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not IsExtractOnly then begin
    if FileExists(ExpandConstant('{autodesktop}\Worthless Check.lnk')) and
      FileExists(ExpandConstant('{autodesktop}\Check Management.lnk')) then
      DeleteFile(ExpandConstant('{autodesktop}\Check Management.lnk'));
    if FileExists(ExpandConstant('{autodesktop}\Worthless Check.lnk')) and
      FileExists(OldDesktopShortcut) then
      DeleteFile(OldDesktopShortcut);
    if FileExists(ExpandConstant('{group}\Worthless Check.lnk')) then
      DeleteFile(ExpandConstant('{group}\Pike County Worthless Check Unit.lnk'));
  end;
end;
