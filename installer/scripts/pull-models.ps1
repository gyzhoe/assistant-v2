# pull-models.ps1 - Download or import required GGUF model files
param(
    [switch]$NonInteractive,
    [switch]$SkipModelPull
)
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot

# -- Logging setup -----------------------------------------------------------
. (Join-Path $PSScriptRoot "logging-utils.ps1")
$logFile      = Initialize-LogFile  -AppDir $AppDir -LogName "pull-models"
$chainLogFile = Initialize-ChainLog -AppDir $AppDir
Write-Log "=== AI Helpdesk Assistant - Pull Models ===" "INFO"
Write-Log "AppDir: $AppDir" "INFO"
Write-ChainLog -ScriptName "pull-models.ps1" -Message "STARTED"

# Trap unexpected terminating errors so they appear in the log and chain log
trap {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile      -Value "[$timestamp] [ERROR] Fatal: $_" -Encoding UTF8
    Add-Content -Path $chainLogFile -Value "[$timestamp] [CHAIN] [pull-models.ps1] FAILED - $_" -Encoding UTF8
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}

# --- Graceful skip for CI / offline environments --------------------------------
$skipEnv = ($env:SKIP_MODEL_PULL -ne $null -and $env:SKIP_MODEL_PULL.Trim() -ne "")
if ($SkipModelPull -or $skipEnv) {
    $skipReason = if ($SkipModelPull) { "-SkipModelPull flag" } else { "SKIP_MODEL_PULL=$($env:SKIP_MODEL_PULL)" }
    Write-Log "Model pull skipped ($skipReason). Run 'Setup LLM Models' from the Start Menu when ready." "INFO"
    Write-Host "Model pull skipped ($skipReason)." -ForegroundColor Yellow
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "SKIPPED - model pull bypassed ($skipReason)"
    exit 0
}
# ---------------------------------------------------------------------------------

Write-Host "=== Setting Up LLM Models ===" -ForegroundColor Cyan
$modelsDir = Join-Path $AppDir "models"
$bundledModels = Join-Path $AppDir "deps\models"

# Check for bundled offline models first
if (Test-Path $bundledModels) {
    Write-Log "Found bundled models - importing offline..." "INFO"
    Write-Host "Found bundled models - importing offline..." -ForegroundColor Yellow
    & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "import-models.ps1") -AppDir $AppDir -NonInteractive:$NonInteractive
    $importExitCode = $LASTEXITCODE
    Write-Log "import-models.ps1 exited with code $importExitCode" "INFO"
    if ($importExitCode -ne 0) {
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - import-models.ps1 exited $importExitCode"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit $importExitCode
    }

    # Verify imported models exist
    Write-Log "Verifying imported models..." "INFO"
    Write-Host "Verifying imported models..." -ForegroundColor Yellow
    $verifyMissing = @()
    foreach ($m in @("nomic-embed-text-v1.5.f16.gguf", "Qwen3.5-9B-Q4_K_M.gguf", "Qwen3-14B-Q4_K_M.gguf")) {
        if (-not (Test-Path (Join-Path $modelsDir $m))) { $verifyMissing += $m }
    }

    if ($verifyMissing.Count -gt 0) {
        Write-Log "ERROR: Post-import verification failed - missing models: $($verifyMissing -join ', ')" "ERROR"
        Write-Host "ERROR: Post-import verification failed - missing models: $($verifyMissing -join ', ')" -ForegroundColor Red
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - post-import verification: missing models: $($verifyMissing -join ', ')"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit 1
    }

    Write-Log "Post-import verification passed - all models present." "INFO"
    Write-Host "Offline model import and verification complete!" -ForegroundColor Green
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "SUCCESS - offline import verified"
    if (-not $NonInteractive) { Read-Host "Press Enter to close" }
    exit 0
}

# Online fallback: download GGUF files from HuggingFace
Write-Log "No bundled models found - downloading from internet..." "INFO"
Write-Host "No bundled models found - downloading from internet..." -ForegroundColor Yellow

