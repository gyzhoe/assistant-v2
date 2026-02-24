# register-native-host.ps1 — Register the native messaging host for Edge/Chrome
# Run once after installing the extension. Requires the extension ID.
#
# Usage:
#   .\register-native-host.ps1 -ExtensionId "abcdefghijklmnopqrstuvwxyz012345"
#   .\register-native-host.ps1 -ExtensionId "abcdefgh..." -Browser Chrome

param(
    [Parameter(Mandatory=$true)]
    [string]$ExtensionId,

    [ValidateSet("Edge", "Chrome")]
    [string]$Browser = "Edge"
)

$HostName = "com.assistant.backend_manager"
$AppDir   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$HostCmd  = Join-Path $AppDir "backend\native_host.cmd"

if (-not (Test-Path $HostCmd)) {
    Write-Host "ERROR: native_host.cmd not found at $HostCmd" -ForegroundColor Red
    exit 1
}

# Build the manifest
$ManifestDir = Join-Path $AppDir "backend"
$ManifestPath = Join-Path $ManifestDir "$HostName.json"

$manifest = @{
    name             = $HostName
    description      = "AI Helpdesk Assistant - Service Manager"
    path             = $HostCmd
    type             = "stdio"
    allowed_origins  = @("chrome-extension://$ExtensionId/")
} | ConvertTo-Json -Depth 3

Set-Content -Path $ManifestPath -Value $manifest -Encoding UTF8
Write-Host "Manifest written to: $ManifestPath" -ForegroundColor Green

# Write registry key
$regBase = if ($Browser -eq "Chrome") {
    "HKCU:\SOFTWARE\Google\Chrome\NativeMessagingHosts"
} else {
    "HKCU:\SOFTWARE\Microsoft\Edge\NativeMessagingHosts"
}

if (-not (Test-Path $regBase)) {
    New-Item -Path $regBase -Force | Out-Null
}

$regKey = Join-Path $regBase $HostName
New-Item -Path $regKey -Force | Out-Null
Set-ItemProperty -Path $regKey -Name "(Default)" -Value $ManifestPath
Write-Host "Registry key set: $regKey -> $ManifestPath" -ForegroundColor Green

Write-Host "`nNative messaging host registered for $Browser." -ForegroundColor Cyan
Write-Host "Extension ID: $ExtensionId" -ForegroundColor Cyan
Write-Host "Restart $Browser for changes to take effect." -ForegroundColor Yellow
