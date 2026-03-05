# import-models.ps1 - Import bundled Ollama models (offline install)
param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

# --- Logging setup -----------------------------------------------------------
. (Join-Path $PSScriptRoot "logging-utils.ps1")
$logFile      = Initialize-LogFile  -AppDir $AppDir -LogName "import-models"
$chainLogFile = Initialize-ChainLog -AppDir $AppDir
Write-Log "=== Importing Ollama Models ===" "INFO"
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

$bundledModels = Join-Path $AppDir "deps\ollama-models"
$ollamaDir = Join-Path $env:USERPROFILE ".ollama\models"

if (-not (Test-Path $bundledModels)) {
    Write-Log "No bundled models found at $bundledModels" "INFO"
    Write-Log "This is an online-only build — skipping offline model import." "INFO"
    Write-Log "Models will be downloaded during first run via 'ollama pull'." "INFO"
    Write-ChainLog -ScriptName "import-models.ps1" -Message "SKIPPED - online-only build (no bundled models at $bundledModels)"
    exit 0
}

# Create target directory if it doesn't exist
if (-not (Test-Path $ollamaDir)) {
    New-Item -ItemType Directory -Path $ollamaDir -Force | Out-Null
}

# Copy blobs (model weights and configs)
$blobsSrc = Join-Path $bundledModels "blobs"
$blobsDst = Join-Path $ollamaDir "blobs"
if (Test-Path $blobsSrc) {
    Write-Log "Copying model blobs (~6.6 GB)... this may take a few minutes." "INFO"
    if (-not (Test-Path $blobsDst)) {
        New-Item -ItemType Directory -Path $blobsDst -Force | Out-Null
    }
    try {
        Copy-Item -Path (Join-Path $blobsSrc "*") -Destination $blobsDst -Recurse -Force
        Write-Log "Blobs copied." "INFO"
    } catch {
        Write-Log "ERROR copying blobs: $_" "ERROR"
        throw
    }
}

# Copy manifests (model registry metadata)
$manifestsSrc = Join-Path $bundledModels "manifests"
if (Test-Path $manifestsSrc) {
    Write-Log "Copying model manifests..." "INFO"
    try {
        Copy-Item -Path $manifestsSrc -Destination $ollamaDir -Recurse -Force
        Write-Log "Manifests copied." "INFO"
    } catch {
        Write-Log "ERROR copying manifests: $_" "ERROR"
        throw
    }
}

Write-Log "Model import complete!" "INFO"
Write-Log "Imported models: qwen3.5:9b, nomic-embed-text" "INFO"
Write-ChainLog -ScriptName "import-models.ps1" -Message "SUCCESS - imported qwen3.5:9b and nomic-embed-text"
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
