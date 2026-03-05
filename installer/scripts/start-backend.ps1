# start-backend.ps1 - Start the FastAPI backend server
$AppDir = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $AppDir "backend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$uvPath = Join-Path $AppDir "tools\uv.exe"

# Ensure Ollama binds to the isolated port and finds bundled CUDA runners
$env:OLLAMA_HOST = "127.0.0.1:11435"
$runnersDir = Join-Path $AppDir "tools\lib\ollama"
if (Test-Path $runnersDir) { $env:OLLAMA_RUNNERS_DIR = $runnersDir }

Push-Location $backendDir
if (Test-Path $venvPython) {
    # Use venv directly (works offline - no resolution step)
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
} else {
    # Fallback to uv run (requires uv sync to have been run)
    & $uvPath run uvicorn app.main:app --host 127.0.0.1 --port 8765
}
Pop-Location
