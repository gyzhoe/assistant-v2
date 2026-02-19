# start-backend.ps1 — Start the FastAPI backend server
$AppDir = Split-Path -Parent $PSScriptRoot
$uvPath = Join-Path $AppDir "tools\uv.exe"
$backendDir = Join-Path $AppDir "backend"

Push-Location $backendDir
& $uvPath run uvicorn app.main:app --host 127.0.0.1 --port 8765
Pop-Location
