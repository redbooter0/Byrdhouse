# byrd-status.ps1 v2 — ByrdHouse health report (Blueprint v2, §1.4 Action 2)
# Answers "is ByrdHouse healthy?" with one command.
# Console: green/yellow/red per check. Also writes machine-readable
# %BYRDHOUSE_ROOT%\status.json for the dashboard.
# Exit code: 0 = all green, 1 = yellow somewhere, 2 = red somewhere.
#Requires -Version 5.1
param([switch]$Quiet)

$ErrorActionPreference = 'SilentlyContinue'
$checks = New-Object System.Collections.ArrayList

function Add-Check([string]$Name, [string]$State, [string]$Detail) {
    [void]$checks.Add([pscustomobject]@{ name = $Name; state = $State; detail = $Detail })
    if (-not $Quiet) {
        $color = @{ green = 'Green'; yellow = 'Yellow'; red = 'Red' }[$State]
        Write-Host ("  [{0,-6}] {1} — {2}" -f $State.ToUpper(), $Name, $Detail) -ForegroundColor $color
    }
}

function Test-Http([string]$Url, [int]$TimeoutSec = 5) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch { return $false }
}

if (-not $Quiet) { Write-Host "`nByrdHouse status — $env:COMPUTERNAME — $(Get-Date -Format s)`n" }

# ── 1. Root + config ─────────────────────────────────────────────────────────
$root = $env:BYRDHOUSE_ROOT
if (-not $root) {
    Add-Check 'byrdhouse_root' 'red' 'BYRDHOUSE_ROOT env var not set. Run setup script or: setx BYRDHOUSE_ROOT "E:\ByrdHouse"'
    exit 2
}
if (-not (Test-Path $root)) {
    Add-Check 'byrdhouse_root' 'red' "BYRDHOUSE_ROOT points to missing folder: $root"
    exit 2
}
Add-Check 'byrdhouse_root' 'green' $root

$cfgPath = Join-Path $root 'byrdhouse.config.json'
$cfg = $null
if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    if ($cfg.auth.admin_token -like 'CHANGE_ME*') {
        Add-Check 'config' 'yellow' 'Loaded, but placeholders remain (admin_token etc.) — edit byrdhouse.config.json'
    } else {
        Add-Check 'config' 'green' 'byrdhouse.config.json loaded'
    }
} else {
    Add-Check 'config' 'red' "Missing $cfgPath — copy the template from the repo root"
}

# ── 2. Hosts resolvable (Tailscale MagicDNS) ─────────────────────────────────
if ($cfg) {
    foreach ($h in $cfg.hosts.PSObject.Properties) {
        if ($h.Value -eq $env:COMPUTERNAME) { continue }
        if (Test-Connection -ComputerName $h.Value -Count 1 -Quiet) {
            Add-Check "host_$($h.Name)" 'green' "$($h.Value) reachable"
        } else {
            $state = if ($h.Name -eq 'vault') { 'yellow' } else { 'red' }
            Add-Check "host_$($h.Name)" $state "$($h.Value) not reachable (Tailscale up on both ends?)"
        }
    }
}

# ── 3. Services ──────────────────────────────────────────────────────────────
if ($cfg) {
    $probes = @{
        comfyui  = '/system_stats'
        lmstudio = '/models'
        qdrant   = '/readyz'
        router   = '/health'
    }
    foreach ($s in $cfg.services.PSObject.Properties) {
        $url = $s.Value.TrimEnd('/') + $probes[$s.Name]
        if (Test-Http $url) {
            Add-Check "svc_$($s.Name)" 'green' "$url OK"
        } else {
            # Router doesn't exist until U3; ComfyUI may be intentionally cold in OPERATOR mode.
            $state = if ($s.Name -eq 'router') { 'yellow' } else { 'red' }
            Add-Check "svc_$($s.Name)" $state "$url unreachable"
        }
    }
}

