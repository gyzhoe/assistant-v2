# dashboard.ps1 — AI Helpdesk Assistant Service Dashboard
# WinForms GUI showing service status with start/stop controls.
# Launched from the Start Menu shortcut or by double-clicking the tray icon.

$AppDir = Split-Path -Parent $PSScriptRoot

# --- Single-instance guard using a named mutex ---
$mutex = New-Object System.Threading.Mutex($false, "Global\AIHelpdeskDashboard")
if (-not $mutex.WaitOne(0, $false)) {
    # Another instance is running — bring it to front via its window title
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DashboardWin32 {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
}
"@
    $hwnd = [DashboardWin32]::FindWindow($null, "AI Helpdesk Assistant")
    if ($hwnd -ne [IntPtr]::Zero) {
        [DashboardWin32]::ShowWindow($hwnd, 9) | Out-Null  # SW_RESTORE
        [DashboardWin32]::SetForegroundWindow($hwnd) | Out-Null
    }
    $mutex.Dispose()
    return
}

# --- Hide the console window ---
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ConsoleWin32 {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$consoleHwnd = [ConsoleWin32]::GetConsoleWindow()
if ($consoleHwnd -ne [IntPtr]::Zero) {
    [ConsoleWin32]::ShowWindow($consoleHwnd, 0) | Out-Null
}

# --- Load WinForms and Drawing ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# --- Constants ---
$ACCENT  = [System.Drawing.Color]::FromArgb(255, 0, 120, 212)  # #0078d4
$GREEN   = [System.Drawing.Color]::FromArgb(255, 16, 185, 129)
$RED     = [System.Drawing.Color]::FromArgb(255, 239, 68, 68)
$GRAY    = [System.Drawing.Color]::FromArgb(255, 156, 163, 175)
$AMBER   = [System.Drawing.Color]::FromArgb(255, 245, 158, 11)
$BG      = [System.Drawing.Color]::FromArgb(255, 249, 250, 251)
$BORDER  = [System.Drawing.Color]::FromArgb(255, 229, 231, 235)

$nssmPath = Join-Path $AppDir "tools\nssm.exe"
$hasNssm  = Test-Path $nssmPath

# --- Helpers ---
function Test-Port([int]$port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        return ($null -ne $conn)
    } catch { return $false }
}

function Stop-ByPort([int]$port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($conn) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
            return $true
        }
    } catch {}
    return $false
}

function Get-HealthData {
    try {
        $wc = New-Object System.Net.WebClient
        $json = $wc.DownloadString("http://localhost:8765/health")
        $wc.Dispose()
        return ($json | ConvertFrom-Json)
    } catch { return $null }
}

function Test-Ollama {
    try {
        $wc = New-Object System.Net.WebClient
        $null = $wc.DownloadString("http://localhost:11434/api/tags")
        $wc.Dispose()
        return $true
    } catch { return $false }
}

# --- Build the Form ---
$form = New-Object System.Windows.Forms.Form
$form.Text = "AI Helpdesk Assistant"
$form.Size = New-Object System.Drawing.Size(560, 550)
$form.MinimumSize = $form.Size
$form.MaximumSize = $form.Size
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.MaximizeBox = $false
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.BackColor = $BG
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

# --- Header bar ---
$header = New-Object System.Windows.Forms.Panel
$header.Dock = [System.Windows.Forms.DockStyle]::Top
$header.Height = 52
$header.BackColor = $ACCENT

$headerTitle = New-Object System.Windows.Forms.Label
$headerTitle.Text = "AI Helpdesk Assistant"
$headerTitle.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 14)
$headerTitle.ForeColor = [System.Drawing.Color]::White
$headerTitle.AutoSize = $true
$headerTitle.Location = New-Object System.Drawing.Point(16, 6)
$header.Controls.Add($headerTitle)

