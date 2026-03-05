# logging-utils.ps1 - Shared logging utilities for AI Helpdesk Assistant installer scripts
#
# Usage in each installer script:
#   . (Join-Path $PSScriptRoot "logging-utils.ps1")
#   $logFile = Initialize-LogFile -AppDir $AppDir -LogName "my-script"
#   Write-Log "Starting..." "INFO"
#   Write-Log "Something wrong" "WARN"
#   Write-Log "Fatal problem" "ERROR"
#
# Log format: [yyyy-MM-dd HH:mm:ss] [LEVEL] Message
# Log location: {AppDir}\logs\{LogName}.log  (static filename; each run appends a blank
#               separator line so multiple runs remain distinguishable in the same file)

function Initialize-LogFile {
    <#
    .SYNOPSIS
        Creates the logs directory under AppDir (if needed) and returns the full path to the
        log file for LogName.  Writes a blank separator line so repeated runs are visually
        separated when tailing the file.
    .PARAMETER AppDir
        Root install directory (parent of logs\).
    .PARAMETER LogName
        Basename for the log file, e.g. "post-install" → logs\post-install.log
    .OUTPUTS
        [string] Full path to the log file.
    #>
    param(
        [Parameter(Mandatory)][string]$AppDir,
        [Parameter(Mandatory)][string]$LogName
    )
    $logsDir = Join-Path $AppDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
    $path = Join-Path $logsDir "$LogName.log"
    # Blank separator makes successive runs easy to distinguish in the same file
    Add-Content -Path $path -Value "" -Encoding UTF8
    return $path
}

function Write-Log {
    <#
    .SYNOPSIS
        Writes a timestamped, levelled entry to $logFile (caller scope) and to the host.
    .PARAMETER Message
        The log message text.
    .PARAMETER Level
        Severity: INFO (default), WARN, or ERROR.
    .NOTES
        Reads $logFile from the caller's scope — callers must set $logFile before calling
        Write-Log (typically via Initialize-LogFile).
    #>
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $ts    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] [$Level] $Message"
    Add-Content -Path $logFile -Value $entry -Encoding UTF8
    Write-Host $Message
}

function Initialize-ChainLog {
    <#
    .SYNOPSIS
        Returns the path to the shared install-chain.log file (creates logs dir if needed).
        All installer scripts write to this single file so the full install chain outcome
        is visible in one place.
    .PARAMETER AppDir
        Root install directory (parent of logs\).
    .OUTPUTS
        [string] Full path to install-chain.log
    #>
    param([Parameter(Mandatory)][string]$AppDir)
    $logsDir = Join-Path $AppDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
    return Join-Path $logsDir "install-chain.log"
}

function Write-ChainLog {
    <#
    .SYNOPSIS
        Appends a chain-level outcome record to $chainLogFile (caller scope).
        Used to log STARTED / SUCCESS / FAILED / SKIPPED events from each installer
        script into a single aggregated install-chain.log for the full install chain.
    .PARAMETER ScriptName
        Short name of the calling script, e.g. "post-install.ps1".
    .PARAMETER Message
        Outcome message, e.g. "STARTED", "SUCCESS", "FAILED - <reason>",
        "SKIPPED - online-only build".
    .NOTES
        Reads $chainLogFile from the caller's scope — callers must call
        Initialize-ChainLog and store the result in $chainLogFile before using
        Write-ChainLog.
    #>
    param(
        [string]$ScriptName,
        [string]$Message
    )
    $ts    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] [CHAIN] [$ScriptName] $Message"
    Add-Content -Path $chainLogFile -Value $entry -Encoding UTF8
}
