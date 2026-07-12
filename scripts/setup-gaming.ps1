# setup-gaming.ps1 — BYRD-GAMING bootstrap (Blueprint v2 §8 directory map, U0 kit)
#
# TWO ways to use this repo on a machine:
#   A) Clone directly:  git clone https://github.com/redbooter0/Byrdhouse.git E:\ByrdHouse
#      Then run:        cd E:\ByrdHouse; .\scripts\setup-gaming.ps1
#   B) Run from a separate clone to copy kit files into the target root:
#      powershell -ExecutionPolicy Bypass -File scripts\setup-gaming.ps1
#
# Idempotent: safe to re-run. Never overwrites an existing config.
#Requires -Version 5.1
param([string]$Root = 'E:\ByrdHouse')

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent

Write-Host "`nByrdHouse gaming-PC setup → $Root`n" -ForegroundColor Cyan

# 1. Directory map (v2 §8)
$dirs = 'db','docs','recipes','workflows','projects','artifacts','inbox','cleaned','processed','logs','scripts','router','dashboard','goose'
foreach ($d in $dirs) {
    $p = Join-Path $Root $d
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null; Write-Host "  created $p" }
}

# 2. Config — copy template only if absent (never clobber a tuned config)
$cfgDest = Join-Path $Root 'byrdhouse.config.json'
if (-not (Test-Path $cfgDest)) {
    Copy-Item (Join-Path $repo 'byrdhouse.config.json') $cfgDest
    Write-Host "  installed config template → EDIT THE CHANGE_ME PLACEHOLDERS: $cfgDest" -ForegroundColor Yellow
} else {
    Write-Host "  config already present, left untouched: $cfgDest"
}

# 3. Kit files: scripts, docs, recipes (overwrite = repo is the source of truth for kit files)
foreach ($d in 'scripts','docs','recipes','workflows','router','dashboard','goose') {
    $src = Join-Path $repo $d
    if (Test-Path $src) {
        Copy-Item "$src\*" (Join-Path $Root $d) -Recurse -Force
        Write-Host "  synced $d\"
    }
}

# 4. BYRDHOUSE_ROOT env var (user scope; new terminals pick it up)
#    Also set in this session so scripts work immediately without reopening.
if ($env:BYRDHOUSE_ROOT -ne $Root) {
    setx BYRDHOUSE_ROOT $Root | Out-Null
    $env:BYRDHOUSE_ROOT = $Root
    Write-Host "  set BYRDHOUSE_ROOT=$Root (takes effect in new terminals; already set for this session)"
}

# 5. Pillow — the kit's only pip dependency (thumbnail text compositor, v3.1 §3)
if (Get-Command python -ErrorAction SilentlyContinue) {
    cmd /c "python -c ""import PIL"" >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  installing Pillow (thumbnail compositor)...'
        python -m pip install --quiet pillow
    } else { Write-Host '  [ok]      Pillow' -ForegroundColor Green }
} else {
    Write-Host '  [missing] python — install Python 3.10+ and re-run' -ForegroundColor Yellow
}

# 6. Tool presence report (informational — install what's missing)
foreach ($tool in @(
    @{ cmd = 'nvidia-smi'; why = 'GPU/VRAM checks and mode switching' },
    @{ cmd = 'lms';        why = 'LM Studio CLI — model load/unload for GPU modes' },
    @{ cmd = 'tailscale';  why = 'MagicDNS hostnames (byrd-gaming / byrd-mini)' },
    @{ cmd = 'sqlite3';    why = 'memory drift check (MINI mainly)' },
    @{ cmd = 'git';        why = 'pull latest kit from GitHub' }
)) {
    if (Get-Command $tool.cmd -ErrorAction SilentlyContinue) {
        Write-Host "  [ok]      $($tool.cmd)" -ForegroundColor Green
    } else {
        Write-Host "  [missing] $($tool.cmd) — needed for: $($tool.why)" -ForegroundColor Yellow
    }
}

# 7. Quick config sanity check
Write-Host "`nConfig check:" -ForegroundColor Cyan
$cfg = Get-Content $cfgDest -Raw | ConvertFrom-Json
$machine = $env:COMPUTERNAME
$issues = @()

if ($cfg.auth.admin_token -like 'CHANGE_ME*') {
    $issues += "  admin_token is still a placeholder — set a real token in $cfgDest"
}
if ($machine -like '*GAMING*' -or $machine -like '*BYRD-G*') {
    if (-not $cfg.startup.run_worker) {
        $issues += "  run_worker is false — GAMING should have run_worker=true"
    }
    if ($cfg.startup.run_router) {
        $issues += "  run_router is true — GAMING should have run_router=false (MINI hosts the router)"
    }
} elseif ($machine -like '*MINI*' -or $machine -like '*BYRD-M*') {
    if (-not $cfg.startup.run_router) {
        $issues += "  run_router is false — MINI should have run_router=true"
    }
    if ($cfg.startup.run_worker) {
        $issues += "  run_worker is true — MINI should have run_worker=false (GAMING runs jobs)"
    }
}
if ($issues.Count -eq 0) {
    Write-Host "  [ok] config looks correct for $machine" -ForegroundColor Green
} else {
    foreach ($i in $issues) { Write-Host $i -ForegroundColor Yellow }
    Write-Host "  Edit: $cfgDest" -ForegroundColor Yellow
}

# 8. First status report
Write-Host "`nRunning byrd-status...`n" -ForegroundColor Cyan
& (Join-Path $Root 'scripts\byrd-status.ps1')