$headerVersion = New-Object System.Windows.Forms.Label
$headerVersion.Text = ""
$headerVersion.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$headerVersion.ForeColor = [System.Drawing.Color]::FromArgb(200, 255, 255, 255)
$headerVersion.AutoSize = $true
$headerVersion.Location = New-Object System.Drawing.Point(16, 32)
$header.Controls.Add($headerVersion)

$form.Controls.Add($header)

# --- Helper to create a section GroupBox ---
function New-Section([string]$title, [int]$top, [int]$height) {
    $gb = New-Object System.Windows.Forms.GroupBox
    $gb.Text = $title
    $gb.Location = New-Object System.Drawing.Point(12, $top)
    $gb.Size = New-Object System.Drawing.Size(520, $height)
    $gb.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 9)
    $gb.ForeColor = [System.Drawing.Color]::FromArgb(255, 55, 65, 81)
    return $gb
}

# --- Helper to create a status circle ---
function New-StatusCircle([int]$x, [int]$y) {
    $panel = New-Object System.Windows.Forms.Panel
    $panel.Location = New-Object System.Drawing.Point($x, $y)
    $panel.Size = New-Object System.Drawing.Size(12, 12)
    $panel.BackColor = $GRAY
    $panel.Tag = $GRAY
    $panel.Add_Paint({
        param($s, $e)
        $e.Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $e.Graphics.Clear($s.Parent.BackColor)
        $brush = New-Object System.Drawing.SolidBrush($s.BackColor)
        $e.Graphics.FillEllipse($brush, 0, 0, 11, 11)
        $brush.Dispose()
    })
    return $panel
}

# =============== SERVICES SECTION ===============
$svcGroup = New-Section "Services" 62 130
$svcGroup.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 9)
$form.Controls.Add($svcGroup)

$script:svcRows = @{}
$rowY = 24
foreach ($svc in @(
    @{ Name = "Backend";  Port = 8765;  Key = "backend"  },
    @{ Name = "Ollama";   Port = 11434; Key = "ollama"   },
    @{ Name = "ChromaDB"; Port = $null; Key = "chromadb" }
)) {
    $circle = New-StatusCircle 16 ($rowY + 4)
    $svcGroup.Controls.Add($circle)

    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $svc.Name
    $lbl.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $lbl.ForeColor = [System.Drawing.Color]::FromArgb(255, 55, 65, 81)
    $lbl.Location = New-Object System.Drawing.Point(36, $rowY)
    $lbl.Size = New-Object System.Drawing.Size(90, 20)
    $svcGroup.Controls.Add($lbl)

    $statusLbl = New-Object System.Windows.Forms.Label
    $statusLbl.Text = "Checking..."
    $statusLbl.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $statusLbl.ForeColor = $GRAY
    $statusLbl.Location = New-Object System.Drawing.Point(130, $rowY)
    $statusLbl.Size = New-Object System.Drawing.Size(200, 20)
    $svcGroup.Controls.Add($statusLbl)

    $btnStart = New-Object System.Windows.Forms.Button
    $btnStart.Text = "Start"
    $btnStart.Size = New-Object System.Drawing.Size(65, 26)
    $btnStart.Location = New-Object System.Drawing.Point(365, ($rowY - 3))
    $btnStart.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $btnStart.FlatAppearance.BorderColor = $BORDER
    $btnStart.BackColor = [System.Drawing.Color]::White
    $btnStart.Cursor = [System.Windows.Forms.Cursors]::Hand
    $svcGroup.Controls.Add($btnStart)

    $btnStop = New-Object System.Windows.Forms.Button
    $btnStop.Text = "Stop"
    $btnStop.Size = New-Object System.Drawing.Size(65, 26)
    $btnStop.Location = New-Object System.Drawing.Point(438, ($rowY - 3))
    $btnStop.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $btnStop.FlatAppearance.BorderColor = $BORDER
    $btnStop.BackColor = [System.Drawing.Color]::White
    $btnStop.Cursor = [System.Windows.Forms.Cursors]::Hand
    $svcGroup.Controls.Add($btnStop)

    $script:svcRows[$svc.Key] = @{
        Circle = $circle; Status = $statusLbl;
        Start = $btnStart; Stop = $btnStop;
        Port = $svc.Port; Name = $svc.Name
    }
    $rowY += 34
}

