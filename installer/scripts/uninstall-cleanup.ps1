# uninstall-cleanup.ps1 - AI Helpdesk Assistant Cleanup Options
# WinForms dialog shown during uninstall, offering removal of all related data.
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
$modelsDir = Join-Path $AppDir "models"
$modelsExist = Test-Path $modelsDir

$chromaDir = Join-Path $AppDir "backend\chroma_data"
$chromaExist = Test-Path $chromaDir
$venvDir = Join-Path $AppDir "backend\.venv"
$venvExist = Test-Path $venvDir
$pythonDir = Join-Path $AppDir "python"
$pythonExist = Test-Path $pythonDir
$logsDir = Join-Path $AppDir "logs"
$logsExist = Test-Path $logsDir
$envFile = Join-Path $AppDir "backend\.env"
$envExist = Test-Path $envFile
$auditFile = Join-Path $AppDir "backend\audit.log"
$auditExist = Test-Path $auditFile

# Estimate sizes
function Get-DirSizeMB($path) {
    if (-not (Test-Path $path)) { return 0 }
    try {
        [math]::Round(
            ((Get-ChildItem -Path $path -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object -Property Length -Sum).Sum / 1MB), 0)
    } catch { 0 }
}

$modelSizeMB = Get-DirSizeMB $modelsDir
$chromaSizeMB = Get-DirSizeMB $chromaDir
$venvSizeMB = Get-DirSizeMB $venvDir

$appDataExist = $chromaExist -or $logsExist -or $envExist -or $auditExist

# If nothing to clean up, exit silently
if (-not $modelsExist -and -not $appDataExist -and -not $venvExist -and -not $pythonExist) {
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
$form.Size = New-Object System.Drawing.Size(480, 390)
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
$infoLabel.Text = "Select what to remove. Uncheck items you want to keep."
$infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$infoLabel.ForeColor = $MUTED
$infoLabel.Location = New-Object System.Drawing.Point(20, 56)
$infoLabel.Size = New-Object System.Drawing.Size(440, 20)
$form.Controls.Add($infoLabel)

# --- Helper to add checkbox + note ---
$yPos = 86

function Add-CleanupOption($text, $checked, $enabled, $noteText) {
    $chk = New-Object System.Windows.Forms.CheckBox
    $chk.Text = $text
    $chk.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
    $chk.ForeColor = $TEXT
    $chk.Location = New-Object System.Drawing.Point(20, $script:yPos)
    $chk.Size = New-Object System.Drawing.Size(440, 24)
    $chk.Checked = $checked
    $chk.Enabled = $enabled
    $form.Controls.Add($chk)
    $script:yPos += 26

    if ($noteText) {
        $note = New-Object System.Windows.Forms.Label
        $note.Text = $noteText
        $note.Font = New-Object System.Drawing.Font("Segoe UI", 8)
        $note.ForeColor = $MUTED
        $note.Location = New-Object System.Drawing.Point(40, $script:yPos)
        $note.Size = New-Object System.Drawing.Size(420, 16)
        $form.Controls.Add($note)
        $script:yPos += 18
    }

    $script:yPos += 6
    return $chk
}

# --- Application data ---
$appDataNote = if ($chromaExist) {
    "Knowledge base, ticket data, logs, config (~$chromaSizeMB MB)"
} else {
    "Logs, config files"
}
$chkAppData = Add-CleanupOption "Remove application data (KB, logs, config)" $appDataExist $appDataExist $(
    if (-not $appDataExist) { "No application data found" } else { $appDataNote }
)

# --- Python venv ---
$pythonSizeMB = Get-DirSizeMB $pythonDir
$totalPySizeMB = $venvSizeMB + $pythonSizeMB
$pyExist = $venvExist -or $pythonExist
$pyNote = if ($totalPySizeMB -gt 0) { "Python environment + bundled runtime (~$totalPySizeMB MB)" } else { $null }
$chkVenv = Add-CleanupOption "Remove Python environment" $pyExist $pyExist $(
    if (-not $pyExist) { "No Python environment found" } else { $pyNote }
)

# --- Models ---
$modelLabel = if ($modelSizeMB -gt 0) { "Remove downloaded LLM models (~$modelSizeMB MB)" } else { "Remove downloaded LLM models" }
$chkModels = Add-CleanupOption $modelLabel $modelsExist $modelsExist $(
    if (-not $modelsExist) { "No model data found" } else { "GGUF model files in the install directory" }
)

# --- Buttons ---
$script:userCancelled = $true

$btnY = $script:yPos + 16

$btnContinue = New-Object System.Windows.Forms.Button
$btnContinue.Text = "Continue Uninstall"
$btnContinue.Size = New-Object System.Drawing.Size(140, 34)
$btnContinue.Location = New-Object System.Drawing.Point(180, $btnY)
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
$btnCancel.Location = New-Object System.Drawing.Point(330, $btnY)
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

# Adjust form height to fit content
$form.ClientSize = New-Object System.Drawing.Size(460, ($btnY + 50))

# --- Show dialog ---
[System.Windows.Forms.Application]::Run($form)

if ($script:userCancelled) {
    exit 1
}

# --- Perform cleanup ---

# Remove application data
if ($chkAppData.Checked -and $appDataExist) {
    # ChromaDB data
    if ($chromaExist) {
        try { Remove-Item -Path $chromaDir -Recurse -Force -ErrorAction Stop } catch {}
    }
    # Logs
    if ($logsExist) {
        try { Remove-Item -Path $logsDir -Recurse -Force -ErrorAction Stop } catch {}
    }
    # .env config
    if ($envExist) {
        try { Remove-Item -Path $envFile -Force -ErrorAction Stop } catch {}
    }
    # Audit log
    if ($auditExist) {
        try { Remove-Item -Path $auditFile -Force -ErrorAction Stop } catch {}
    }
}

# Remove Python venv and bundled Python
if ($chkVenv.Checked -and $venvExist) {
    try { Remove-Item -Path $venvDir -Recurse -Force -ErrorAction Stop } catch {}
}
if ($chkVenv.Checked -and $pythonExist) {
    try { Remove-Item -Path $pythonDir -Recurse -Force -ErrorAction Stop } catch {}
}

# Remove LLM model data
if ($chkModels.Checked -and $modelsExist) {
    try { Remove-Item -Path $modelsDir -Recurse -Force -ErrorAction Stop } catch {}
}

exit 0
