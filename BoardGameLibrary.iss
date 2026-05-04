; Board Game Library — Inno Setup installer script
; Build after running PyInstaller:
;   "C:\Users\tballew\AppData\Local\Programs\Inno Setup 6\ISCC.exe" BoardGameLibrary.iss

#define AppName      "Board Game Library"
#define AppVersion   "1.1"
#define AppPublisher "Ballewcifer"
#define AppExeName   "BoardGameLibrary.exe"
#define SourceDir    "dist\BoardGameLibrary"

[Setup]
; Unique GUID — do NOT change after first release (used for upgrade detection)
AppId={{D4E8F123-9A2B-4C5D-8E6F-01234567890A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright=Copyright (C) 2026 {#AppPublisher}

; Install to Program Files by default; user-level install is also allowed
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Output
OutputDir=installer
OutputBaseFilename=BoardGameLibrarySetup-v{#AppVersion}
SetupIconFile=icon.ico

; Compression
Compression=lzma2/ultra
SolidCompression=yes

; Appearance
WizardStyle=modern
WizardSizePercent=120
DisableDirPage=no
DisableProgramGroupPage=yes

; Misc
AllowNoIcons=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; All PyInstaller output — recurse so _internal/ folder is included
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}";        Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}";         Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove any pyc caches left in the install dir
Type: filesandordirs; Name: "{app}\__pycache__"
