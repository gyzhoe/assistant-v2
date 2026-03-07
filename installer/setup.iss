; setup.iss — AI Helpdesk Assistant Inno Setup Script
; Builds a per-user installer for Windows 10/11 x64.
; Compile with: iscc /DMyAppVersion=2.0.0 setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif

; InstallerType: "online" (no models) or "offline" (bundled models).
; Override at compile time: iscc /DInstallerType=offline setup.iss
#ifndef InstallerType
  #define InstallerType "online"
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
#if InstallerType == "offline"
OutputBaseFilename=AIHelpdeskAssistant-Full-Setup-{#MyAppVersion}
#else
OutputBaseFilename=AIHelpdeskAssistant-Online-Setup-{#MyAppVersion}
#endif
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll
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
#if InstallerType == "offline"
Name: "models";    Description: "LLM models (bundled, ~6 GB)";                    Types: full custom
#else
Name: "models";    Description: "Download LLM models (~6 GB, requires internet)";   Types: full custom
#endif

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

; llama-server GPU-specific builds — auto-detected at install time.
; Only one variant is installed based on the detected GPU.
; NVIDIA CUDA 12.4 (best performance for NVIDIA GPUs, Pascal and newer)
Source: "deps\llama-cuda\*";         DestDir: "{app}\tools";             Flags: ignoreversion recursesubdirs createallsubdirs; Components: llama; Check: IsNvidiaGPU
; Vulkan (universal GPU support — AMD, Intel Arc, NVIDIA fallback)
Source: "deps\llama-vulkan\*";       DestDir: "{app}\tools";             Flags: ignoreversion recursesubdirs createallsubdirs; Components: llama; Check: IsVulkanGPU
; CPU only (no GPU acceleration — fallback for systems without a supported GPU)
Source: "deps\llama-cpu\*";          DestDir: "{app}\tools";             Flags: ignoreversion recursesubdirs createallsubdirs; Components: llama; Check: IsCPUOnly

; Bundled Python 3.13 standalone (offline install)
Source: "deps\python\*";             DestDir: "{app}\deps\python";       Flags: ignoreversion recursesubdirs createallsubdirs; Components: backend

; Pre-downloaded Python wheels (offline install)
Source: "deps\wheels\*";             DestDir: "{app}\deps\wheels";       Flags: ignoreversion; Components: backend

; Requirements file for offline pip install
Source: "..\backend\requirements.txt"; DestDir: "{app}\backend";         Flags: ignoreversion; Components: backend

; Bundled GGUF model files (offline install only — ~6 GB)
; Requires both: InstallerType=offline AND model files present in deps/models/.
; Online builds always skip this, even if models happen to exist locally.
#if InstallerType == "offline"
  #ifexist "deps\models\nomic-embed-text-v1.5.f16.gguf"
  Source: "deps\models\*";             DestDir: "{app}\models";            Flags: ignoreversion; Components: models
  #endif
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
; Step 1: Kill ALL app processes FIRST — must happen before cleanup dialog
; so files aren't locked when the user tries to delete them.
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Get-Process -Name 'llama-server','ollama','ollama_llama_server' -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "KillLlama"
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""foreach ($port in @(8765, 11435, 11436)) {{ try {{ Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }} }} catch {{}} }}"""; Flags: runhidden waituntilterminated; RunOnceId: "KillAppPorts"
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith('{app}', [System.StringComparison]::OrdinalIgnoreCase) }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }}; Start-Sleep -Seconds 2"""; Flags: runhidden waituntilterminated; RunOnceId: "KillAppProcesses"

; Step 2: Cleanup dialog — now safe to delete files (processes are dead)
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\uninstall-cleanup.ps1"" -AppDir ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "UninstallCleanup"

; Step 3: Remove the install directory if it's empty or nearly empty after Inno cleanup
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Start-Sleep -Seconds 1; $d = '{app}'; if (Test-Path $d) {{ Remove-Item -Path $d -Recurse -Force -EA SilentlyContinue }}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveInstallDir"

[Code]
var
  DetectedGPUType: String;   // 'nvidia', 'amd', 'intel', 'cpu'
  DetectedGPUName: String;   // e.g. 'NVIDIA GeForce GTX 1070 Ti'
  ExistingVersion: String;   // e.g. '1.14.1' or '' if fresh install

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

