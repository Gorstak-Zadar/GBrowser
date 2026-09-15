; GBrowser Inno Setup Script
#define MyAppName "GBrowser"
#define MyAppVersion "0.6.1"
#define MyAppPublisher "Gorstak"
#define MyAppExeName "GBrowser.exe"
#define MyAppIcon "GBrowser.ico"

[Setup]
AppId={{f1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppIcon}
SetupIconFile={#MyAppIcon}
Compression=lzma2
SolidCompression=yes
OutputDir=releases\{#MyAppVersion}
OutputBaseFilename=GBrowser-{#MyAppVersion}-Setup
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\GBrowser\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GBrowser\{#MyAppIcon}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GBrowser\*.dll"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "dist\GBrowser\*.pyd"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "dist\GBrowser\blocklist.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GBrowser\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
