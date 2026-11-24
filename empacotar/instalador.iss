; Instalador do Cortes Grátis (Inno Setup 6). Gerado pelo empacotar\construir.ps1.
; Instala sem pedir admin, na pasta que a pessoa escolher (ex.: F:\Cortes Gratis).
; Tudo que o programa baixa depois (modelos, IA local, clipes) fica em <pasta>\dados.

#ifndef Versao
  #define Versao "0.0.0"
#endif

[Setup]
AppId={{6C3F2A1E-8B7D-4E1A-9C55-2F0D7A9E4B31}
AppName=Cortes Grátis
AppVersion={#Versao}
AppPublisher=Vinicius Montanari
AppPublisherURL=https://github.com/Vinicius-Montanari/cortes-gratis
AppSupportURL=https://github.com/Vinicius-Montanari/cortes-gratis/issues
DefaultDirName={localappdata}\Programs\Cortes Gratis
DisableDirPage=no
DefaultGroupName=Cortes Grátis
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=CortesGratis-{#Versao}-instalador
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\Cortes Gratis.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\build\pyinstaller\dist\Cortes Gratis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cortes Grátis"; Filename: "{app}\Cortes Gratis.exe"
Name: "{group}\Pasta dos clipes"; Filename: "{app}\dados\projetos"
Name: "{group}\Instalar IA local"; Filename: "{app}\Cortes Gratis.exe"; Parameters: "--instalar-ia-local"; Comment: "Instala a IA local mostrando cada passo"
Name: "{group}\Desinstalar o Cortes Grátis"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cortes Grátis"; Filename: "{app}\Cortes Gratis.exe"; Tasks: atalho

[Dirs]
Name: "{app}\dados\projetos"

[Run]
Filename: "{app}\Cortes Gratis.exe"; Description: "Abrir o Cortes Grátis agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Garante que o programa e a IA local estão fechados antes de apagar.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""Cortes Gratis.exe"" /T"; Flags: runhidden; RunOnceId: "FecharPrograma"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if DirExists(ExpandConstant('{app}\dados')) then
      if MsgBox('Apagar também os clipes, as configurações, os modelos e a IA local baixados?' + #13#10 + #13#10 +
                'Pasta: ' + ExpandConstant('{app}\dados') + #13#10 + #13#10 +
                'Escolha Não se quiser guardar os clipes ou reinstalar depois sem baixar tudo de novo.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{app}'), True, True, True);
end;
