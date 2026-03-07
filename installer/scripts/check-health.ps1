# check-health.ps1 - Verify all components are working
param([switch]$NonInteractive)
$AppDir = Split-Path -Parent $PSScriptRoot
$allGood = $true

Write-Host "=== AI Helpdesk Assistant - Health Check ===" -ForegroundColor Cyan

# Check LLM Server
Write-Host "`n[LLM Server]" -ForegroundColor White
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11435/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $data = $r.Content | ConvertFrom-Json
    if ($data.status -eq "ok") {
        Write-Host "  Status: Running and ready (port 11435)" -ForegroundColor Green
    } else {
        Write-Host "  Status: Running but loading model (port 11435)" -ForegroundColor Yellow
    }
} catch {
    $statusCode = $null
    if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
    if ($statusCode -eq 503) {
        Write-Host "  Status: Running but model still loading (port 11435)" -ForegroundColor Yellow
    } else {
        Write-Host "  Status: NOT RUNNING" -ForegroundColor Red
        $allGood = $false
    }
}

# Check Embed Server
Write-Host "`n[Embed Server]" -ForegroundColor White
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11436/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $data = $r.Content | ConvertFrom-Json
    if ($data.status -eq "ok") {
        Write-Host "  Status: Running and ready (port 11436)" -ForegroundColor Green
    } else {
        Write-Host "  Status: Running but loading model (port 11436)" -ForegroundColor Yellow
    }
} catch {
    $statusCode = $null
    if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
    if ($statusCode -eq 503) {
        Write-Host "  Status: Running but model still loading (port 11436)" -ForegroundColor Yellow
    } else {
        Write-Host "  Status: NOT RUNNING" -ForegroundColor Red
        $allGood = $false
    }
}

# Check Backend
Write-Host "`n[Backend]" -ForegroundColor White
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  Status: Running" -ForegroundColor Green
    $data = $r.Content | ConvertFrom-Json
    Write-Host "  LLM: $(if ($data.llm_reachable) { 'reachable' } else { 'NOT reachable' })" -ForegroundColor Gray
    Write-Host "  ChromaDB: $(if ($data.chroma_ready) { 'ready' } else { 'not ready' })" -ForegroundColor Gray
} catch {
    Write-Host "  Status: NOT RUNNING" -ForegroundColor Red
    $allGood = $false
}

# Check Extension files
Write-Host "`n[Extension]" -ForegroundColor White
$extDir = Join-Path $AppDir "extension"
if (Test-Path (Join-Path $extDir "manifest.json")) {
    Write-Host "  Status: Files present at $extDir" -ForegroundColor Green
    Write-Host "  Note: Load in Edge via edge://extensions -> Load unpacked" -ForegroundColor Yellow
} else {
    Write-Host "  Status: NOT FOUND" -ForegroundColor Red
    $allGood = $false
}

Write-Host "`n========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "All components OK!" -ForegroundColor Green
} else {
    Write-Host "Some components need attention." -ForegroundColor Yellow
}

if (-not $NonInteractive) { Read-Host "`nPress Enter to close" }
