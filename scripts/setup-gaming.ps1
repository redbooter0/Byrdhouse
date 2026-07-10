# setup-gaming.ps1 — BYRD-GAMING bootstrap (Blueprint v2 §8 directory map, U0 kit)
# Run from a clone of the Byrdhouse repo, in an elevated-or-normal PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\setup-gaming.ps1
# Idempotent: safe to re-run. Never overwrites an existing config.
#Requires -Version 5.1
param([string]$Root = 'E:\ByrdHouse')

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent

Write-Host "`nByrdHouse gaming-PC setup → $Root`n" -ForegroundColor Cyan

# 1. Directory map (v2 §8)
$dirs = 'db','docs','recipes','workflows','projects','artifacts','inbox','cleaned','processed','logs','scripts','router','dashboard'
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
foreach ($d in 'scripts','docs','recipes','workflows','router','dashboard') {
    $src = Join-Path $repo $d
    if (Test-Path $src) {
        Copy-Item "$src\*" (Join-Path $Root $d) -Recurse -Force
        Write-Host "  synced $d\"
    }
}

# 4. BYRDHOUSE_ROOT env var (user scope; new terminals pick it up)
if ($env:BYRDHOUSE_ROOT -ne $Root) {
    setx BYRDHOUSE_ROOT $Root | Out-Null
    $env:BYRDHOUSE_ROOT = $Root
    Write-Host "  set BYRDHOUSE_ROOT=$Root (reopen other terminals to see it)"
}

# 5. Pillow — the kit's only pip dependency (thumbnail text compositor, v3.1 §3)
if (Get-Command python -ErrorAction SilentlyContinue) {
    python -c "import PIL" 2>$null
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
    @{ cmd = 'sqlite3';    why = 'memory drift check (MINI mainly)' }
)) {
    if (Get-Command $tool.cmd -ErrorAction SilentlyContinue) {
        Write-Host "  [ok]      $($tool.cmd)" -ForegroundColor Green
    } else {
        Write-Host "  [missing] $($tool.cmd) — needed for: $($tool.why)" -ForegroundColor Yellow
    }
}

# 7. First status report
Write-Host "`nRunning byrd-status...`n" -ForegroundColor Cyan
& (Join-Path $Root 'scripts\byrd-status.ps1')
