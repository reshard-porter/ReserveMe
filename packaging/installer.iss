; Inno Setup script — builds ReserveMe-Setup-<version>.exe from dist\ReserveMe
; Compile with:  iscc packaging\installer.iss   (run from the project folder after PyInstaller)

#define AppName "ReserveMe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6E0F2C7A-3B57-4E7B-9C1D-5A2B8E4F1A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ReserveMe
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ReserveMe-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ReserveMe.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\ReserveMe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ReserveMe.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ReserveMe.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ReserveMe.exe"; Description: "Start ReserveMe"; Flags: nowait postinstall skipifsilent
