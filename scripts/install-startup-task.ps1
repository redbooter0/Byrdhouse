# install-startup-task.ps1 - register start-byrdhouse.ps1 as a logon task
# (Blueprint v2 U0: "one startup command per machine as a scheduled task").
# Run once from an ADMIN PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\install-startup-task.ps1
#Requires -Version 5.1
param([string]$TaskName = 'ByrdHouse-Startup')

$root = $env:BYRDHOUSE_ROOT
if (-not $root) { Write-Error 'BYRDHOUSE_ROOT not set - run setup first.'; exit 2 }
$script = Join-Path $root 'scripts\start-byrdhouse.ps1'
if (-not (Test-Path $script)) { Write-Error "Missing $script - run setup first."; exit 2 }

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
           -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = 'PT30S'   # let Tailscale/Docker settle first
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' - runs start-byrdhouse.ps1 30s after logon." -ForegroundColor Green
Write-Host "Test it now with:  Start-ScheduledTask -TaskName $TaskName"
