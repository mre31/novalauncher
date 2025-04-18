#define MyAppName "Nova Launcher"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "NovaWeb"
#define MyAppExeName "NovaLauncher.exe"
#define SourceDir "dist"
#define MyAppInstallDirName ".novalauncher"

[Setup]
AppId={{F5A1B2C3-D4E5-F6A7-B8C9-D0E1F2A3B4C5}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userappdata}\{#MyAppInstallDirName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=NovaLauncherSetup
SetupIconFile=resources\logo.ico
WizardImageFile=resources\header.bmp
WizardSmallImageFile=resources\N.bmp
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";

[Files]
Source: "{#SourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CleanInstallCheckBox: TNewCheckBox;

procedure InitializeWizard();
var
  TasksPage: TWizardPage;
  Offset: Integer;
begin
  TasksPage := PageFromID(wpSelectTasks);
  Offset := ScaleY(20);

  CleanInstallCheckBox := TNewCheckBox.Create(WizardForm);
  CleanInstallCheckBox.Parent := TasksPage.Surface;
  CleanInstallCheckBox.Top := WizardForm.TasksList.Top + WizardForm.TasksList.Height + Offset;
  CleanInstallCheckBox.Left := WizardForm.TasksList.Left;
  CleanInstallCheckBox.Width := WizardForm.TasksList.Width;
  CleanInstallCheckBox.Height := ScaleY(17);
  CleanInstallCheckBox.Caption := 'Perform clean install (Deletes %APPDATA%\.minecraft!)';
  CleanInstallCheckBox.Checked := False;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  MinecraftDir: String;
  Msg: String;
begin
  if CurPageID = wpSelectTasks then
  begin
    MinecraftDir := ExpandConstant('{userappdata}\.minecraft');
    
    if CleanInstallCheckBox.Checked then
    begin
      Msg := 'WARNING: You have selected "Clean Install".' + #13#10 +
             'This option will PERMANENTLY DELETE the entire folder:' + #13#10 + MinecraftDir + #13#10 +
             'This includes ALL your worlds, resource packs, mods, settings, etc. in that folder.' + #13#10 +
             'Are you absolutely sure you want to proceed?';
      if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
      begin
        CleanInstallCheckBox.Checked := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  MinecraftDir: String;
begin
  if (CurStep = ssPostInstall) and CleanInstallCheckBox.Checked then
  begin
    MinecraftDir := ExpandConstant('{userappdata}\.minecraft');
    if DirExists(MinecraftDir) then
    begin
      if MsgBox('Final Warning: About to delete ' + MinecraftDir + ' including your saves. Continue?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        if not DelTree(MinecraftDir, True, True, True) then
        begin
          MsgBox('Could not completely delete the folder: ' + MinecraftDir + #13#10 + 'You might need to delete it manually.', mbError, MB_OK);
        end;
      end;
    end;
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}"