# import-models.ps1 - Import bundled GGUF model files (offline install)
param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

# --- Logging setup -----------------------------------------------------------
. (Join-Path $PSScriptRoot "logging-utils.ps1")
$logFile      = Initialize-LogFile  -AppDir $AppDir -LogName "import-models"
$chainLogFile = Initialize-ChainLog -AppDir $AppDir
Write-Log "=== Importing GGUF Models ===" "INFO"
Write-Log "Log file: $logFile" "INFO"
Write-Log "AppDir: $AppDir" "INFO"
Write-ChainLog -ScriptName "import-models.ps1" -Message "STARTED"

# Trap unexpected terminating errors so they appear in the log and chain log
trap {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile      -Value "[$ts] [ERROR] Fatal: $_" -Encoding UTF8
    Add-Content -Path $chainLogFile -Value "[$ts] [CHAIN] [import-models.ps1] FAILED - $_" -Encoding UTF8
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}

$bundledModels = Join-Path $AppDir "deps\models"
$modelsDir = Join-Path $AppDir "models"

if (-not (Test-Path $bundledModels)) {
    Write-Log "No bundled models found at $bundledModels" "INFO"
    Write-Log "This is an online-only build - skipping offline model import." "INFO"
    Write-Log "Models will be downloaded during first run via 'Setup LLM Models'." "INFO"
    Write-ChainLog -ScriptName "import-models.ps1" -Message "SKIPPED - online-only build (no bundled models at $bundledModels)"
    exit 0
}

# Create target directory if it doesn't exist
if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
}

# Copy GGUF files from bundled deps to models directory
Write-Log "Copying GGUF model files..." "INFO"
$ggufFiles = Get-ChildItem -Path $bundledModels -Filter "*.gguf" -File
if ($ggufFiles.Count -eq 0) {
    Write-Log "WARNING: No .gguf files found in $bundledModels" "WARN"
    Write-Host "WARNING: No .gguf files found in bundled models directory." -ForegroundColor Yellow
    Write-ChainLog -ScriptName "import-models.ps1" -Message "SKIPPED - no .gguf files found in $bundledModels"
    exit 0
}

foreach ($f in $ggufFiles) {
    $destPath = Join-Path $modelsDir $f.Name
    $sizeMB = [math]::Round($f.Length / 1MB, 1)
    Write-Log "Copying $($f.Name) ($sizeMB MB)..." "INFO"
    Write-Host "Copying $($f.Name) ($sizeMB MB)..." -ForegroundColor Yellow
    try {
        Copy-Item -Path $f.FullName -Destination $destPath -Force
        Write-Log "Copied $($f.Name)" "INFO"
    } catch {
        Write-Log "ERROR copying $($f.Name): $_" "ERROR"
        throw
    }
}

Write-Log "Model import complete!" "INFO"
Write-Log "Imported $($ggufFiles.Count) model file(s)" "INFO"
Write-ChainLog -ScriptName "import-models.ps1" -Message "SUCCESS - imported $($ggufFiles.Count) GGUF model file(s)"
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
