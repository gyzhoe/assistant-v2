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
$venvDir = Join-Path $backendDir ".venv"

Write-Host "=== AI Helpdesk Assistant - Post-Install Setup ===" -ForegroundColor Cyan

# ── Kill stale processes that may lock .venv files ───────────────────────────────────────
Write-Host "Checking for running backend processes..." -ForegroundColor Yellow

# Stop backend on port 8765 (covers manual starts and service mode)
try {
    $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Stopping backend process $($proc.ProcessName) (PID $($proc.Id))..." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }
} catch { }

# Kill any Python processes running from the app's venv
try {
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($AppDir, [System.StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object {
            Write-Host "  Stopping stale process $($_.Name) (PID $($_.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 1
} catch { }

# ── Remove old venv if it exists (clean slate for new deps) ──────────────────────────────
if (Test-Path $venvDir) {
    Write-Host "Removing old virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
    if (Test-Path $venvDir) {
        Write-Host "  Warning: could not fully remove .venv (files may still be locked)." -ForegroundColor Red
        Write-Host "  Retrying after a short wait..." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
    }
}

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
        # Install all bundled wheels directly (avoids version-pin mismatches between
        # requirements.txt and the actual wheel filenames downloaded by CI).
        $wheels = Get-ChildItem -Path $wheelsDir -Filter "*.whl" | ForEach-Object { $_.FullName }
        & $uvPath pip install --python .venv\Scripts\python.exe --offline --no-index $wheels
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

# ── Generate API token and create .env if needed ──────────────────────────────
$envFile = Join-Path $backendDir ".env"
$envExample = Join-Path $backendDir ".env.example"

if (Test-Path $envFile) {
    Write-Host "Existing .env found — skipping token generation." -ForegroundColor Yellow
} elseif (Test-Path $envExample) {
    Write-Host "Generating API token..." -ForegroundColor Yellow
    $tokenBytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($tokenBytes)
    $token = ($tokenBytes | ForEach-Object { $_.ToString("x2") }) -join ""

    $envContent = Get-Content $envExample -Raw
    $envContent = $envContent -replace "API_TOKEN=REPLACE_WITH_STRONG_SECRET", "API_TOKEN=$token"
    Set-Content -Path $envFile -Value $envContent -NoNewline
    Write-Host "API token generated and written to .env (auto-detected by extension)." -ForegroundColor Green
} else {
    Write-Host "Warning: .env.example not found — skipping .env creation." -ForegroundColor Yellow
}

Write-Host "Post-install setup complete!" -ForegroundColor Green
