# uninstall-cleanup.ps1 - AI Helpdesk Assistant Cleanup Options
# WinForms dialog shown during uninstall, offering removal of Ollama runtime and LLM models.
# Exit codes: 0 = cleanup completed (or skipped by user choice), 1 = user cancelled.

param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

# --- Hide the console window ---
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class CleanupConsoleWin32 {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$consoleHwnd = [CleanupConsoleWin32]::GetConsoleWindow()
if ($consoleHwnd -ne [IntPtr]::Zero) {
    [CleanupConsoleWin32]::ShowWindow($consoleHwnd, 0) | Out-Null
}

# --- Load WinForms ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# --- Detect environment ---
$ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
$ollamaUninstaller = Join-Path $ollamaDir "unins000.exe"
$ollamaInstalled = Test-Path $ollamaUninstaller
$modelsDir = Join-Path $env:USERPROFILE ".ollama\models"
$modelsExist = Test-Path $modelsDir

# Estimate model size
$modelSizeMB = 0
if ($modelsExist) {
    try {
        $modelSizeMB = [math]::Round(
            ((Get-ChildItem -Path $modelsDir -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object -Property Length -Sum).Sum / 1MB), 0)
    } catch { $modelSizeMB = 0 }
}

# If nothing to clean up, exit silently
if (-not $ollamaInstalled -and -not $modelsExist) {
    exit 0
}

# --- Constants ---
$ACCENT = [System.Drawing.Color]::FromArgb(255, 0, 120, 212)
$BG     = [System.Drawing.Color]::FromArgb(255, 249, 250, 251)
$BORDER = [System.Drawing.Color]::FromArgb(255, 229, 231, 235)
$TEXT   = [System.Drawing.Color]::FromArgb(255, 55, 65, 81)
$MUTED  = [System.Drawing.Color]::FromArgb(255, 107, 114, 128)

# --- Build the dialog ---
$form = New-Object System.Windows.Forms.Form
$form.Text = "AI Helpdesk Assistant - Cleanup Options"
$form.Size = New-Object System.Drawing.Size(460, 300)
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.BackColor = $BG
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$form.TopMost = $true

# --- Header ---
$headerPanel = New-Object System.Windows.Forms.Panel
$headerPanel.Dock = [System.Windows.Forms.DockStyle]::Top
$headerPanel.Height = 44
$headerPanel.BackColor = $ACCENT

$headerLabel = New-Object System.Windows.Forms.Label
$headerLabel.Text = "Cleanup Options"
$headerLabel.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 12)
$headerLabel.ForeColor = [System.Drawing.Color]::White
$headerLabel.AutoSize = $true
$headerLabel.Location = New-Object System.Drawing.Point(16, 10)
$headerPanel.Controls.Add($headerLabel)
$form.Controls.Add($headerPanel)

# --- Info label ---
$infoLabel = New-Object System.Windows.Forms.Label
$infoLabel.Text = "Uncheck items you want to keep for other projects."
$infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$infoLabel.ForeColor = $MUTED
$infoLabel.Location = New-Object System.Drawing.Point(20, 56)
$infoLabel.Size = New-Object System.Drawing.Size(400, 20)
$form.Controls.Add($infoLabel)

# --- Ollama checkbox ---
$chkOllama = New-Object System.Windows.Forms.CheckBox
$chkOllama.Text = "Remove Ollama LLM Runtime (~100 MB)"
$chkOllama.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$chkOllama.ForeColor = $TEXT
$chkOllama.Location = New-Object System.Drawing.Point(20, 90)
$chkOllama.Size = New-Object System.Drawing.Size(400, 24)
$chkOllama.Checked = $ollamaInstalled
$chkOllama.Enabled = $ollamaInstalled
$form.Controls.Add($chkOllama)

if (-not $ollamaInstalled) {
    $ollamaNote = New-Object System.Windows.Forms.Label
    $ollamaNote.Text = "Ollama not found - nothing to remove"
    $ollamaNote.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $ollamaNote.ForeColor = $MUTED
    $ollamaNote.Location = New-Object System.Drawing.Point(40, 114)
    $ollamaNote.Size = New-Object System.Drawing.Size(380, 16)
    $form.Controls.Add($ollamaNote)
}

# --- Models checkbox ---
$modelLabel = if ($modelSizeMB -gt 0) {
    "Remove downloaded LLM models (~$modelSizeMB MB)"
} else {
    "Remove downloaded LLM models"
}
$chkModels = New-Object System.Windows.Forms.CheckBox
$chkModels.Text = $modelLabel
$chkModels.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$chkModels.ForeColor = $TEXT
$chkModels.Location = New-Object System.Drawing.Point(20, 140)
$chkModels.Size = New-Object System.Drawing.Size(400, 24)
$chkModels.Checked = $modelsExist
$chkModels.Enabled = $modelsExist
$form.Controls.Add($chkModels)

if (-not $modelsExist) {
    $modelsNote = New-Object System.Windows.Forms.Label
    $modelsNote.Text = "No model data found - nothing to remove"
    $modelsNote.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $modelsNote.ForeColor = $MUTED
    $modelsNote.Location = New-Object System.Drawing.Point(40, 164)
    $modelsNote.Size = New-Object System.Drawing.Size(380, 16)
    $form.Controls.Add($modelsNote)
}

# --- Buttons ---
$script:userCancelled = $true

$btnContinue = New-Object System.Windows.Forms.Button
$btnContinue.Text = "Continue Uninstall"
$btnContinue.Size = New-Object System.Drawing.Size(140, 34)
$btnContinue.Location = New-Object System.Drawing.Point(160, 210)
$btnContinue.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnContinue.BackColor = $ACCENT
$btnContinue.ForeColor = [System.Drawing.Color]::White
$btnContinue.FlatAppearance.BorderSize = 0
$btnContinue.Cursor = [System.Windows.Forms.Cursors]::Hand
$btnContinue.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 9)
$btnContinue.Add_Click({
    $script:userCancelled = $false
    $form.Close()
})
$form.Controls.Add($btnContinue)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Text = "Cancel"
$btnCancel.Size = New-Object System.Drawing.Size(90, 34)
$btnCancel.Location = New-Object System.Drawing.Point(310, 210)
$btnCancel.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnCancel.FlatAppearance.BorderColor = $BORDER
$btnCancel.BackColor = [System.Drawing.Color]::White
$btnCancel.Cursor = [System.Windows.Forms.Cursors]::Hand
$btnCancel.Add_Click({
    $form.Close()
})
$form.Controls.Add($btnCancel)

$form.AcceptButton = $btnContinue
$form.CancelButton = $btnCancel

# --- Show dialog ---
[System.Windows.Forms.Application]::Run($form)

if ($script:userCancelled) {
    exit 1
}

# --- Perform cleanup ---

# Remove Ollama runtime
if ($chkOllama.Checked -and $ollamaInstalled) {
    try {
        $proc = Start-Process -FilePath $ollamaUninstaller -ArgumentList "/VERYSILENT /NORESTART" -Wait -PassThru
        # Also kill any lingering Ollama processes
        Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    } catch {
        # Best-effort - don't block uninstall if Ollama removal fails
    }
}

# Remove LLM model data
if ($chkModels.Checked -and $modelsExist) {
    try {
        Remove-Item -Path $modelsDir -Recurse -Force -ErrorAction Stop
    } catch {
        # Best-effort - files might be locked
    }
}

exit 0
