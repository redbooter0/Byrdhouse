# backup-nightly.ps1 — the BYRD-VAULT job (Blueprint v2 §1.4 Action 7).
# SQLite .backup (safe while WAL is live) + robocopy mirror of the archive.
# One dead SSD must never erase the memory system.
#
#   backup-nightly.ps1              run a backup now
#   backup-nightly.ps1 -Install    register a daily 03:30 scheduled task (admin)
#Requires -Version 5.1
param([switch]$Install)

$root = $env:BYRDHOUSE_ROOT
if (-not $root) { Write-Error 'BYRDHOUSE_ROOT not set.'; exit 2 }

if ($Install) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\backup-nightly.ps1`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 3:30am
    Register-ScheduledTask -TaskName 'ByrdHouse-Backup' -Action $action -Trigger $trigger `
        -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force | Out-Null
    Write-Host "Registered 'ByrdHouse-Backup' — daily 03:30." -ForegroundColor Green
    exit 0
}

$cfg = Get-Content (Join-Path $root 'byrdhouse.config.json') -Raw | ConvertFrom-Json
$dest = $cfg.backup.dest
if (-not $dest -or $dest -like 'CHANGE_ME*') { Write-Error 'Set backup.dest in byrdhouse.config.json first.'; exit 2 }
$dest = Join-Path $dest $env:COMPUTERNAME
New-Item -ItemType Directory -Path $dest -Force | Out-Null
$log = Join-Path $root ("logs\backup_{0:yyyyMMdd}.log" -f (Get-Date))

# 1. Live-safe SQLite backups (python stdlib, works on WAL databases)
$dbDest = Join-Path $dest 'db'
New-Item -ItemType Directory -Path $dbDest -Force | Out-Null
Get-ChildItem (Join-Path $root 'db') -Filter *.db -ErrorAction SilentlyContinue | ForEach-Object {
    $out = Join-Path $dbDest $_.Name
    python -c "import sqlite3; s=sqlite3.connect(r'$($_.FullName)'); d=sqlite3.connect(r'$out'); s.backup(d); d.close(); s.close()"
    Write-Host "  db backed up: $($_.Name)"
}

# 2. Mirror the folders that cannot be regenerated
foreach ($d in 'artifacts','recipes','docs','workflows') {
    $src = Join-Path $root $d
    if (Test-Path $src) {
        robocopy $src (Join-Path $dest $d) /MIR /R:2 /W:5 /NP /LOG+:$log | Out-Null
        Write-Host "  mirrored $d\ (robocopy exit $LASTEXITCODE)"
    }
}
Copy-Item (Join-Path $root 'byrdhouse.config.json') $dest -Force

$stamp = Get-Date -Format 'o'
Set-Content (Join-Path $dest 'LAST_BACKUP.txt') $stamp
Write-Host "Backup complete → $dest ($stamp)" -ForegroundColor Green
