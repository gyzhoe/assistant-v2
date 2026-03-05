# pull-models.ps1 - Download or import required Ollama LLM models
param(
    [switch]$NonInteractive,
    [switch]$SkipModelPull
)
$ErrorActionPreference = "Stop"

# Check for bundled offline models first
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
# Honour -SkipModelPull switch or SKIP_MODEL_PULL env var (any non-empty value).
# Exits 0 with a clear SKIPPED chain-log entry so automated builds never produce
# a silent failure or a false success when network access is unavailable.
$skipEnv = ($env:SKIP_MODEL_PULL -ne $null -and $env:SKIP_MODEL_PULL.Trim() -ne "")
if ($SkipModelPull -or $skipEnv) {
    $skipReason = if ($SkipModelPull) { "-SkipModelPull flag" } else { "SKIP_MODEL_PULL=$($env:SKIP_MODEL_PULL)" }
    Write-Log "Model pull skipped ($skipReason). Run 'Setup LLM Models' from the Start Menu when ready." "INFO"
    Write-Host "Model pull skipped ($skipReason)." -ForegroundColor Yellow
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "SKIPPED - model pull bypassed ($skipReason)"
    exit 0
}
# ---------------------------------------------------------------------------------

Write-Host "=== Setting Up Ollama Models ===" -ForegroundColor Cyan
$ollamaExe = Join-Path $AppDir "tools\ollama.exe"
$bundledModels = Join-Path $AppDir "deps\ollama-models"

if (Test-Path (Join-Path $bundledModels "blobs")) {
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

    # -- Post-import verification: confirm models are registered in Ollama -------
    Write-Log "Verifying imported models via Ollama /api/tags..." "INFO"
    Write-Host "Verifying imported models..." -ForegroundColor Yellow

    # Bind Ollama to non-default port; enable Vulkan GPU backend
    $env:OLLAMA_HOST   = "127.0.0.1:11435"
    $env:OLLAMA_VULKAN = "1"
    $runnersDir = Join-Path $AppDir "tools\lib\ollama"
    if (Test-Path $runnersDir) { $env:OLLAMA_RUNNERS_DIR = $runnersDir }

    # Start Ollama if not already reachable
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Log "Ollama already reachable for post-import verification." "INFO"
    } catch {
        if (Test-Path $ollamaExe) {
            Write-Log "Starting Ollama for post-import verification..." "INFO"
            Write-Host "Starting Ollama for verification..." -ForegroundColor Yellow
            Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        } else {
            Write-Log "WARNING: ollama.exe not found at $ollamaExe — skipping model verification." "WARN"
            Write-Host "WARNING: ollama.exe not found — skipping model verification." -ForegroundColor Yellow
            Write-ChainLog -ScriptName "pull-models.ps1" -Message "SUCCESS - offline import via import-models.ps1 (verification skipped: ollama.exe absent)"
            if (-not $NonInteractive) { Read-Host "Press Enter to close" }
            exit 0
        }
    }

    # Wait for Ollama to become available
    $verifyMaxRetries = 30
    $verifyCount      = 0
    while ($verifyCount -lt $verifyMaxRetries) {
        try {
            $null = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            break
        } catch {
            $verifyCount++
            Write-Log "Waiting for Ollama to start for verification... ($verifyCount/$verifyMaxRetries)" "INFO"
            Start-Sleep -Seconds 2
        }
    }

    if ($verifyCount -eq $verifyMaxRetries) {
        Write-Log "ERROR: Ollama did not become reachable for post-import verification." "ERROR"
        Write-Host "ERROR: Ollama did not start for model verification." -ForegroundColor Red
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - Ollama did not start for post-import verification"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit 1
    }

    # Query /api/tags and check that every required model is registered
    $verifyModels     = @("nomic-embed-text", "qwen3.5:9b")
    $tagsRespV        = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 5
    $tagsJsonV        = $tagsRespV.Content | ConvertFrom-Json
    $installedNamesV  = @()
    foreach ($im in $tagsJsonV.models) { $installedNamesV += $im.name.ToLower() }

    $verifyMissing = @()
    foreach ($req in $verifyModels) {
        $found = $false
        $candidates = @($req.ToLower())
        if ($req -notmatch ":") { $candidates += "$($req):latest".ToLower() }
        foreach ($c in $candidates) {
            if ($installedNamesV -contains $c) { $found = $true; break }
        }
        if (-not $found) { $verifyMissing += $req }
    }

    if ($verifyMissing.Count -gt 0) {
        Write-Log "ERROR: Post-import verification failed — missing models: $($verifyMissing -join ', ')" "ERROR"
        Write-Host "ERROR: Post-import verification failed — missing models: $($verifyMissing -join ', ')" -ForegroundColor Red
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - post-import verification: missing models: $($verifyMissing -join ', ')"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit 1
    }

    Write-Log "Post-import verification passed — all models present in Ollama." "INFO"
    Write-Host "Offline model import and verification complete!" -ForegroundColor Green
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "SUCCESS - offline import verified via /api/tags"
    if (-not $NonInteractive) { Read-Host "Press Enter to close" }
    exit 0
}