# ── 4. Qdrant drift (SQLite rows vs Qdrant points) ──────────────────────────
if ($cfg -and $cfg.memory) {
    $m = $cfg.memory
    if ($m.sqlite_db -like '*CHANGE_ME*' -or $m.qdrant_collection -like '*CHANGE_ME*') {
        Add-Check 'memory_drift' 'yellow' 'Not configured — fill memory.* in config on BYRD-MINI'
    } elseif (-not (Test-Path $m.sqlite_db)) {
        Add-Check 'memory_drift' 'red' "SQLite db not found: $($m.sqlite_db)"
    } elseif (-not (Get-Command sqlite3 -ErrorAction SilentlyContinue)) {
        Add-Check 'memory_drift' 'yellow' 'sqlite3 CLI not on PATH — cannot count rows'
    } else {
        $rows = [int](sqlite3 $m.sqlite_db "SELECT COUNT(*) FROM $($m.sqlite_table);")
        $points = -1
        try {
            $resp = Invoke-RestMethod -Uri "$($cfg.services.qdrant)/collections/$($m.qdrant_collection)" -TimeoutSec 5
            $points = [int]$resp.result.points_count
        } catch {}
        if ($points -lt 0) {
            Add-Check 'memory_drift' 'red' "Qdrant collection '$($m.qdrant_collection)' unreadable"
        } elseif ([math]::Abs($rows - $points) -le 5) {
            Add-Check 'memory_drift' 'green' "SQLite $rows vs Qdrant $points — in sync"
        } else {
            Add-Check 'memory_drift' 'red' "DRIFT: SQLite $rows vs Qdrant $points — vector saves failing silently"
        }
    }
}

# ── 5. Disk free on the ByrdHouse drive ──────────────────────────────────────
$drive = (Get-Item $root).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB, 1)
if ($freeGB -lt 15)      { Add-Check 'disk' 'red'    "$($drive.Name): only ${freeGB}GB free" }
elseif ($freeGB -lt 50)  { Add-Check 'disk' 'yellow' "$($drive.Name): ${freeGB}GB free — plan cleanup/expansion" }
else                     { Add-Check 'disk' 'green'  "$($drive.Name): ${freeGB}GB free" }

# ── 6. GPU / VRAM (gaming PC only) ───────────────────────────────────────────
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $g = (nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader,nounits) -split ','
    Add-Check 'gpu' 'green' ("{0} — {1}MB / {2}MB VRAM used" -f $g[0].Trim(), $g[1].Trim(), $g[2].Trim())
} else {
    Add-Check 'gpu' 'yellow' 'nvidia-smi not found (expected on BYRD-MINI; a problem on BYRD-GAMING)'
}

# ── 7. MCP roster pings ──────────────────────────────────────────────────────
if ($cfg -and $cfg.mcp) {
    foreach ($srv in $cfg.mcp.PSObject.Properties) {
        if ($srv.Name -eq '_comment') { continue }
        $ping = $srv.Value.ping
        if (-not $ping) { continue }   # no ping URL configured -> skip silently
        if (Test-Http $ping) { Add-Check "mcp_$($srv.Name)" 'green' "$ping OK" }
        else                 { Add-Check "mcp_$($srv.Name)" 'red' "$ping unreachable" }
    }
}

# ── Report ───────────────────────────────────────────────────────────────────
$overall = 'green'
if ($checks | Where-Object state -eq 'yellow') { $overall = 'yellow' }
if ($checks | Where-Object state -eq 'red')    { $overall = 'red' }

$status = [pscustomobject]@{
    generated_at = (Get-Date -Format 'o')
    host         = $env:COMPUTERNAME
    overall      = $overall
    checks       = $checks
}
$status | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $root 'status.json') -Encoding UTF8

if (-not $Quiet) {
    $color = @{ green = 'Green'; yellow = 'Yellow'; red = 'Red' }[$overall]
    Write-Host "`nOVERALL: $($overall.ToUpper())  →  $root\status.json`n" -ForegroundColor $color
}
exit @{ green = 0; yellow = 1; red = 2 }[$overall]
