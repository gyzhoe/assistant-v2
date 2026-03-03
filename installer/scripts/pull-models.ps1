# pull-models.ps1 — Download or import required Ollama LLM models
param([switch]$NonInteractive)
$ErrorActionPreference = "Stop"

Write-Host "=== Setting Up Ollama Models ===" -ForegroundColor Cyan

# Check for bundled offline models first
$AppDir = Split-Path -Parent $PSScriptRoot
$bundledModels = Join-Path $AppDir "deps\ollama-models"

if (Test-Path (Join-Path $bundledModels "blobs")) {
    Write-Host "Found bundled models — importing offline..." -ForegroundColor Yellow
    & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "import-models.ps1") -AppDir $AppDir -NonInteractive:$NonInteractive
    exit $LASTEXITCODE
}

# Online fallback: pull models from Ollama registry
Write-Host "No bundled models found — pulling from internet..." -ForegroundColor Yellow

# Wait for Ollama to be available
$maxRetries = 30
$retryCount = 0
while ($retryCount -lt $maxRetries) {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
        break
    } catch {
        $retryCount++
        Write-Host "Waiting for Ollama to start... ($retryCount/$maxRetries)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

if ($retryCount -eq $maxRetries) {
    Write-Host "ERROR: Ollama is not running. Please start Ollama first." -ForegroundColor Red
    if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
    exit 1
}

Write-Host "Pulling qwen2.5:14b (~9 GB)..." -ForegroundColor Yellow
& ollama pull qwen2.5:14b

Write-Host "Pulling nomic-embed-text (~275 MB)..." -ForegroundColor Yellow
& ollama pull nomic-embed-text

Write-Host "Model download complete!" -ForegroundColor Green
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
