# Registers a daily Windows Task Scheduler job that runs newsAi at 07:00 local time.
# Usage (run from project root in elevated PowerShell):
#   .\scripts\install_schedule.ps1

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entry  = Join-Path $projectRoot "run_daily.py"

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Run: python -m venv .venv; .\.venv\Scripts\activate; pip install -e '.[dev]'"
}
if (-not (Test-Path $entry)) {
    throw "run_daily.py not found at $entry"
}

$taskName = "newsAi-daily"
$action   = New-ScheduledTaskAction -Execute $python -Argument "`"$entry`"" -WorkingDirectory $projectRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -RunOnlyIfNetworkAvailable

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "AI 投资晨读 daily generator"

Write-Host "Registered task '$taskName' to run daily at 07:00. Check with: Get-ScheduledTask -TaskName $taskName"
