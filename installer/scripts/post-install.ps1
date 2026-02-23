# post-install.ps1 — Sets up Python environment via uv (offline-capable)
param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$uvPath = Join-Path $AppDir "tools\uv.exe"
$backendDir = Join-Path $AppDir "backend"
$bundledPython = Join-Path $AppDir "deps\python"
$wheelsDir = Join-Path $AppDir "deps\wheels"
$requirementsFile = Join-Path $backendDir "requirements.txt"

Write-Host "=== AI Helpdesk Assistant - Post-Install Setup ===" -ForegroundColor Cyan

# Determine if we have bundled offline assets
$offlineMode = (Test-Path (Join-Path $bundledPython "python.exe")) -and (Test-Path $wheelsDir) -and (Test-Path $requirementsFile)

if ($offlineMode) {
    Write-Host "Offline mode: using bundled Python and wheels." -ForegroundColor Yellow

    # Copy bundled Python to a permanent location
    $pythonDir = Join-Path $AppDir "python"
    if (-not (Test-Path $pythonDir)) {
        Write-Host "Copying bundled Python 3.13..." -ForegroundColor Yellow
        Copy-Item -Recurse $bundledPython $pythonDir
    }
    $pythonExe = Join-Path $pythonDir "python.exe"
    Write-Host "Python 3.13 ready at $pythonExe" -ForegroundColor Green

    # Create venv using bundled Python and install from local wheels
    Write-Host "Installing backend dependencies from local wheels..." -ForegroundColor Yellow
    Push-Location $backendDir
    try {
        & $uvPath venv --python $pythonExe .venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
        & $uvPath pip install --python .venv\Scripts\python.exe --offline --no-index --find-links $wheelsDir -r $requirementsFile
        if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies from wheels" }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Online mode: downloading Python and packages." -ForegroundColor Yellow

    # Install Python 3.13 via uv (downloads from internet)
    Write-Host "Installing Python 3.13 via uv..." -ForegroundColor Yellow
    & $uvPath python install 3.13
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Python 3.13" }
    Write-Host "Python 3.13 installed." -ForegroundColor Green

    # Create venv and install backend dependencies from PyPI
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
}

Write-Host "Post-install setup complete!" -ForegroundColor Green
