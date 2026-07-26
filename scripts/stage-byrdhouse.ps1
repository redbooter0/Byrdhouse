# stage-byrdhouse.ps1 — run the WHOLE belt from a branch in an ISOLATED staging
# copy, so new lanes are proven on real hardware BEFORE they are routed into
# production. Nothing in the production root (env BYRDHOUSE_ROOT) is touched:
# staging has its own clone, config, SQLite db, artifact archive and router
# port. It shares only the two live services every lane must ultimately use —
# ComfyUI and LM Studio — read from the PRODUCTION config, never hardcoded.
#
#   powershell -ExecutionPolicy Bypass -File scripts\stage-byrdhouse.ps1
#     [-Branch claude/comfyui-ollama-describer-ppk9bc]  branch to stage (PR #28)
#     [-StagingRoot E:\ByrdHouse-staging]               default: sibling of prod root
#     [-RouterPort 8788]                                 staging dashboard port
#     [-Update]                                          git pull the branch, keep db
#
# Then open  http://localhost:8788  (or http://byrd-gaming:8788 from the iPad)
# and drive images AND video from the staging web app. When a lane is proven,
# routing it into production is just: merge the PR, git pull the production
# root, restart start-byrdhouse. Delete the staging folder any time.
#
# ONE GPU RULE: the staging worker runs the same IMAGE/VIDEO/OPERATOR mode
# rituals against the same RTX 3070 — do not run the production worker at the
# same time or the two will fight over LM Studio and VRAM. This script checks
# and warns. Windows PowerShell 5.1, no dependencies.
#Requires -Version 5.1
param(
    [string]$Branch = "claude/comfyui-ollama-describer-ppk9bc",
    [string]$StagingRoot = "",
    [int]$RouterPort = 8788,
    [switch]$Update
)
$ErrorActionPreference = "Stop"

$prod = $env:BYRDHOUSE_ROOT
if (-not $prod -or -not (Test-Path (Join-Path $prod "byrdhouse.config.json"))) {
    Write-Host "BYRDHOUSE_ROOT is not set or has no byrdhouse.config.json — run setup first." -ForegroundColor Red
    exit 1
}
if (-not $StagingRoot) {
    $StagingRoot = Join-Path (Split-Path $prod -Parent) ((Split-Path $prod -Leaf) + "-staging")
}

# ── 1. clone or update the branch ────────────────────────────────────────────
$repoUrl = (git -C $prod remote get-url origin 2>$null)
if (-not $repoUrl) { $repoUrl = "https://github.com/redbooter0/Byrdhouse.git" }
if (-not (Test-Path (Join-Path $StagingRoot ".git"))) {
    Write-Host "Cloning $Branch into $StagingRoot ..." -ForegroundColor Cyan
    git clone --branch $Branch --single-branch $repoUrl $StagingRoot
} else {
    Write-Host "Updating staging clone ($Branch) ..." -ForegroundColor Cyan
    git -C $StagingRoot fetch origin $Branch
    git -C $StagingRoot checkout $Branch
    git -C $StagingRoot pull origin $Branch
}

# ── 2. staging config: production services, isolated router/db ───────────────
$cfg = Get-Content (Join-Path $prod "byrdhouse.config.json") -Raw | ConvertFrom-Json
$cfg.services.router = "http://localhost:$RouterPort"
if ($cfg.startup) {
    $cfg.startup.run_router = $true
    $cfg.startup.run_worker = $true
}
$cfgPath = Join-Path $StagingRoot "byrdhouse.config.json"
$cfg | ConvertTo-Json -Depth 12 | Set-Content -Path $cfgPath -Encoding UTF8
Write-Host "Staging config written (router :$RouterPort; ComfyUI $($cfg.services.comfyui); LM Studio $($cfg.services.lmstudio))"

# Keep the founder's identity available in staging without duplicating photos:
# profile references are gitignored, so copy them from production once.
$prodRefs = Join-Path $prod "profiles\me\references"
$stagRefs = Join-Path $StagingRoot "profiles\me\references"
if ((Test-Path $prodRefs) -and -not (Test-Path (Join-Path $stagRefs "me_photo_04.jpg"))) {
    Write-Host "Copying profile reference photos into staging (local only, gitignored)..."
    Copy-Item -Path (Join-Path $prodRefs "*") -Destination $stagRefs -Recurse -Force -ErrorAction SilentlyContinue
}

# ── 3. one-GPU safety check ──────────────────────────────────────────────────
$prodRouter = $null
try { $prodRouter = ([uri]$((Get-Content (Join-Path $prod "byrdhouse.config.json") -Raw | ConvertFrom-Json).services.router)) } catch {}
$prodWorker = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape((Join-Path $prod "scripts\worker.py")) }
if ($prodWorker) {
    Write-Host "⚠ The PRODUCTION worker is running (PID $($prodWorker.ProcessId))." -ForegroundColor Yellow
    Write-Host "  One RTX 3070 = one worker. Stop it before staging tests:" -ForegroundColor Yellow
    Write-Host "    Stop-Process -Id $($prodWorker.ProcessId)" -ForegroundColor Yellow
}

# ── 4. launch the staging belt (separate windows, own root) ──────────────────
$env:BYRDHOUSE_ROOT = $StagingRoot
Write-Host "Starting staging router (:$RouterPort) and worker from $StagingRoot ..." -ForegroundColor Cyan
Start-Process python -ArgumentList (Join-Path $StagingRoot "router\router.py") `
    -WorkingDirectory $StagingRoot
Start-Sleep -Seconds 2
Start-Process python -ArgumentList (Join-Path $StagingRoot "scripts\worker.py") `
    -WorkingDirectory $StagingRoot

Write-Host ""
Write-Host "STAGING BELT UP — nothing in production was touched." -ForegroundColor Green
Write-Host "  Dashboard:  http://localhost:$RouterPort   (iPad: http://byrd-gaming:$RouterPort)"
Write-Host "  Prove the lanes in this order (all from the web app, no ComfyUI clicks):"
Write-Host "   1. Create -> identity_sdxl_t2i v2 -> a likeness image lands in Library"
Write-Host "   2. Library -> approve it"
Write-Host "   3. Library -> animate (on the approved card) -> a playable clip appears"
Write-Host "  When it works how you want: merge the PR, git pull production, restart."
