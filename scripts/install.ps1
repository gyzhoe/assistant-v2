#Requires -Version 5.1
<#
.SYNOPSIS
    One-command installer for AI Helpdesk Assistant.

.DESCRIPTION
    Downloads and runs the latest AI Helpdesk Assistant installer from GitHub.
    Defaults to silent install. Use -Interactive to show the installer UI.

.PARAMETER Interactive
    Run the installer with the setup UI visible instead of silently.

.EXAMPLE
    # Silent install (default):
    irm https://raw.githubusercontent.com/gyzhoe/assistant-v2/main/scripts/install.ps1 | iex

.EXAMPLE
    # Interactive install:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/gyzhoe/assistant-v2/main/scripts/install.ps1))) -Interactive
#>
param(
    [switch]$Interactive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = 'gyzhoe/assistant-v2'
$ApiUrl = "https://api.github.com/repos/$Repo/releases/latest"

function Write-Step {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Red
}

Write-Host ""
Write-Host "AI Helpdesk Assistant — Installer" -ForegroundColor White
Write-Host "====================================" -ForegroundColor DarkGray
Write-Host ""

# --- Fetch latest release info ---
Write-Step "Fetching latest release from GitHub..."

try {
    $Release = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Fail "Failed to fetch release info: $_"
    Write-Fail "Check your internet connection and try again."
    exit 1
}

$Tag = $Release.tag_name
$Asset = $Release.assets | Where-Object { $_.name -like '*.exe' } | Select-Object -First 1

if (-not $Asset) {
    Write-Fail "No .exe asset found in release $Tag."
    exit 1
}

$DownloadUrl = $Asset.browser_download_url
$FileName    = $Asset.name
$TempPath    = Join-Path $env:TEMP $FileName

Write-Step "Found release $Tag — $FileName"

# --- Download installer ---
Write-Step "Downloading installer to $TempPath ..."

try {
    $ProgressPreference = 'SilentlyContinue'   # suppress slow progress bar
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempPath -UseBasicParsing -ErrorAction Stop
    $ProgressPreference = 'Continue'
} catch {
    Write-Fail "Download failed: $_"
    if (Test-Path $TempPath) { Remove-Item $TempPath -Force }
    exit 1
}

if (-not (Test-Path $TempPath) -or (Get-Item $TempPath).Length -eq 0) {
    Write-Fail "Downloaded file is missing or empty."
    exit 1
}

Write-Success "Download complete."

# --- Run installer ---
if ($Interactive) {
    Write-Step "Launching installer UI..."
    $InstallerArgs = @('/SP-', '/NORESTART')
} else {
    Write-Step "Running silent install..."
    $InstallerArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
}

try {
    $Process = Start-Process -FilePath $TempPath -ArgumentList $InstallerArgs -Wait -PassThru -ErrorAction Stop
} catch {
    Write-Fail "Failed to start installer: $_"
    Remove-Item $TempPath -Force -ErrorAction SilentlyContinue
    exit 1
}

$ExitCode = $Process.ExitCode

# --- Clean up ---
Remove-Item $TempPath -Force -ErrorAction SilentlyContinue

# --- Result ---
if ($ExitCode -ne 0) {
    Write-Fail "Installer exited with code $ExitCode."
    Write-Fail "Try running with -Interactive to see what went wrong."
    exit $ExitCode
}

Write-Host ""
Write-Success "AI Helpdesk Assistant $Tag installed successfully."
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor DarkGray
Write-Host "  1. Open Microsoft Edge and load the extension from the install directory." -ForegroundColor DarkGray
Write-Host "  2. Open a WHD ticket and press Alt+Shift+H to activate the sidebar." -ForegroundColor DarkGray
Write-Host ""
