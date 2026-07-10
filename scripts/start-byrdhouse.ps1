# start-byrdhouse.ps1 — the ONE command per machine (Blueprint v2, U0 deliverable).
# On BYRD-GAMING: brings up LM Studio's server + operator model and ComfyUI,
# then runs byrd-status. On BYRD-MINI it just skips what isn't installed.
# Cold-reboot test: run this, read the green report, trust the machine.
#Requires -Version 5.1
param([int]$ComfyTimeoutSec = 180)

$ErrorActionPreference = 'Continue'
$root = $env:BYRDHOUSE_ROOT
if (-not $root) { Write-Error 'BYRDHOUSE_ROOT not set — run setup-gaming.ps1 first.'; exit 2 }
$cfg = Get-Content (Join-Path $root 'byrdhouse.config.json') -Raw | ConvertFrom-Json

function Test-Http([string]$Url) {
    try { $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5; $true } catch { $false }
}

Write-Host "`nByrdHouse startup — $env:COMPUTERNAME`n" -ForegroundColor Cyan

# ── LM Studio: server + operator model ───────────────────────────────────────
if (Get-Command lms -ErrorAction SilentlyContinue) {
    Write-Host '[lmstudio] starting server...'
    lms server start 2>$null
    $model = $cfg.gpu.operator_model
    if ($model -and $model -notlike 'CHANGE_ME*') {
        $loaded = (lms ps 2>$null) -join ' '
        if ($loaded -notlike "*$model*") {
            Write-Host "[lmstudio] loading operator model $model ..."
            lms load $model
        } else {
            Write-Host "[lmstudio] operator model already loaded"
        }
    } else {
        Write-Host '[lmstudio] gpu.operator_model not set in config — skipping model load' -ForegroundColor Yellow
    }
} else {
    Write-Host '[lmstudio] lms CLI not found — skipping (fine on BYRD-MINI)' -ForegroundColor Yellow
}

# ── ComfyUI ──────────────────────────────────────────────────────────────────
$comfyUrl = $cfg.services.comfyui
if (Test-Http "$comfyUrl/system_stats") {
    Write-Host "[comfyui] already up at $comfyUrl"
} else {
    $dir = $cfg.startup.comfyui_dir
    $cmd = $cfg.startup.comfyui_cmd
    if ($dir -and $dir -notlike 'CHANGE_ME*' -and (Test-Path $dir)) {
        Write-Host "[comfyui] launching $cmd in $dir ..."
        Start-Process -FilePath (Join-Path $dir $cmd) -WorkingDirectory $dir -WindowStyle Minimized
        $deadline = (Get-Date).AddSeconds($ComfyTimeoutSec)
        while ((Get-Date) -lt $deadline) {
            if (Test-Http "$comfyUrl/system_stats") { Write-Host '[comfyui] up.'; break }
            Start-Sleep -Seconds 5
        }
        if (-not (Test-Http "$comfyUrl/system_stats")) {
            Write-Host "[comfyui] still not answering after ${ComfyTimeoutSec}s — check its window" -ForegroundColor Red
        }
    } else {
        Write-Host '[comfyui] startup.comfyui_dir not configured/found — skipping (fine on BYRD-MINI)' -ForegroundColor Yellow
    }
}

# ── Router (the belt API) ────────────────────────────────────────────────────
$routerUrl = $cfg.services.router
if ($cfg.startup.run_router) {
    if (Test-Http "$routerUrl/health") {
        Write-Host "[router] already up at $routerUrl"
    } else {
        Write-Host '[router] starting...'
        Start-Process python -ArgumentList "`"$root\router\router.py`"" -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline -and -not (Test-Http "$routerUrl/health")) { Start-Sleep 2 }
        if (Test-Http "$routerUrl/health") { Write-Host "[router] up — dashboard at $routerUrl" }
        else { Write-Host '[router] failed to answer — run manually to see the error: python router\router.py' -ForegroundColor Red }
    }
}

# ── Worker daemon ────────────────────────────────────────────────────────────
if ($cfg.startup.run_worker) {
    $running = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -like '*worker.py*' }
    if ($running) {
        Write-Host '[worker] already running'
    } else {
        Write-Host '[worker] starting...'
        Start-Process python -ArgumentList "`"$root\scripts\worker.py`"" -WindowStyle Hidden
    }
}

# ── Status report ────────────────────────────────────────────────────────────
& (Join-Path $root 'scripts\byrd-status.ps1')