# Ensure models directory exists
if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
}

$models = @(
    @{ name = "nomic-embed-text-v1.5.f16.gguf"; url = "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.f16.gguf"; desc = "~262 MB" }
    @{ name = "Qwen3.5-9B-Q4_K_M.gguf"; url = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"; desc = "~5.5 GB" }
    @{ name = "Qwen3-14B-Q4_K_M.gguf"; url = "https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf"; desc = "~9 GB (optional, better language control)" }
)
$maxPullRetries = 4
$pullRetryDelay = 5

foreach ($m in $models) {
    $modelName = $m.name
    $modelPath = Join-Path $modelsDir $modelName
    $succeeded = $false
    $lastError = ""

    # Skip if already downloaded
    if (Test-Path $modelPath) {
        $size = [math]::Round((Get-Item $modelPath).Length / 1MB, 1)
        Write-Log "$modelName already exists ($size MB) - skipping download" "INFO"
        Write-Host "$modelName already exists ($size MB) - skipping" -ForegroundColor Green
        continue
    }

    for ($attempt = 0; $attempt -le $maxPullRetries; $attempt++) {
        if ($attempt -gt 0) {
            Write-Log "  Download attempt $attempt of $($maxPullRetries + 1) failed - sleeping ${pullRetryDelay}s before attempt $($attempt + 1)..." "WARN"
            Write-Host "  Download failed - retrying in ${pullRetryDelay}s (attempt $($attempt + 1) of $($maxPullRetries + 1))..." -ForegroundColor Yellow
            Start-Sleep -Seconds $pullRetryDelay
        }
        Write-Log "Download attempt $($attempt + 1) of $($maxPullRetries + 1) started for $modelName ($($m.desc))" "INFO"
        Write-Host "Downloading $modelName ($($m.desc))... [attempt $($attempt + 1)/$($maxPullRetries + 1)]" -ForegroundColor Yellow
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $m.url -OutFile $modelPath -UseBasicParsing
            $ProgressPreference = 'Continue'
            $size = [math]::Round((Get-Item $modelPath).Length / 1MB, 1)
            Write-Log "Download attempt $($attempt + 1) succeeded for $modelName ($size MB)" "INFO"
            Write-Host "  Downloaded $modelName ($size MB)" -ForegroundColor Green
            $succeeded = $true
            break
        } catch {
            $lastError = $_.Exception.Message
            Write-Log "Download attempt $($attempt + 1) for $modelName failed: $lastError" "WARN"
            # Remove partial download
            if (Test-Path $modelPath) { Remove-Item $modelPath -Force -ErrorAction SilentlyContinue }
        }
    }
    if (-not $succeeded) {
        Write-Log "ERROR: Failed to download $modelName after $($maxPullRetries + 1) attempts." "ERROR"
        Write-Host "ERROR: Failed to download $modelName after $($maxPullRetries + 1) attempts." -ForegroundColor Red
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - $modelName download exhausted $($maxPullRetries + 1) attempts (last error: $lastError)"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit 1
    }
}

# Verify all models are present
Write-Log "Verifying downloaded models..." "INFO"
Write-Host "Verifying downloaded models..." -ForegroundColor Yellow
$missing = @()
foreach ($m in $models) {
    $modelPath = Join-Path $modelsDir $m.name
    if (-not (Test-Path $modelPath) -or (Get-Item $modelPath).Length -eq 0) {
        $missing += $m.name
    }
}
if ($missing.Count -gt 0) {
    Write-Log "ERROR: Verification failed - missing models: $($missing -join ', ')" "ERROR"
    Write-Host "ERROR: Verification failed - missing models: $($missing -join ', ')" -ForegroundColor Red
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - verification: missing models: $($missing -join ', ')"
    if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
    exit 1
}

Write-Log "Model download complete! All models verified." "INFO"
Write-Host "Model download complete! All models verified." -ForegroundColor Green
Write-ChainLog -ScriptName "pull-models.ps1" -Message "SUCCESS - all models downloaded and verified"
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
