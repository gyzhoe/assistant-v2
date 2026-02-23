# tray-monitor.ps1 — System tray icon showing backend status
# Polls http://localhost:8765/health every 5 seconds and updates the tray icon.
# Right-click menu provides Start/Stop/Health Check/Exit controls.

$AppDir = Split-Path -Parent $PSScriptRoot

# --- Single-instance guard using a named mutex ---
$mutex = New-Object System.Threading.Mutex($false, "Global\AIHelpdeskTrayMonitor")
if (-not $mutex.WaitOne(0, $false)) {
    # Another instance is already running
    $mutex.Dispose()
    return
}

# --- Hide the console window ---
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$consoleHwnd = [Win32]::GetConsoleWindow()
if ($consoleHwnd -ne [IntPtr]::Zero) {
    [Win32]::ShowWindow($consoleHwnd, 0) | Out-Null  # 0 = SW_HIDE
}

# --- Load WinForms and Drawing ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- Create colored circle icons ---
function New-CircleIcon([System.Drawing.Color]$color) {
    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)
    $brush = New-Object System.Drawing.SolidBrush($color)
    $g.FillEllipse($brush, 1, 1, 14, 14)
    # Add a subtle dark border for visibility on light taskbars
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(80, 0, 0, 0), 1)
    $g.DrawEllipse($pen, 1, 1, 13, 13)
    $pen.Dispose()
    $brush.Dispose()
    $g.Dispose()
    $icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
    return $icon
}

$iconGreen  = New-CircleIcon ([System.Drawing.Color]::FromArgb(255, 16, 185, 129))   # green
$iconYellow = New-CircleIcon ([System.Drawing.Color]::FromArgb(255, 245, 158, 11))   # amber
$iconRed    = New-CircleIcon ([System.Drawing.Color]::FromArgb(255, 239, 68, 68))    # red
$iconGray   = New-CircleIcon ([System.Drawing.Color]::FromArgb(255, 156, 163, 175))  # gray (starting)

# --- Build the NotifyIcon ---
$trayIcon = New-Object System.Windows.Forms.NotifyIcon
$trayIcon.Icon = $iconGray
$trayIcon.Text = "AI Helpdesk: Starting..."
$trayIcon.Visible = $true

# --- Context menu ---
$menu = New-Object System.Windows.Forms.ContextMenuStrip

$miStart = New-Object System.Windows.Forms.ToolStripMenuItem("Start Backend")
$miStart.Add_Click({
    $script = Join-Path $AppDir "scripts\start-backend.ps1"
    Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" -WindowStyle Hidden
})

$miStop = New-Object System.Windows.Forms.ToolStripMenuItem("Stop Backend")
$miStop.Add_Click({
    $script = Join-Path $AppDir "scripts\stop-backend.ps1"
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$script`" -NonInteractive" -WindowStyle Hidden
})

$miHealth = New-Object System.Windows.Forms.ToolStripMenuItem("Health Check")
$miHealth.Add_Click({
    $script = Join-Path $AppDir "scripts\check-health.ps1"
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$script`""
})

$miFolder = New-Object System.Windows.Forms.ToolStripMenuItem("Open Extension Folder")
$miFolder.Add_Click({
    $extDir = Join-Path $AppDir "extension"
    Start-Process explorer.exe -ArgumentList $extDir
})

$miSep = New-Object System.Windows.Forms.ToolStripSeparator

$miExit = New-Object System.Windows.Forms.ToolStripMenuItem("Exit")
$miExit.Add_Click({
    $script:exitRequested = $true
    $timer.Stop()
    $trayIcon.Visible = $false
    $trayIcon.Dispose()
    [System.Windows.Forms.Application]::Exit()
})

$menu.Items.AddRange(@($miStart, $miStop, $miHealth, $miFolder, $miSep, $miExit))
$trayIcon.ContextMenuStrip = $menu

# --- Health polling timer ---
$script:exitRequested = $false
$webClient = New-Object System.Net.WebClient

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000  # 5 seconds

$timer.Add_Tick({
    if ($script:exitRequested) { return }
    try {
        $json = $webClient.DownloadString("http://localhost:8765/health")
        $data = $json | ConvertFrom-Json
        if ($data.ollama_reachable) {
            $trayIcon.Icon = $iconGreen
            $trayIcon.Text = "AI Helpdesk: Running"
        } else {
            $trayIcon.Icon = $iconYellow
            $trayIcon.Text = "AI Helpdesk: Running (Ollama offline)"
        }
    } catch {
        $trayIcon.Icon = $iconRed
        $trayIcon.Text = "AI Helpdesk: Backend offline"
    }
})

$timer.Start()

# --- Run the message loop (blocks until Application.Exit) ---
try {
    [System.Windows.Forms.Application]::Run()
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
