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
Name: "models";    Description: "LLM models — llama3.2:3b + nomic-embed-text (~2.2 GB)"; Types: full custom
Name: "service";   Description: "Register backend as Windows Service (auto-start)"; Types: full custom
Name: "ollamasvc"; Description: "Run Ollama as hidden service (no tray icon)";     Types: full custom

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
Source: "nssm\nssm.exe";             DestDir: "{app}\tools";             Flags: ignoreversion; Components: service ollamasvc

; Ollama installer (downloaded by CI)
Source: "deps\OllamaSetup.exe";      DestDir: "{tmp}";                   Flags: ignoreversion deleteafterinstall; Components: ollama

; Bundled Python 3.13 standalone (offline install)
Source: "deps\python\*";             DestDir: "{app}\deps\python";       Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend

; Pre-downloaded Python wheels (offline install)
Source: "deps\wheels\*";             DestDir: "{app}\deps\wheels";       Flags: ignoreversion; Components: backend

; Requirements file for offline pip install
Source: "..\backend\requirements.txt"; DestDir: "{app}\backend";         Flags: ignoreversion; Components: backend

; Bundled Ollama models (offline install — ~2.2 GB)
Source: "deps\ollama-models\*";      DestDir: "{app}\deps\ollama-models"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: models

; PowerShell helper scripts
Source: "scripts\post-install.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\start-backend.ps1";  DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\stop-backend.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\pull-models.ps1";    DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\import-models.ps1";  DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\check-health.ps1";   DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\tray-monitor.ps1";  DestDir: "{app}\scripts";          Flags: ignoreversion

[Icons]
; Start/Stop use NSSM directly — instant, no terminal window
Name: "{group}\Start Backend";       Filename: "{app}\tools\nssm.exe"; Parameters: "start AIHelpdeskBackend"; Components: service
Name: "{group}\Stop Backend";        Filename: "{app}\tools\nssm.exe"; Parameters: "stop AIHelpdeskBackend";  Components: service
; Fallback shortcuts when service component not selected
Name: "{group}\Start Backend";       Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\start-backend.ps1"""; WorkingDir: "{app}\backend"; Components: not service
Name: "{group}\Stop Backend";        Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NonInteractive -File ""{app}\scripts\stop-backend.ps1"""; Components: not service
; Interactive diagnostic tools — keep visible PowerShell
Name: "{group}\Setup LLM Models";    Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\pull-models.ps1"""
Name: "{group}\Health Check";        Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\check-health.ps1"""
Name: "{group}\Extension Folder";    Filename: "{app}\extension"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Auto-start tray monitor at Windows login
Name: "{userstartup}\AI Helpdesk Monitor"; Filename: "powershell.exe"; Parameters: "-WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\scripts\tray-monitor.ps1"""; WorkingDir: "{app}"

[Run]
; Install Ollama silently
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART"; StatusMsg: "Installing Ollama..."; Components: ollama; Flags: waituntilterminated

; Kill Ollama desktop app (installer starts it automatically with tray icon)
Filename: "taskkill.exe"; Parameters: "/F /IM ""Ollama.exe"""; Components: ollamasvc; Flags: waituntilterminated runhidden; StatusMsg: "Stopping Ollama desktop app..."

; Remove Ollama auto-start entries (Startup folder shortcut + registry key)
Filename: "cmd.exe"; Parameters: "/c del /q ""{userstartup}\Ollama.lnk"" 2>nul"; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Ollama /f"; Components: ollamasvc; Flags: waituntilterminated runhidden

; Register Ollama as hidden NSSM service (ollama serve on port 11434)
Filename: "{app}\tools\nssm.exe"; Parameters: "install AIHelpdeskOllama ""{code:GetOllamaExePath}"" serve"; StatusMsg: "Registering Ollama service..."; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama DisplayName ""AI Helpdesk Ollama"""; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama Description ""Ollama LLM inference server for AI Helpdesk"""; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama Start SERVICE_DELAYED_AUTO_START"; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama AppStdout ""{app}\logs\ollama-stdout.log"""; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama AppStderr ""{app}\logs\ollama-stderr.log"""; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama AppRotateFiles 1"; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "set AIHelpdeskOllama AppRotateBytes 5242880"; Components: ollamasvc; Flags: waituntilterminated runhidden
Filename: "{app}\tools\nssm.exe"; Parameters: "start AIHelpdeskOllama"; StatusMsg: "Starting Ollama service..."; Components: ollamasvc; Flags: waituntilterminated runhidden

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

; Import bundled LLM models (copies pre-downloaded model files)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NonInteractive -File ""{app}\scripts\import-models.ps1"" -AppDir ""{app}"" -NonInteractive"; StatusMsg: "Importing LLM models..."; Components: models; Flags: waituntilterminated runhidden

; Launch tray monitor after install
Filename: "powershell.exe"; Parameters: "-WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\scripts\tray-monitor.ps1"""; Description: "Launch system tray monitor"; Flags: postinstall nowait skipifsilent

; Post-install: open extension folder and Edge extensions page
Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""; Description: "Open extension folder (load in Edge manually)"; Flags: postinstall nowait skipifsilent
Filename: "{code:GetEdgePath}"; Parameters: "edge://extensions"; Description: "Open Edge Extensions page"; Flags: postinstall nowait skipifsilent unchecked; Check: EdgeExists

[UninstallDelete]
; Remove startup shortcut
Type: files; Name: "{userstartup}\AI Helpdesk Monitor.lnk"

[UninstallRun]
; Kill tray monitor process before uninstall (match by command line)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*tray-monitor*' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"""; Flags: runhidden waituntilterminated
; Stop and remove backend service
Filename: "{app}\tools\nssm.exe"; Parameters: "stop AIHelpdeskBackend"; Flags: runhidden waituntilterminated
Filename: "{app}\tools\nssm.exe"; Parameters: "remove AIHelpdeskBackend confirm"; Flags: runhidden waituntilterminated
; Stop and remove Ollama service
Filename: "{app}\tools\nssm.exe"; Parameters: "stop AIHelpdeskOllama"; Flags: runhidden waituntilterminated
Filename: "{app}\tools\nssm.exe"; Parameters: "remove AIHelpdeskOllama confirm"; Flags: runhidden waituntilterminated

[Code]
function GetOllamaExePath(Param: String): String;
begin
  // Check common Ollama install locations
  if FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) then
    Result := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')
  else if FileExists(ExpandConstant('{pf}\Ollama\ollama.exe')) then
    Result := ExpandConstant('{pf}\Ollama\ollama.exe')
  else if FileExists(ExpandConstant('{pf32}\Ollama\ollama.exe')) then
    Result := ExpandConstant('{pf32}\Ollama\ollama.exe')
  else
    // Fallback — assume it's on PATH
    Result := 'ollama.exe';
end;

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
