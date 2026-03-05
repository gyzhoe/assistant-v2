# check-health.ps1 - Verify all components are working
param([switch]$NonInteractive)
$AppDir = Split-Path -Parent $PSScriptRoot
$allGood = $true

Write-Host "=== AI Helpdesk Assistant - Health Check ===" -ForegroundColor Cyan

# Check Ollama
Write-Host "`n[Ollama]" -ForegroundColor White
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11435/api/tags" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $models = ($r.Content | ConvertFrom-Json).models.name
    Write-Host "  Status: Running" -ForegroundColor Green
    Write-Host "  Models: $($models -join ', ')" -ForegroundColor Gray
} catch {
    Write-Host "  Status: NOT RUNNING" -ForegroundColor Red
    $allGood = $false
}

# Check Backend
Write-Host "`n[Backend]" -ForegroundColor White
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  Status: Running" -ForegroundColor Green
    $data = $r.Content | ConvertFrom-Json
    Write-Host "  Ollama: $(if ($data.ollama_reachable) { 'reachable' } else { 'NOT reachable' })" -ForegroundColor Gray
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