# Online fallback: pull models from Ollama registry
Write-Log "No bundled models found - pulling from internet..." "INFO"
Write-Host "No bundled models found - pulling from internet..." -ForegroundColor Yellow

# Bind Ollama to non-default port to avoid conflicts with system installs
$env:OLLAMA_HOST = "127.0.0.1:11435"
# Enable Vulkan GPU backend for AMD/Intel GPUs (silently falls back to CPU if unavailable)
$env:OLLAMA_VULKAN = "1"
# Point to bundled CUDA/CPU runners for GPU acceleration
$runnersDir = Join-Path $AppDir "tools\lib\ollama"
if (Test-Path $runnersDir) { $env:OLLAMA_RUNNERS_DIR = $runnersDir }

# Start Ollama if not already running
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
} catch {
    if (Test-Path $ollamaExe) {
        Write-Log "Starting Ollama..." "INFO"
        Write-Host "Starting Ollama..." -ForegroundColor Yellow
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
}

# Wait for Ollama to be available
$maxRetries = 30
$retryCount = 0
while ($retryCount -lt $maxRetries) {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        break
    } catch {
        $retryCount++
        Write-Log "Waiting for Ollama to start... ($retryCount/$maxRetries)" "INFO"
        Write-Host "Waiting for Ollama to start... ($retryCount/$maxRetries)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

if ($retryCount -eq $maxRetries) {
    Write-Log "ERROR: Ollama is not running after $maxRetries retries. Aborting." "ERROR"
    Write-Host "ERROR: Ollama is not running. Please start Ollama first." -ForegroundColor Red
    Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - Ollama did not start after $maxRetries retries"
    if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
    exit 1
}

$models = @(
    @{ name = "nomic-embed-text"; desc = "~275 MB" }
    @{ name = "qwen3.5:9b"; desc = "~6 GB" }
)
$maxPullRetries = 4
$pullRetryDelay = 5

foreach ($m in $models) {
    $modelName = $m.name
    $succeeded = $false
    $lastExitCode = 0
    for ($attempt = 0; $attempt -le $maxPullRetries; $attempt++) {
        if ($attempt -gt 0) {
            Write-Log "  Pull attempt $attempt of $($maxPullRetries + 1) failed (exit code $lastExitCode) — sleeping ${pullRetryDelay}s before attempt $($attempt + 1)..." "WARN"
            Write-Host "  Pull failed (exit $lastExitCode) — retrying in ${pullRetryDelay}s (attempt $($attempt + 1) of $($maxPullRetries + 1))..." -ForegroundColor Yellow
            Start-Sleep -Seconds $pullRetryDelay
        }
        Write-Log "Pull attempt $($attempt + 1) of $($maxPullRetries + 1) started for $modelName ($($m.desc))" "INFO"
        Write-Host "Pulling $modelName ($($m.desc))... [attempt $($attempt + 1)/$($maxPullRetries + 1)]" -ForegroundColor Yellow
        & $ollamaExe pull $modelName
        $lastExitCode = $LASTEXITCODE
        if ($lastExitCode -eq 0) {
            Write-Log "Pull attempt $($attempt + 1) of $($maxPullRetries + 1) succeeded for $modelName" "INFO"
            $succeeded = $true
            break
        }
        Write-Log "Pull attempt $($attempt + 1) of $($maxPullRetries + 1) for $modelName failed (exit code $lastExitCode)" "WARN"
    }
    if (-not $succeeded) {
        Write-Log "ERROR: Failed to pull $modelName after $($maxPullRetries + 1) attempts." "ERROR"
        Write-Host "ERROR: Failed to pull $modelName after $($maxPullRetries + 1) attempts." -ForegroundColor Red
        Write-ChainLog -ScriptName "pull-models.ps1" -Message "FAILED - $modelName pull exhausted $($maxPullRetries + 1) attempts (last exit code $lastExitCode)"
        if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
        exit 1
    }
}

# Verify all models are present via /api/tags
Write-Log "Verifying downloaded models..." "INFO"
Write-Host "Verifying downloaded models..." -ForegroundColor Yellow
$tagsResp = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 5
$tagsJson = $tagsResp.Content | ConvertFrom-Json
$installedNames = @()
foreach ($im in $tagsJson.models) { $installedNames += $im.name.ToLower() }

$missing = @()
foreach ($m in $models) {
    $req = $m.name
    $found = $false
    $candidates = @($req.ToLower())
    if ($req -notmatch ":") { $candidates += "$($req):latest".ToLower() }
    foreach ($c in $candidates) {
        if ($installedNames -contains $c) { $found = $true; break }
    }
    if (-not $found) { $missing += $req }
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
Write-ChainLog -ScriptName "pull-models.ps1" -Message "SUCCESS - all models pulled and verified"
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
