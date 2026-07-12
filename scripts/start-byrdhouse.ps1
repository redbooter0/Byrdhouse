# start-byrdhouse.ps1 - the ONE command per machine (Blueprint v2, U0 deliverable).
# On BYRD-GAMING: brings up LM Studio's server + operator model, ComfyUI, and worker.
# On BYRD-MINI: brings up the router/dashboard (and skips GPU services).
# Cold-reboot test: run this, read the green report, trust the machine.
#
# Usage:  cd D:\ByrdHouse   (or E:\ByrdHouse)
#         .\scripts\start-byrdhouse.ps1
#
# The script auto-detects BYRDHOUSE_ROOT from its own location if the env var
# is not set, so it works in a fresh terminal after setup or clone.
#Requires -Version 5.1
param([int]$ComfyTimeoutSec = 180)

$ErrorActionPreference = 'Continue'

# ── Resolve BYRDHOUSE_ROOT: env var > script location > bail ─────────────────
$root = $env:BYRDHOUSE_ROOT
if (-not $root) {
    $root = Split-Path $PSScriptRoot -Parent
    if (Test-Path (Join-Path $root 'byrdhouse.config.json')) {
        $env:BYRDHOUSE_ROOT = $root
        Write-Host "[init] BYRDHOUSE_ROOT not set — auto-detected from script location: $root" -ForegroundColor Yellow
        Write-Host "       To make permanent: setx BYRDHOUSE_ROOT `"$root`"" -ForegroundColor Yellow
    } else {
        Write-Error "BYRDHOUSE_ROOT not set and no config found at $root\byrdhouse.config.json. Run setup-gaming.ps1 or setup-mini.ps1 first."
        exit 2
    }
}

$cfgPath = Join-Path $root 'byrdhouse.config.json'
if (-not (Test-Path $cfgPath)) {
    Write-Error "Config not found at $cfgPath — run setup-gaming.ps1 or setup-mini.ps1 first."
    exit 2
}
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json

function Resolve-Python {
    $candidate = $cfg.startup.python_exe
    if ($candidate -and $candidate -notlike 'CHANGE_ME*' -and (Test-Path $candidate)) {
        return $candidate
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    return $null
}

function Test-Http([string]$Url) {
    try { $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5; $true } catch { $false }
}

Write-Host "`nByrdHouse startup - $env:COMPUTERNAME - root: $root`n" -ForegroundColor Cyan

# ── LM Studio (GAMING only — skips cleanly on MINI) ─────────────────────────
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
            Write-Host '[lmstudio] operator model already loaded'
        }
    } else {
        Write-Host '[lmstudio] gpu.operator_model not set in config - skipping model load' -ForegroundColor Yellow
    }
} else {
    Write-Host '[lmstudio] lms CLI not found - skipping (fine on BYRD-MINI)' -ForegroundColor Yellow
}

# ── ComfyUI (GAMING only — skips cleanly on MINI) ───────────────────────────
$comfyUrl = $cfg.services.comfyui
if (Test-Http "$comfyUrl/system_stats") {
    Write-Host "[comfyui] already up at $comfyUrl"
} else {
    $dir = $cfg.startup.comfyui_dir
    $cmd = $cfg.startup.comfyui_cmd
    if ($dir -and $dir -notlike 'CHANGE_ME*' -and (Test-Path $dir)) {
        Write-Host "[comfyui] launching $cmd in $dir ..."
        if ($cmd.ToLower().EndsWith('.ps1')) {
            Start-Process powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $dir $cmd)) -WorkingDirectory $dir -WindowStyle Minimized
        } else {
            Start-Process -FilePath (Join-Path $dir $cmd) -WorkingDirectory $dir -WindowStyle Minimized
        }
        $deadline = (Get-Date).AddSeconds($ComfyTimeoutSec)
        while ((Get-Date) -lt $deadline) {
            if (Test-Http "$comfyUrl/system_stats") { Write-Host '[comfyui] up.'; break }
            Start-Sleep -Seconds 5
        }
        if (-not (Test-Http "$comfyUrl/system_stats")) {
            Write-Host "[comfyui] still not answering after ${ComfyTimeoutSec}s - check its window" -ForegroundColor Red
        }
    } else {
        Write-Host '[comfyui] startup.comfyui_dir not configured/found - skipping (fine on BYRD-MINI)' -ForegroundColor Yellow
    }
}

# ── Router (MINI owns this; GAMING skips) ────────────────────────────────────
$routerUrl = $cfg.services.router
if ($cfg.startup.run_router) {
    if (Test-Http "$routerUrl/health") {
        Write-Host "[router] already up at $routerUrl"
    } else {
        $routerScript = Join-Path $root 'router\router.py'
        if (-not (Test-Path $routerScript)) {
            Write-Host "[router] router.py not found at $routerScript" -ForegroundColor Red
        } else {
            $python = Resolve-Python
            if (-not $python) {
                Write-Host '[router] python not found - skipping' -ForegroundColor Red
            } else {
                Write-Host "[router] starting ($python $routerScript)..."
                Start-Process $python -ArgumentList "`"$routerScript`"" -WindowStyle Hidden
                $deadline = (Get-Date).AddSeconds(30)
                while ((Get-Date) -lt $deadline -and -not (Test-Http "$routerUrl/health")) { Start-Sleep 2 }
                if (Test-Http "$routerUrl/health") {
                    Write-Host "[router] up - dashboard at $routerUrl" -ForegroundColor Green
                } else {
                    Write-Host "[router] failed to answer after 30s" -ForegroundColor Red
                    Write-Host "         Run manually to see the error: $python `"$routerScript`"" -ForegroundColor Red
                }
            }
        }
    }
} else {
    Write-Host "[router] run_router=false in config - skipping (this machine is not the router host)" -ForegroundColor Yellow
}

# ── Worker (GAMING owns this; MINI skips) ────────────────────────────────────
if ($cfg.startup.run_worker) {
    # Wait for the router to be reachable before starting the worker
    if (-not (Test-Http "$routerUrl/health")) {
        Write-Host "[worker] waiting for router at $routerUrl ..." -ForegroundColor Yellow
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline -and -not (Test-Http "$routerUrl/health")) { Start-Sleep 3 }
    }
    if (-not (Test-Http "$routerUrl/health")) {
        Write-Host "[worker] router still unreachable at $routerUrl — worker will retry on its own but may be slow" -ForegroundColor Red
        Write-Host "         Make sure BYRD-MINI is running: .\scripts\start-byrdhouse.ps1 on MINI first" -ForegroundColor Red
    }
    $running = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -like '*worker.py*' }
    if ($running) {
        Write-Host '[worker] already running'
    } else {
        $workerScript = Join-Path $root 'scripts\worker.py'
        if (-not (Test-Path $workerScript)) {
            Write-Host "[worker] worker.py not found at $workerScript" -ForegroundColor Red
        } else {
            $python = Resolve-Python
            if (-not $python) {
                Write-Host '[worker] python not found - skipping' -ForegroundColor Red
            } else {
                Write-Host "[worker] starting ($python $workerScript)..."
                Start-Process $python -ArgumentList "`"$workerScript`"" -WindowStyle Hidden
                Write-Host '[worker] launched in background' -ForegroundColor Green
            }
        }
    }
} else {
    Write-Host "[worker] run_worker=false in config - skipping (this machine does not run jobs)" -ForegroundColor Yellow
}

# ── Status report ────────────────────────────────────────────────────────────
$statusScript = Join-Path $root 'scripts\byrd-status.ps1'
if (Test-Path $statusScript) {
    & $statusScript
} else {
    Write-Host "[status] byrd-status.ps1 not found at $statusScript" -ForegroundColor Red
}
