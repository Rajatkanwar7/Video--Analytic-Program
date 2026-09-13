#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
[Setup]
AppId={{F79F3846-EC5B-4407-A62D-70D034858C76}
AppName=JailWatch VMS
AppVersion={#AppVersion}
AppPublisher=JailWatch Project
AppPublisherURL=https://github.com/Rajatkanwar7/Video--Analytic-Program
DefaultDirName={localappdata}\Programs\JailWatchVMS
DefaultGroupName=JailWatch VMS
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=JailWatchVMS-Setup-{#AppVersion}-x64
SetupIconFile=..\build_assets\jailwatch.ico
UninstallDisplayIcon={app}\JailWatchVMS.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
LicenseFile=..\docs\THIRD_PARTY.md

[Files]
Source: "..\dist\JailWatchVMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\JailWatch VMS"; Filename: "{app}\JailWatchVMS.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\JailWatch VMS"; Filename: "{app}\JailWatchVMS.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\JailWatchVMS.exe"; Description: "Open JailWatch VMS"; Flags: nowait postinstall skipifsilent
