# stop-backend.ps1 — Stop the AI Helpdesk Backend service
param([switch]$NonInteractive)
$AppDir = Split-Path -Parent $PSScriptRoot
$nssmPath = Join-Path $AppDir "tools\nssm.exe"

if (Test-Path $nssmPath) {
    & $nssmPath stop AIHelpdeskBackend
    Write-Host "Backend service stopped." -ForegroundColor Green
} else {
    Write-Host "NSSM not found. Trying to stop uvicorn directly..." -ForegroundColor Yellow
    Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
}

if (-not $NonInteractive) { Read-Host "Press Enter to close" }
