# setup_task_scheduler.ps1
#
# Creates a Windows Task Scheduler job that runs sync_closed_won.py every day at 7:00 AM.
#
# Run this script ONCE from PowerShell (as Administrator):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup_task_scheduler.ps1

$TaskName    = "Wildix Forecaster - Closed-Won Sync"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$SyncScript  = Join-Path $ScriptDir "sync_closed_won.py"
$LogPath     = Join-Path $ProjectRoot "data\sync_closed_won.log"

# Detect Python path (PowerShell 5 compatible)
$PyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($PyCmd) {
    $PythonExe = $PyCmd.Source
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCmd) {
        $PythonExe = $PythonCmd.Source
    } else {
        Write-Error "Python not found. Make sure 'py' or 'python' is on your PATH."
        exit 1
    }
}

Write-Host "Python found at: $PythonExe" -ForegroundColor Cyan
Write-Host "Script:          $SyncScript" -ForegroundColor Cyan
Write-Host "Project root:    $ProjectRoot" -ForegroundColor Cyan
Write-Host "Log file:        $LogPath"
Write-Host ""

# Build the task
$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-3.12 `"$SyncScript`"" `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At "07:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable $true

# Register (overwrites if already exists)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily sync of Closed-Won MRR from Wildix Partner Portal to Forecaster DB" `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Task registered successfully." -ForegroundColor Green
Write-Host "Runs daily at 7:00 AM (or next available time if PC was off)." -ForegroundColor Green
Write-Host "Log: $LogPath" -ForegroundColor Green
Write-Host ""
Write-Host "To run immediately:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
Write-Host ""
Write-Host "To remove:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
