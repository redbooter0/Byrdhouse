# setup-mini.ps1 — BYRD-MINI bootstrap (nervous system: db, queue, dashboard, memory)
# Same as setup-gaming.ps1 but rooted at D:\ByrdHouse. The SQLite operations db
# (db\byrdhouse.db, Blueprint v2 §5) lives on THIS machine only.
#Requires -Version 5.1
param([string]$Root = 'D:\ByrdHouse')

& (Join-Path $PSScriptRoot 'setup-gaming.ps1') -Root $Root

Write-Host @"

MINI-specific reminders:
  - Fill in the memory.* section of $Root\byrdhouse.config.json on MINI:
    sqlite_db = D:\ByrdHouse\db\byrdhouse_memory.db
    sqlite_table = memories
    qdrant_collection = byrdhouse_memories
    so byrd-status can detect silent Qdrant drift — Blueprint v2 lists this as fragile risk #3.
  - Qdrant Docker container (byrdhouse-qdrant) should be set to restart=always.
"@ -ForegroundColor Cyan
