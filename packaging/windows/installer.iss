; Inno Setup script for the Job Pilot installer; packaging\build_windows.ps1 runs it after PyInstaller.
; It installs for the current user only, so it needs no administrator rights. The data in
; %APPDATA%\JobPilot (jobs, companies, settings) stays when Job Pilot is uninstalled.

#define AppVersion "0.1.0"

[Setup]
AppId={{6F2C9B1E-4D7A-4E5B-9C3F-1A8D2E7B5C40}
AppName=Job Pilot
AppVersion={#AppVersion}
AppVerName=Job Pilot {#AppVersion}
DefaultDirName={autopf}\Job Pilot
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=JobPilot-Setup-{#AppVersion}
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\Job Pilot.exe
UninstallDisplayName=Job Pilot
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Closes a running Job Pilot before updating it.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\Job Pilot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Job Pilot"; Filename: "{app}\Job Pilot.exe"
Name: "{autodesktop}\Job Pilot"; Filename: "{app}\Job Pilot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Job Pilot.exe"; Description: "Open Job Pilot"; Flags: nowait postinstall skipifsilent
