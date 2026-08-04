; AICE Simulator 설치 프로그램 (Inno Setup 스크립트)
#define MyAppName "AICE Simulator"
#define MyAppVersion "1.0"
#define MyAppPublisher "따라하며 끝내는 시리즈"
#define MyAppExeName "AICE_Simulator.exe"

[Setup]
AppId={{8F2C1A3E-4B5D-4E6F-9A1B-2C3D4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 관리자 권한 없이 사용자 폴더에도 설치 가능하게(Program Files 권한 문제 회피)
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=AICE_Simulator_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked

[Files]
Source: "dist\AICE_Simulator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "설치 후 바로 실행하기"; Flags: nowait postinstall skipifsilent
