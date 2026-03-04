# import-models.ps1 — Import bundled Ollama models (offline install)
param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

Write-Host "=== Importing Ollama Models ===" -ForegroundColor Cyan

$bundledModels = Join-Path $AppDir "deps\ollama-models"
$ollamaDir = Join-Path $env:USERPROFILE ".ollama\models"

if (-not (Test-Path $bundledModels)) {
    Write-Host "No bundled models found at $bundledModels" -ForegroundColor Red
    Write-Host "Run 'ollama pull qwen3.5:9b' and 'ollama pull nomic-embed-text' manually." -ForegroundColor Yellow
    if (-not $NonInteractive) { Read-Host "Press Enter to exit" }
    exit 1
}

# Create target directory if it doesn't exist
if (-not (Test-Path $ollamaDir)) {
    New-Item -ItemType Directory -Path $ollamaDir -Force | Out-Null
}

# Copy blobs (model weights and configs)
$blobsSrc = Join-Path $bundledModels "blobs"
$blobsDst = Join-Path $ollamaDir "blobs"
if (Test-Path $blobsSrc) {
    Write-Host "Copying model blobs (~6.6 GB)... this may take a few minutes." -ForegroundColor Yellow
    if (-not (Test-Path $blobsDst)) {
        New-Item -ItemType Directory -Path $blobsDst -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $blobsSrc "*") -Destination $blobsDst -Recurse -Force
    Write-Host "Blobs copied." -ForegroundColor Green
}

# Copy manifests (model registry metadata)
$manifestsSrc = Join-Path $bundledModels "manifests"
$manifestsDst = Join-Path $ollamaDir "manifests"
if (Test-Path $manifestsSrc) {
    Write-Host "Copying model manifests..." -ForegroundColor Yellow
    Copy-Item -Path $manifestsSrc -Destination $ollamaDir -Recurse -Force
    Write-Host "Manifests copied." -ForegroundColor Green
}

Write-Host "Model import complete!" -ForegroundColor Green
Write-Host "Imported models: qwen3.5:9b, nomic-embed-text" -ForegroundColor Cyan
if (-not $NonInteractive) { Read-Host "Press Enter to close" }
