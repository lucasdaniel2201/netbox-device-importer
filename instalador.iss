; Instalador do Importador de Cameras (Inno Setup 6)
;
; Compilar com:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador.iss
;
; Instalacao POR USUARIO (sem precisar de administrador) em
; %LOCALAPPDATA%\Programs\Importador de Cameras. Essa pasta e gravavel, entao os
; relatorios continuam sendo salvos ao lado do executavel.

#define AppName "Importador de Cameras"
#define AppVersion "1.0.0"
#define AppPublisher "L&K Tecnologia"
#define AppExeName "ImportadorCameras.exe"
#define SourceExe "dist\ImportadorCameras.exe"
#define SourceIcon "app\assets\app_icon.ico"

[Setup]
; O AppId identifica o aplicativo: mantem o mesmo para permitir atualizar por cima
; e desinstalar corretamente. Nunca mude entre versoes.
AppId={{1087554C-D6E0-483E-846B-EDD8DB219EFD}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Instalador do {#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=ImportadorCamerasSetup-{#AppVersion}
SetupIconFile={#SourceIcon}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: {#SourceExe}; DestDir: {app}; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent
