; setup.iss — AI Helpdesk Assistant Inno Setup Script
; Builds a per-user installer for Windows 10/11 x64.
; Compile with: iscc /DMyAppVersion=2.0.0 setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif

#define MyAppName     "AI Helpdesk Assistant"
#define MyAppPublisher "AI Helpdesk"
#define MyAppURL      "https://github.com/gyzhoe/assistant-v2"

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
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
DisableDirPage=no
AppendDefaultDirName=no
UsePreviousAppDir=yes
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
Name: "llama";     Description: "llama.cpp LLM Runtime (llama-server)";          Types: full custom
Name: "models";    Description: "Download LLM models (~6 GB, requires internet)";   Types: full custom

[InstallDelete]
; Clean up stale files from previous installs before copying new ones.
; Preserves: chroma_data (user KB), logs, .env (user config).
Type: filesandordirs; Name: "{app}\backend\app"
Type: filesandordirs; Name: "{app}\backend\ingestion"
Type: filesandordirs; Name: "{app}\backend\static"
Type: filesandordirs; Name: "{app}\backend\.venv"
Type: files;          Name: "{app}\backend\pyproject.toml"
Type: files;          Name: "{app}\backend\requirements.txt"
Type: filesandordirs; Name: "{app}\extension"
Type: filesandordirs; Name: "{app}\deps\python"
Type: filesandordirs; Name: "{app}\deps\wheels"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\tools"

[Dirs]
; uninsneveruninstall: log files are created by post-install scripts (not tracked by Inno
; Setup), so the directory must survive uninstall for diagnostic purposes.  User-initiated
; removal is still available via the uninstall-cleanup.ps1 dialog.
Name: "{app}\logs";              Flags: uninsneveruninstall
Name: "{app}\backend\chroma_data"
Name: "{app}\models";             Flags: uninsneveruninstall

[Files]
; Backend source
Source: "..\backend\app\*";           DestDir: "{app}\backend\app";       Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend
Source: "..\backend\ingestion\*";     DestDir: "{app}\backend\ingestion"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend
Source: "..\backend\pyproject.toml";  DestDir: "{app}\backend";           Flags: ignoreversion; Components: backend
Source: "..\backend\.env.example";   DestDir: "{app}\backend";           Flags: ignoreversion; Components: backend

; Native messaging host scripts (backend manages its own lifecycle via extension messages)
Source: "..\backend\native_host.py";  DestDir: "{app}\backend";           Flags: ignoreversion; Components: backend
Source: "..\backend\native_host.cmd"; DestDir: "{app}\backend";           Flags: ignoreversion; Components: backend

; Extension dist (pre-built by CI)
Source: "..\extension\dist\*";        DestDir: "{app}\extension";         Flags: ignoreversion recursesubdirs createallsubdirs; Components: extension

; Management SPA static files (served by FastAPI at /manage)
Source: "..\backend\static\manage\*"; DestDir: "{app}\backend\static\manage"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend

; uv standalone binary (downloaded by CI)
Source: "deps\uv.exe";               DestDir: "{app}\tools";             Flags: ignoreversion; Components: backend

; Rust assistant-tools binary (replaces PowerShell scripts)
Source: "deps\assistant-tools.exe";  DestDir: "{app}\tools";             Flags: ignoreversion; Components: backend

; llama-server binary + CUDA DLLs
; Everything under {app}\tools\ for AppLocker compatibility
Source: "deps\llama-server\*";        DestDir: "{app}\tools";             Flags: ignoreversion recursesubdirs createallsubdirs; Components: llama

; Bundled Python 3.13 standalone (offline install)
Source: "deps\python\*";             DestDir: "{app}\deps\python";       Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend

; Pre-downloaded Python wheels (offline install)
Source: "deps\wheels\*";             DestDir: "{app}\deps\wheels";       Flags: ignoreversion; Components: backend

; Requirements file for offline pip install
Source: "..\backend\requirements.txt"; DestDir: "{app}\backend";         Flags: ignoreversion; Components: backend

; Bundled GGUF model files (offline install — ~15 GB)
; Only included when built locally with models present; CI builds skip this.
#ifexist "deps\models\nomic-embed-text-v1.5.f16.gguf"
Source: "deps\models\*";             DestDir: "{app}\models";            Flags: ignoreversion; Components: models
#endif

; PowerShell helper scripts
Source: "scripts\logging-utils.ps1";     DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\post-install.ps1";      DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\start-backend.ps1";     DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\pull-models.ps1";       DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\import-models.ps1";     DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\check-health.ps1";      DestDir: "{app}\scripts";          Flags: ignoreversion
Source: "scripts\uninstall-cleanup.ps1"; DestDir: "{app}\scripts";          Flags: ignoreversion

; GUI model-pull script (launched via pythonw.exe — no console window)
Source: "scripts\pull-models-gui.py";    DestDir: "{app}\scripts";          Flags: ignoreversion

[Icons]
; Interactive tools — uses compiled Rust binary
Name: "{group}\Health Check";        Filename: "{app}\tools\assistant-tools.exe"; Parameters: "health-check --app-dir ""{app}"""
Name: "{group}\Check for Updates";   Filename: "{app}\tools\assistant-tools.exe"; Parameters: "update --app-dir ""{app}"""
Name: "{group}\Extension Folder";    Filename: "{app}\extension"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\com.assistant.backend_manager"; \
  ValueType: string; ValueData: "{app}\backend\com.assistant.backend_manager.json"; \
  Flags: uninsdeletekey

[Run]
; Run post-install script (installs Python 3.13 via uv, creates venv, installs deps)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\post-install.ps1"" -AppDir ""{app}"""; StatusMsg: "Setting up Python environment..."; Flags: waituntilterminated runhidden; Components: backend

; Import bundled LLM models (copies pre-downloaded model files)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NonInteractive -File ""{app}\scripts\import-models.ps1"" -AppDir ""{app}"" -NonInteractive"; StatusMsg: "Importing LLM models..."; Components: models; Flags: waituntilterminated runhidden

; Pull LLM models — tkinter GUI (pythonw.exe hides console, logs go to file)
Filename: "{app}\backend\.venv\Scripts\pythonw.exe"; Parameters: """{app}\scripts\pull-models-gui.py"" --app-dir ""{app}"""; StatusMsg: "Downloading LLM models..."; Flags: waituntilterminated; Components: models

; Post-install: open extension folder and Edge extensions page
Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""; Description: "Open extension folder (load in Edge manually)"; Flags: postinstall nowait skipifsilent
Filename: "{code:GetEdgePath}"; Parameters: "edge://extensions"; Description: "Open Edge Extensions page"; Flags: postinstall nowait skipifsilent unchecked; Check: EdgeExists

[UninstallRun]
; Kill llama-server and legacy Ollama processes before cleanup (locks DLLs if left running)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Get-Process -Name 'llama-server','ollama','ollama_llama_server' -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue; Start-Sleep -Seconds 2"""; Flags: runhidden waituntilterminated; RunOnceId: "KillLlamaOllama"
; Cleanup dialog — offer model removal before anything is torn down
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\uninstall-cleanup.ps1"" -AppDir ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "UninstallCleanup"
; Kill backend on port 8765
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""try {{ $c = Get-NetTCPConnection -LocalPort 8765 -State Listen -EA SilentlyContinue | Select -First 1; if ($c) {{ Stop-Process -Id $c.OwningProcess -Force -EA SilentlyContinue }} }} catch {{}}"""; Flags: runhidden waituntilterminated; RunOnceId: "KillBackendPort"
; Kill Python processes from install directory
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith('{app}', [System.StringComparison]::OrdinalIgnoreCase) }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }}"""; Flags: runhidden waituntilterminated; RunOnceId: "KillAppPython"

[Code]
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

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  NssmPath: String;
  AppDir: String;
begin
  Result := '';
  NeedsRestart := False;
  AppDir := ExpandConstant('{app}');
  NssmPath := AppDir + '\tools\nssm.exe';

  // Migration: stop and remove NSSM-managed services from previous installs
  if FileExists(NssmPath) then
  begin
    Exec(NssmPath, 'stop AIHelpdeskBackend', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Exec(NssmPath, 'remove AIHelpdeskBackend confirm', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Exec(NssmPath, 'stop AIHelpdeskOllama', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Exec(NssmPath, 'remove AIHelpdeskOllama confirm', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
  end;

  // Kill llama-server and legacy Ollama processes (may run from different locations)
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'Get-Process -Name ''llama-server'',''ollama'',''ollama_llama_server'' -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue; ' +
    'Start-Sleep -Seconds 2"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // Kill backend process listening on port 8765 (covers manual starts)
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'try { $c = Get-NetTCPConnection -LocalPort 8765 -State Listen -EA SilentlyContinue | Select -First 1; ' +
    'if ($c) { Stop-Process -Id $c.OwningProcess -Force -EA SilentlyContinue } } catch {}"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // Kill any Python processes running from the install directory
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'Get-CimInstance Win32_Process | ' +
    'Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith(''' + AppDir + ''', [System.StringComparison]::OrdinalIgnoreCase) } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }; ' +
    'Start-Sleep -Seconds 1"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure GenerateNativeMessagingManifest;
var
  ManifestPath: String;
  HostPath: String;
  JsonContent: String;
begin
  ManifestPath := ExpandConstant('{app}\backend\com.assistant.backend_manager.json');
  HostPath := ExpandConstant('{app}\backend\native_host.cmd');
  // Double backslashes for JSON path encoding
  StringChangeEx(HostPath, '\', '\\', True);
  JsonContent :=
    '{' + #13#10 +
    '  "name": "com.assistant.backend_manager",' + #13#10 +
    '  "description": "AI Helpdesk Assistant - Service Manager",' + #13#10 +
    '  "path": "' + HostPath + '",' + #13#10 +
    '  "type": "stdio",' + #13#10 +
    '  "allowed_origins": ["chrome-extension://inapklomefcicbehlgihcidbmboiimgc/"]' + #13#10 +
    '}';
  SaveStringToFile(ManifestPath, JsonContent, False);
end;

procedure GenerateVersionJson;
var
  VersionPath: String;
  JsonContent: String;
begin
  VersionPath := ExpandConstant('{app}\version.json');
  JsonContent :=
    '{' + #13#10 +
    '  "version": "{#MyAppVersion}",' + #13#10 +
    '  "deps_version": "1.0.0",' + #13#10 +
    '  "llama_version": "b8215",' + #13#10 +
    '  "python_version": "3.13.2"' + #13#10 +
    '}';
  SaveStringToFile(VersionPath, JsonContent, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    ForceDirectories(ExpandConstant('{app}\logs'));
    GenerateNativeMessagingManifest;
    GenerateVersionJson;

    // Verify llama-server binary installed correctly (diagnostic log)
    if FileExists(ExpandConstant('{app}\tools\llama-server.exe')) then
      Log('llama-server.exe verified at ' + ExpandConstant('{app}\tools\llama-server.exe'))
    else
      Log('WARNING: llama-server.exe not found — LLM inference will be unavailable');
  end;
end;
