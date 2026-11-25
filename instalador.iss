; Instalador do Importador de Cameras (Inno Setup 6)
;
; Compilar com:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador.iss
;
; Instalacao POR USUARIO (sem precisar de administrador) em
; %LOCALAPPDATA%\Programs\Importador de Cameras. Essa pasta e gravavel, entao os
; relatorios continuam sendo salvos ao lado do executavel.

#define AppName "Importador de Cameras"
#define AppVersion "1.3.2"
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
; Fecha o app sozinho durante o upgrade. O Windows trava o .exe em uso: sem isso
; o setup falha ao substituir o arquivo ("sem permissao para mover o .exe") -
; era o que acontecia quando o proprio app abria o instalador com a janela aberta.
; `force` nao pergunta nada (o app nao tem dado nao salvo) e vale inclusive para
; quem ainda esta numa versao antiga, cuja logica de fechar o app era falha.
CloseApplications=force
; Quem reabre o app ao final e o [Run] abaixo; o Restart Manager nao precisa
; relancar uma copia por conta propria.
RestartApplications=no
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
; O app e aberto pelo cmd com PYINSTALLER_RESET_ENVIRONMENT=1 de proposito.
;
; Quem instala uma atualizacao costuma chegar aqui pelo proprio app: ele baixa o
; Setup, agenda a instalacao e fecha. O app e um executavel *onefile* do
; PyInstaller, e enquanto roda ele mantem no ambiente `_PYI_ARCHIVE_FILE`,
; `_PYI_APPLICATION_HOME_DIR` e `_PYI_PARENT_PROCESS_LEVEL`. O Setup herda isso e
; repassa ao `.exe` abaixo - e o bootloader do `.exe`, vendo `_PYI_ARCHIVE_FILE`
; igual ao proprio caminho (a atualizacao e por cima, mesmo arquivo), conclui que
; e o processo FILHO do app antigo. Resultado: nao extrai nada, procura
; `python312.dll` na pasta `_MEI` do app anterior (ja apagada) e a primeira
; abertura depois de instalar falha com:
;   "Failed to load Python DLL ...\LoadLibrary: nao foi possivel encontrar o modulo"
; Abrir de novo pelo atalho funcionava, porque o atalho nao traz esse ambiente.
;
; `PYINSTALLER_RESET_ENVIRONMENT=1` e o mecanismo oficial do bootloader para
; "ignore o ambiente herdado e comece do zero": ele le a variavel, descarta as
; demais `_PYI_*` e se comporta como processo de topo. Assim funciona mesmo para
; quem ainda esta em versao antiga, cujo codigo nao limpa o ambiente ao agendar.
;
; Detalhes que parecem cosmeticos e nao sao:
;   - `set "VAR=1"` com as aspas: escrito como `set VAR=1 &`, o cmd define o valor
;     como "1 " (com espaco no fim), e o bootloader compara com "1" exato - o
;     reset seria ignorado em silencio. Verificado com `cmd /v:on`: com aspas da
;     `[1]`, sem aspas da `[1 ]`;
;   - `runhidden`: esconde a janela do cmd, senao pisca um console preto ao abrir;
;   - `start "" "caminho"`: o primeiro "" e o titulo da janela; sem ele o cmd
;     trataria o caminho como titulo.
Filename: "{cmd}"; Parameters: "/c set ""PYINSTALLER_RESET_ENVIRONMENT=1"" & start """" ""{app}\{#AppExeName}"""; Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent runhidden
