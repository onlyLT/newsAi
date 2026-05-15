# Registers ONE Windows Task Scheduler job per channel, at staggered times,
# to avoid B站 21566 风控 (frequent-post rate limit) when running multiple
# channels back-to-back.
#
# Tasks created:
#   newsAi-ai-invest    daily at 07:00  →  python run_daily.py --channel ai-invest
#   newsAi-cn-finance   daily at 19:00  →  python run_daily.py --channel cn-finance
#
# Usage (run from project root in ELEVATED PowerShell):
#   .\scripts\install_schedule.ps1
#
# To remove later:
#   Unregister-ScheduledTask -TaskName "newsAi-ai-invest"  -Confirm:$false
#   Unregister-ScheduledTask -TaskName "newsAi-cn-finance" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "newsAi-daily"      -Confirm:$false  # legacy

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$python      = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entry       = Join-Path $projectRoot "run_daily.py"

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Run: python -m venv .venv; .\.venv\Scripts\activate; pip install -e '.[dev]'"
}
if (-not (Test-Path $entry)) {
    throw "run_daily.py not found at $entry"
}

# Remove any prior single-task install (legacy "newsAi-daily")
if (Get-ScheduledTask -TaskName "newsAi-daily" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "newsAi-daily" -Confirm:$false
    Write-Host "Removed legacy task 'newsAi-daily'"
}

# Per-channel task config: id → trigger time
$channelSchedule = @(
    @{ Id = "ai-invest";  Time = "7:00am"  ; Description = "AI 投资晨读 daily generator (morning slot)" },
    @{ Id = "cn-finance"; Time = "7:00pm"  ; Description = "中国财经早报 daily generator (evening slot)" }
)

foreach ($ch in $channelSchedule) {
    $taskName    = "newsAi-$($ch.Id)"
    $arg         = "`"$entry`" --channel $($ch.Id)"
    $action      = New-ScheduledTaskAction -Execute $python -Argument $arg -WorkingDirectory $projectRoot
    $trigger     = New-ScheduledTaskTrigger -Daily -At $ch.Time
    $settings    = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -RunOnlyIfNetworkAvailable

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description $ch.Description | Out-Null
    Write-Host "Registered '$taskName' at $($ch.Time)"
}

Write-Host ""
Write-Host "Done. Verify with: Get-ScheduledTask -TaskName 'newsAi-*' | Get-ScheduledTaskInfo"
