# post-install.ps1 — Sets up Python environment via uv
param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$uvPath = Join-Path $AppDir "tools\uv.exe"
$backendDir = Join-Path $AppDir "backend"

Write-Host "=== AI Helpdesk Assistant - Post-Install Setup ===" -ForegroundColor Cyan

# Install Python 3.13 via uv (managed, no system install needed)
Write-Host "Installing Python 3.13 via uv..." -ForegroundColor Yellow
& $uvPath python install 3.13
if ($LASTEXITCODE -ne 0) { throw "Failed to install Python 3.13" }
Write-Host "Python 3.13 installed." -ForegroundColor Green

# Create venv and install backend dependencies
Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
Push-Location $backendDir
try {
    & $uvPath venv --python 3.13 .venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
    & $uvPath sync --python 3.13
    if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies" }
} finally {
    Pop-Location
}

Write-Host "Post-install setup complete!" -ForegroundColor Green