# --- Button click handlers ---
function Disable-Briefly([System.Windows.Forms.Button]$btn, [int]$ms = 2500) {
    $btn.Enabled = $false
    $t = New-Object System.Windows.Forms.Timer
    $t.Interval = $ms
    $t.Tag = $btn
    $t.Add_Tick({ $this.Tag.Enabled = $true; $this.Stop(); $this.Dispose() })
    $t.Start()
}

# Backend Start
$script:svcRows.backend.Start.Add_Click({
    Disable-Briefly $script:svcRows.backend.Start
    if ($hasNssm) {
        Start-Process -FilePath $nssmPath -ArgumentList "start AIHelpdeskBackend" -WindowStyle Hidden
    } else {
        $s = Join-Path $AppDir "scripts\start-backend.ps1"
        Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$s`"" -WindowStyle Hidden
    }
})

# Backend Stop
$script:svcRows.backend.Stop.Add_Click({
    Disable-Briefly $script:svcRows.backend.Stop
    if ($hasNssm) {
        Start-Process -FilePath $nssmPath -ArgumentList "stop AIHelpdeskBackend" -WindowStyle Hidden
    } else {
        Stop-ByPort 8765
    }
})

# Ollama Start
$script:svcRows.ollama.Start.Add_Click({
    Disable-Briefly $script:svcRows.ollama.Start
    if ($hasNssm) {
        Start-Process -FilePath $nssmPath -ArgumentList "start AIHelpdeskOllama" -WindowStyle Hidden
    } else {
        # Try ollama serve directly
        $ollamaExe = $null
        foreach ($p in @(
            "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
            "$env:ProgramFiles\Ollama\ollama.exe"
        )) { if (Test-Path $p) { $ollamaExe = $p; break } }
        if (-not $ollamaExe) { $ollamaExe = "ollama.exe" }
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
})

# Ollama Stop
$script:svcRows.ollama.Stop.Add_Click({
    Disable-Briefly $script:svcRows.ollama.Stop
    if ($hasNssm) {
        Start-Process -FilePath $nssmPath -ArgumentList "stop AIHelpdeskOllama" -WindowStyle Hidden
    } else {
        Stop-ByPort 11434
    }
})

# ChromaDB has no independent start/stop (embedded in backend)
$script:svcRows.chromadb.Start.Visible = $false
$script:svcRows.chromadb.Stop.Visible = $false

# =============== KNOWLEDGE BASE SECTION ===============
$kbGroup = New-Section "Knowledge Base" 200 70
$form.Controls.Add($kbGroup)

$kbLabel = New-Object System.Windows.Forms.Label
$kbLabel.Text = "Waiting for backend..."
$kbLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$kbLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 107, 114, 128)
$kbLabel.Location = New-Object System.Drawing.Point(16, 28)
$kbLabel.Size = New-Object System.Drawing.Size(490, 32)
$kbGroup.Controls.Add($kbLabel)

# =============== EXTENSION SECTION ===============
$extGroup = New-Section "Browser Extension" 278 70
$form.Controls.Add($extGroup)

$extLabel = New-Object System.Windows.Forms.Label
$extLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$extLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 107, 114, 128)
$extLabel.Location = New-Object System.Drawing.Point(16, 28)
$extLabel.Size = New-Object System.Drawing.Size(370, 32)
$extGroup.Controls.Add($extLabel)

$extLink = New-Object System.Windows.Forms.LinkLabel
$extLink.Text = "Open Extension Folder"
$extLink.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$extLink.AutoSize = $true
$extLink.Location = New-Object System.Drawing.Point(390, 28)
$extLink.LinkColor = $ACCENT
$extLink.Add_LinkClicked({
    $extDir = Join-Path $AppDir "extension"
    Start-Process explorer.exe -ArgumentList $extDir
})
$extGroup.Controls.Add($extLink)

# Check extension files
$extDir = Join-Path $AppDir "extension"
$manifestExists = Test-Path (Join-Path $extDir "manifest.json")
if ($manifestExists) {
    $extLabel.Text = "Extension files installed"
    $extLabel.ForeColor = $GREEN
} else {
    $extLabel.Text = "Extension files not found"
    $extLabel.ForeColor = $RED
}

# =============== FOOTER ===============
$refreshBtn = New-Object System.Windows.Forms.Button
$refreshBtn.Text = "Refresh Now"
$refreshBtn.Size = New-Object System.Drawing.Size(100, 30)
$refreshBtn.Location = New-Object System.Drawing.Point(12, 360)
$refreshBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$refreshBtn.FlatAppearance.BorderColor = $BORDER
$refreshBtn.BackColor = [System.Drawing.Color]::White
$refreshBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
$form.Controls.Add($refreshBtn)

$autoRefreshLabel = New-Object System.Windows.Forms.Label
$autoRefreshLabel.Text = "Auto-refreshes every 5 seconds"
$autoRefreshLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$autoRefreshLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 156, 163, 175)
$autoRefreshLabel.AutoSize = $true
$autoRefreshLabel.Location = New-Object System.Drawing.Point(120, 367)
$form.Controls.Add($autoRefreshLabel)

$lastUpdateLabel = New-Object System.Windows.Forms.Label
$lastUpdateLabel.Text = ""
$lastUpdateLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$lastUpdateLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 156, 163, 175)
$lastUpdateLabel.AutoSize = $true
$lastUpdateLabel.Location = New-Object System.Drawing.Point(12, 396)
$form.Controls.Add($lastUpdateLabel)

# --- Separator line ---
$separator = New-Object System.Windows.Forms.Panel
$separator.Location = New-Object System.Drawing.Point(12, 424)
$separator.Size = New-Object System.Drawing.Size(520, 1)
$separator.BackColor = $BORDER
$form.Controls.Add($separator)

# --- Uninstall link ---
$uninstallLink = New-Object System.Windows.Forms.LinkLabel
$uninstallLink.Text = "Uninstall AI Helpdesk Assistant..."
$uninstallLink.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$uninstallLink.AutoSize = $true
$uninstallLink.Location = New-Object System.Drawing.Point(12, 436)
$uninstallLink.LinkColor = [System.Drawing.Color]::FromArgb(255, 156, 163, 175)
$uninstallLink.ActiveLinkColor = $RED
$uninstallLink.Cursor = [System.Windows.Forms.Cursors]::Hand
$uninstallLink.Add_LinkClicked({
    $uninsExe = Join-Path $AppDir "unins000.exe"
    if (-not (Test-Path $uninsExe)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Uninstaller not found at:`n$uninsExe`n`nYou can uninstall from Windows Settings > Apps.",
            "Uninstaller Not Found",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        )
        return
    }
    $confirm = [System.Windows.Forms.MessageBox]::Show(
        "This will uninstall AI Helpdesk Assistant and stop all services.`n`nYou'll be able to choose whether to keep Ollama and model data.`n`nContinue?",
        "Confirm Uninstall",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($confirm -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-Process -FilePath $uninsExe
        $form.Close()
    }
})
$form.Controls.Add($uninstallLink)

