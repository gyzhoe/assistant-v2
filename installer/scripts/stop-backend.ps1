# stop-backend.ps1 — Stop the AI Helpdesk Backend service
param([switch]$NonInteractive)
$AppDir = Split-Path -Parent $PSScriptRoot
$nssmPath = Join-Path $AppDir "tools\nssm.exe"

if (Test-Path $nssmPath) {
    & $nssmPath stop AIHelpdeskBackend
    Write-Host "Backend service stopped." -ForegroundColor Green
} else {
    Write-Host "NSSM not found. Stopping process on port 8765..." -ForegroundColor Yellow
    try {
        $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($conn) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $proc.Id -Force
                Write-Host "Stopped process $($proc.ProcessName) (PID $($proc.Id))." -ForegroundColor Green
            }
        } else {
            Write-Host "No process listening on port 8765." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to stop backend: $_" -ForegroundColor Red
    }
}

if (-not $NonInteractive) { Read-Host "Press Enter to close" }
