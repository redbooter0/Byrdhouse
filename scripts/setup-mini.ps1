# setup-mini.ps1 — BYRD-MINI bootstrap (nervous system: db, queue, dashboard, memory)
# Same as setup-gaming.ps1 but rooted at D:\ByrdHouse and auto-sets run_router=true.
#
# Usage:  cd D:\ByrdHouse
#         .\scripts\setup-mini.ps1
#Requires -Version 5.1
param([string]$Root = 'D:\ByrdHouse')

& (Join-Path $PSScriptRoot 'setup-gaming.ps1') -Root $Root

# Auto-fix config for MINI: run_router=true, run_worker=false
$cfgPath = Join-Path $Root 'byrdhouse.config.json'
if (Test-Path $cfgPath) {
    $raw = Get-Content $cfgPath -Raw
    $cfg = $raw | ConvertFrom-Json
    $changed = $false
    if (-not $cfg.startup.run_router) {
        $raw = $raw -replace '"run_router"\s*:\s*false', '"run_router": true'
        $changed = $true
        Write-Host "  [fix] set run_router=true (MINI hosts the router)" -ForegroundColor Green
    }
    if ($cfg.startup.run_worker) {
        $raw = $raw -replace '"run_worker"\s*:\s*true', '"run_worker": false'
        $changed = $true
        Write-Host "  [fix] set run_worker=false (GAMING runs jobs, not MINI)" -ForegroundColor Green
    }
    if ($changed) {
        Set-Content $cfgPath $raw -Encoding UTF8
    }
}

Write-Host @"

MINI-specific reminders:
  - Fill in the memory.* section of $Root\byrdhouse.config.json on MINI:
    sqlite_db = D:\ByrdHouse\db\byrdhouse_memory.db
    sqlite_table = memories
    qdrant_collection = byrdhouse_memories
    so byrd-status can detect silent Qdrant drift — Blueprint v2 lists this as fragile risk #3.
  - Qdrant Docker container (byrdhouse-qdrant) should be set to restart=always.
"@ -ForegroundColor Cyan