# =============== STATUS REFRESH LOGIC ===============
function Update-Status {
    $health = Get-HealthData
    $now = Get-Date -Format "HH:mm:ss"
    $lastUpdateLabel.Text = "Last updated: $now"

    if ($health) {
        # Backend is up
        $script:svcRows.backend.Circle.BackColor = $GREEN
        $script:svcRows.backend.Status.Text = "Running"
        $script:svcRows.backend.Status.ForeColor = $GREEN

        # Version from health endpoint
        if ($health.version) {
            $headerVersion.Text = "v$($health.version)"
        }

        # Ollama status from backend health
        if ($health.ollama_reachable) {
            $script:svcRows.ollama.Circle.BackColor = $GREEN
            $script:svcRows.ollama.Status.Text = "Running"
            $script:svcRows.ollama.Status.ForeColor = $GREEN
        } else {
            $script:svcRows.ollama.Circle.BackColor = $RED
            $script:svcRows.ollama.Status.Text = "Offline"
            $script:svcRows.ollama.Status.ForeColor = $RED
        }

        # ChromaDB status
        if ($health.chroma_ready) {
            $script:svcRows.chromadb.Circle.BackColor = $GREEN
            $script:svcRows.chromadb.Status.Text = "Ready"
            $script:svcRows.chromadb.Status.ForeColor = $GREEN
        } else {
            $script:svcRows.chromadb.Circle.BackColor = $AMBER
            $script:svcRows.chromadb.Status.Text = "Not ready"
            $script:svcRows.chromadb.Status.ForeColor = $AMBER
        }

        # Knowledge base doc counts
        if ($health.chroma_doc_counts) {
            $parts = @()
            foreach ($key in $health.chroma_doc_counts.PSObject.Properties) {
                $parts += "$($key.Name): $($key.Value) docs"
            }
            if ($parts.Count -gt 0) {
                $kbLabel.Text = $parts -join "   |   "
                $kbLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 55, 65, 81)
            } else {
                $kbLabel.Text = "No collections found"
                $kbLabel.ForeColor = $GRAY
            }
        } else {
            $kbLabel.Text = "No data available"
            $kbLabel.ForeColor = $GRAY
        }
    } else {
        # Backend is down
        $script:svcRows.backend.Circle.BackColor = $RED
        $script:svcRows.backend.Status.Text = "Offline"
        $script:svcRows.backend.Status.ForeColor = $RED

        # Check Ollama independently when backend is down
        if (Test-Ollama) {
            $script:svcRows.ollama.Circle.BackColor = $GREEN
            $script:svcRows.ollama.Status.Text = "Running"
            $script:svcRows.ollama.Status.ForeColor = $GREEN
        } elseif (Test-Port 11434) {
            $script:svcRows.ollama.Circle.BackColor = $AMBER
            $script:svcRows.ollama.Status.Text = "Port open (not responding)"
            $script:svcRows.ollama.Status.ForeColor = $AMBER
        } else {
            $script:svcRows.ollama.Circle.BackColor = $RED
            $script:svcRows.ollama.Status.Text = "Offline"
            $script:svcRows.ollama.Status.ForeColor = $RED
        }

        # ChromaDB unknown when backend is down
        $script:svcRows.chromadb.Circle.BackColor = $GRAY
        $script:svcRows.chromadb.Status.Text = "Unknown (backend offline)"
        $script:svcRows.chromadb.Status.ForeColor = $GRAY

        $kbLabel.Text = "Backend offline"
        $kbLabel.ForeColor = $GRAY
        $headerVersion.Text = ""
    }

    # Repaint status circles
    foreach ($row in $script:svcRows.Values) {
        $row.Circle.Invalidate()
    }
}

# Manual refresh
$refreshBtn.Add_Click({
    Disable-Briefly $refreshBtn 2000
    Update-Status
})

# Auto-refresh timer
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.Add_Tick({ Update-Status })
$timer.Start()

# Initial status check
Update-Status

# --- Form close cleanup ---
$form.Add_FormClosing({
    $timer.Stop()
    $timer.Dispose()
})

# --- Run ---
try {
    [System.Windows.Forms.Application]::Run($form)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