// Detect GPU via WMI (Win32_VideoController).
// Prioritises discrete GPUs: NVIDIA > AMD > Intel Arc > CPU fallback.
procedure DetectGPU;
var
  ResultCode: Integer;
  TmpFile: String;
  Output: AnsiString;
  Lines: TArrayOfString;
begin
  DetectedGPUType := 'cpu';
  DetectedGPUName := 'No supported GPU detected';
  TmpFile := ExpandConstant('{tmp}\gpu_detect.txt');

  // PowerShell one-liner: query all GPUs, prioritise discrete, output "type|name"
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -NoProfile -Command "' +
    '$gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name; ' +
    '$type = ''cpu''; $name = ''No supported GPU detected''; ' +
    'foreach ($g in $gpus) { ' +
    '  if ($g -match ''NVIDIA'') { $type = ''nvidia''; $name = $g; break } ' +
    '  elseif ($g -match ''AMD|Radeon'') { $type = ''amd''; $name = $g; break } ' +
    '  elseif ($g -match ''Intel.*Arc'') { $type = ''intel''; $name = $g; break } ' +
    '}; ' +
    '\"$type|$name\" | Out-File -FilePath ''' + TmpFile + ''' -Encoding ASCII -NoNewline"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if LoadStringFromFile(TmpFile, Output) then
  begin
    // Parse "type|name" format
    if LoadStringsFromFile(TmpFile, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Output := Lines[0];
    end;

    if Pos('nvidia|', String(Output)) = 1 then
    begin
      DetectedGPUType := 'nvidia';
      DetectedGPUName := Copy(String(Output), 8, Length(String(Output)) - 7);
    end
    else if Pos('amd|', String(Output)) = 1 then
    begin
      DetectedGPUType := 'amd';
      DetectedGPUName := Copy(String(Output), 5, Length(String(Output)) - 4);
    end
    else if Pos('intel|', String(Output)) = 1 then
    begin
      DetectedGPUType := 'intel';
      DetectedGPUName := Copy(String(Output), 7, Length(String(Output)) - 6);
    end
    else
    begin
      DetectedGPUType := 'cpu';
      DetectedGPUName := 'No supported GPU detected';
    end;
  end;

  DeleteFile(TmpFile);

  // Map GPU type to backend label for logging
  case DetectedGPUType of
    'nvidia': Log('GPU detected: NVIDIA — will install CUDA 12.4 build (' + DetectedGPUName + ')');
    'amd':    Log('GPU detected: AMD — will install Vulkan build (' + DetectedGPUName + ')');
    'intel':  Log('GPU detected: Intel Arc — will install Vulkan build (' + DetectedGPUName + ')');
  else
    Log('GPU detection: no supported GPU found — will install CPU-only build');
  end;
end;

// Check functions used by [Files] entries to conditionally install GPU-specific builds
function IsNvidiaGPU: Boolean;
begin
  Result := DetectedGPUType = 'nvidia';
end;

function IsVulkanGPU: Boolean;
begin
  Result := (DetectedGPUType = 'amd') or (DetectedGPUType = 'intel');
end;

function IsCPUOnly: Boolean;
begin
  Result := DetectedGPUType = 'cpu';
end;

function GPUBackendName: String;
begin
  case DetectedGPUType of
    'nvidia': Result := 'cuda';
    'amd':    Result := 'vulkan';
    'intel':  Result := 'vulkan';
  else
    Result := 'cpu';
  end;
end;

// Detect existing installation by reading version.json from the default install dir.
procedure DetectExistingInstall;
var
  VersionFile: String;
  Content: AnsiString;
  VerStart, VerEnd: Integer;
  VerStr: String;
begin
  ExistingVersion := '';
  VersionFile := ExpandConstant('{localappdata}\AIHelpdeskAssistant\version.json');
  if FileExists(VersionFile) then
  begin
    if LoadStringFromFile(VersionFile, Content) then
    begin
      // Parse "version": "X.Y.Z" from JSON
      VerStart := Pos('"version"', String(Content));
      if VerStart > 0 then
      begin
        VerStart := Pos(':', String(Content));
        // Find the opening quote after the colon
        while (VerStart <= Length(String(Content))) and (String(Content)[VerStart] <> '"') do
          VerStart := VerStart + 1;
        VerStart := VerStart + 1; // skip the quote
        VerEnd := VerStart;
        while (VerEnd <= Length(String(Content))) and (String(Content)[VerEnd] <> '"') do
          VerEnd := VerEnd + 1;
        VerStr := Copy(String(Content), VerStart, VerEnd - VerStart);
        if Length(VerStr) > 0 then
        begin
          ExistingVersion := VerStr;
          Log('Existing installation detected: v' + ExistingVersion);
        end;
      end;
    end;
  end;
end;

function InitializeSetup: Boolean;
begin
  DetectGPU;
  DetectExistingInstall;
  Result := True;
end;

procedure InitializeWizard;
var
  GPULabel: String;
  WelcomeLabel: TNewStaticText;
begin
  // Update the llama component description to show the detected GPU
  case DetectedGPUType of
    'nvidia': GPULabel := 'llama.cpp LLM Runtime — NVIDIA CUDA 12.4 (' + DetectedGPUName + ')';
    'amd':    GPULabel := 'llama.cpp LLM Runtime — Vulkan (' + DetectedGPUName + ')';
    'intel':  GPULabel := 'llama.cpp LLM Runtime — Vulkan (' + DetectedGPUName + ')';
  else
    GPULabel := 'llama.cpp LLM Runtime — CPU only (no GPU detected)';
  end;

  // Update component description in the wizard
  WizardForm.ComponentsList.ItemCaption[2] := GPULabel;

  // Show upgrade notice on the welcome page if an existing install is detected
  if ExistingVersion <> '' then
  begin
    WelcomeLabel := TNewStaticText.Create(WizardForm);
    WelcomeLabel.Parent := WizardForm.WelcomePage;
    WelcomeLabel.Left := WizardForm.WelcomeLabel2.Left;
    WelcomeLabel.Top := WizardForm.WelcomeLabel2.Top + WizardForm.WelcomeLabel2.Height + 16;
    WelcomeLabel.Width := WizardForm.WelcomeLabel2.Width;
    WelcomeLabel.AutoSize := False;
    WelcomeLabel.WordWrap := True;
    WelcomeLabel.Height := 40;
    WelcomeLabel.Caption := 'Existing installation detected: v' + ExistingVersion +
      ' will be upgraded to v{#MyAppVersion}. Your data (knowledge base, models, settings) will be preserved.';
    WelcomeLabel.Font.Style := [fsBold];
  end;
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

  // Kill processes on all ports used by the app (backend + llama-server instances)
  // This catches processes regardless of where they were started from
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'foreach ($port in @(8765, 11435, 11436)) { ' +
    '  try { ' +
    '    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue; ' +
    '    foreach ($c in $conns) { ' +
    '      $p = Get-Process -Id $c.OwningProcess -EA SilentlyContinue; ' +
    '      if ($p) { Stop-Process -Id $p.Id -Force -EA SilentlyContinue } ' +
    '    } ' +
    '  } catch {} ' +
    '}; ' +
    'Start-Sleep -Seconds 2"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // Kill any Python/pythonw processes running from the install directory
  // (catches venv processes, model download scripts, etc.)
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
  GPUName: String;
begin
  VersionPath := ExpandConstant('{app}\version.json');
  // Escape backslashes and quotes in GPU name for JSON
  GPUName := DetectedGPUName;
  StringChangeEx(GPUName, '\', '\\', True);
  StringChangeEx(GPUName, '"', '\"', True);
  JsonContent :=
    '{' + #13#10 +
    '  "version": "{#MyAppVersion}",' + #13#10 +
    '  "deps_version": "1.0.0",' + #13#10 +
    '  "llama_version": "b8215",' + #13#10 +
    '  "llama_backend": "' + GPUBackendName + '",' + #13#10 +
    '  "gpu_detected": "' + GPUName + '",' + #13#10 +
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
      Log('llama-server.exe verified at ' + ExpandConstant('{app}\tools\llama-server.exe') + ' (backend: ' + GPUBackendName + ')')
    else
      Log('WARNING: llama-server.exe not found — LLM inference will be unavailable');
  end;
end;
