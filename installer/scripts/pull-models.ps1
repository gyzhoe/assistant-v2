# pull-models.ps1 — Download required Ollama LLM models
$ErrorActionPreference = "Stop"

Write-Host "=== Pulling Ollama Models ===" -ForegroundColor Cyan

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
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Pulling llama3.2:3b (~2 GB)..." -ForegroundColor Yellow
& ollama pull llama3.2:3b

Write-Host "Pulling nomic-embed-text (~275 MB)..." -ForegroundColor Yellow
& ollama pull nomic-embed-text

Write-Host "Model download complete!" -ForegroundColor Green
Read-Host "Press Enter to close"
