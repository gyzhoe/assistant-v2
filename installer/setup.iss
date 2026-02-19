; setup.iss — AI Helpdesk Assistant Inno Setup Script
; Builds a per-user installer for Windows 10/11 x64.
; Compile with: iscc /DMyAppVersion=1.0.0 setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName     "AI Helpdesk Assistant"
#define MyAppPublisher "AI Helpdesk"
#define MyAppURL      "https://github.com/gyzhoe/assistant"

[Setup]
AppId={{B8F2A1D4-7E3C-4A90-9D5F-1C6E8B4A2F07}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\AIHelpdeskAssistant
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=AIHelpdeskAssistant-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
LicenseFile=assets\license.txt
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Local AI assistant for SolarWinds Web Help Desk

[Types]
Name: "full";   Description: "Full installation (recommended)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "backend";   Description: "Backend Service (FastAPI + Python)";           Types: full custom; Flags: fixed
Name: "extension"; Description: "Edge Extension (pre-built)";                   Types: full custom; Flags: fixed
Name: "ollama";    Description: "Ollama LLM Runtime (~100 MB)";                 Types: full custom
Name: "models";    Description: "Download LLM models after install (~2.3 GB)";  Types: full custom
Name: "service";   Description: "Register backend as Windows Service (auto-start)"; Types: full custom

[Dirs]
Name: "{app}\logs"
Name: "{app}\backend\chroma_data"

[Files]
; Backend source
Source: "..\backend\app\*";           DestDir: "{app}\backend\app";       Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend
Source: "..\backend\ingestion\*";     DestDir: "{app}\backend\ingestion"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend
Source: "..\backend\pyproject.toml";  DestDir: "{app}\backend";           Flags: ignoreversion; Components: backend

; Extension dist (pre-built by CI)
Source: "..\extension\dist\*";        DestDir: "{app}\extension";         Flags: ignoreversion recursesubdirs createallsubdirs; Components: extension

; uv standalone binary (downloaded by CI)
Source: "deps\uv.exe";               DestDir: "{app}\tools";             Flags: ignoreversion; Components: backend

; NSSM for service registration (downloaded by CI)
Source: "nssm\nssm.exe";             DestDir: "{app}\tools";             Flags: ignoreversion; Components: service

; Ollama installer (downloaded by CI)
Source: "deps\OllamaSetup.exe";      DestDir: "{tmp}";                   Flags: ignoreversion deleteafterinstall; Components: ollama

; PowerShell helper scripts
Source: "scripts\post-install.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\start-backend.ps1";  DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\stop-backend.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\pull-models.ps1";    DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\check-health.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion

[Icons]
Name: "{group}\Start Backend";       Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\start-backend.ps1"""; WorkingDir: "{app}\backend"
Name: "{group}\Stop Backend";        Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\stop-backend.ps1"""
Name: "{group}\Pull LLM Models";     Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\pull-models.ps1"""
Name: "{group}\Health Check";        Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\check-health.ps1"""
Name: "{group}\Extension Folder";    Filename: "{app}\extension"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Install Ollama silently
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART"; StatusMsg: "Installing Ollama..."; Components: ollama; Flags: waituntilterminated

; Run post-install script (installs Python 3.13 via uv, creates venv, installs deps)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\post-install.ps1"" -AppDir ""{app}"""; StatusMsg: "Setting up Python environment..."; Flags: waituntilterminated runhidden; Components: backend

; Register backend as Windows Service via NSSM
Filename: "{app}\tools\nssm.exe"; Parameters: "install AIHelpdeskBackend powershell.exe ""-ExecutionPolicy Bypass -File '{app}\scripts\start-backend.ps1'"""; StatusMsg: "Registering backend service..."; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend AppDirectory ""{app}\backend"""; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend DisplayName ""AI Helpdesk Backend"""; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend Description ""FastAPI backend for AI Helpdesk Assistant"""; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend Start SERVICE_DELAYED_AUTO_START"; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend AppStdout ""{app}\logs\backend-stdout.log"""; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend AppStderr ""{app}\logs\backend-stderr.log"""; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend AppRotateFiles 1"; Components: service; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskBackend AppRotateBytes 5242880"; Components: service; Flags: waituntilterminated runhidden

; Start the service
Filename: "{app}\tools\nssm.exe"; Parameters: "start AIHelpdeskBackend"; StatusMsg: "Starting backend service..."; Components: service; Flags: waituntilterminated runhidden

; Pull LLM models (optional, shown to user — this is the longest step)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\pull-models.ps1"""; StatusMsg: "Downloading LLM models (this may take several minutes)..."; Components: models; Flags: waituntilterminated shellexec

; Post-install: open extension folder and Edge extensions page
Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""; Description: "Open extension folder (load in Edge manually)"; Flags: postinstall nowait skipifsilent
Filename: "{code:GetEdgePath}"; Parameters: "edge://extensions"; Description: "Open Edge Extensions page"; Flags: postinstall nowait skipifsilent unchecked; Check: EdgeExists

[UninstallRun]
; Stop and remove the Windows Service
Filename: "{app}\tools\nssm.exe"; Parameters: "stop AIHelpdeskBackend"; Flags: runhidden waituntilterminated
Filename: "{app}\tools\nssm.exe"; Parameters: "remove AIHelpdeskBackend confirm"; Flags: runhidden waituntilterminated

[Code]
function IsOllamaInstalled: Boolean;
var
  ResultCode: Integer;
begin
  // Check common install locations
  Result :=
    FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) or
    FileExists(ExpandConstant('{pf}\Ollama\ollama.exe')) or
    FileExists(ExpandConstant('{pf32}\Ollama\ollama.exe'));

  // Also check if ollama is on PATH (covers custom installs)
  if not Result then
  begin
    Result := Exec('cmd.exe', '/c where ollama >nul 2>nul', '', SW_HIDE,
                   ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  end;
end;

function GetEdgePath(Param: String): String;
var
  EdgePath: String;
begin
  // Check registry for Edge install path (works for all install types)
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe',
                         '', EdgePath) then
    Result := EdgePath
  else if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe',
                              '', EdgePath) then
    Result := EdgePath
  else
    // Fallback to common locations
    if FileExists(ExpandConstant('{pf32}\Microsoft\Edge\Application\msedge.exe')) then
      Result := ExpandConstant('{pf32}\Microsoft\Edge\Application\msedge.exe')
    else if FileExists(ExpandConstant('{pf}\Microsoft\Edge\Application\msedge.exe')) then
      Result := ExpandConstant('{pf}\Microsoft\Edge\Application\msedge.exe')
    else
      Result := 'msedge.exe';
end;

function EdgeExists: Boolean;
begin
  Result := GetEdgePath('') <> 'msedge.exe';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    // Auto-deselect Ollama component if already installed
    if IsOllamaInstalled then
    begin
      WizardForm.ComponentsList.Checked[2] := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    ForceDirectories(ExpandConstant('{app}\logs'));
  end;
end;
