# byrdcoder-preflight.ps1 — ByrdCoder Local V0 readiness check (read-only).
# Verifies the Phase 1 bridge contract on this machine: LM Studio reachable at
# the CONFIGURED url (byrdhouse.config.json services.lmstudio — zero hardcoded
# hosts), chat models discovered with embeddings excluded, context/capability
# metadata reported, Qwen/Qwopus coder models present, opencode CLI installed,
# pinned plugin recorded, generated machine config isolated from git.
# Writes logs\byrdcoder\preflight_<stamp>.json. Exit 0 = ready, 1 = FAILs.
#Requires -Version 5.1
param([switch]$Quiet)

$ErrorActionPreference = 'SilentlyContinue'
$report = [ordered]@{ generated = (Get-Date -Format s); computer = $env:COMPUTERNAME; checks = @() }
$script:failCount = 0

function Check([string]$Name, [string]$State, [string]$Detail) {
    $report.checks += [ordered]@{ name = $Name; state = $State; detail = $Detail }
    if ($State -eq 'fail') { $script:failCount++ }
    if (-not $Quiet) {
        $color = @{ ok = 'Green'; fail = 'Red'; info = 'Yellow' }[$State]
        Write-Host ("  [{0,-4}] {1} — {2}" -f $State.ToUpper(), $Name, $Detail) -ForegroundColor $color
    }
}

if (-not $Quiet) { Write-Host "`nByrdCoder preflight — $env:COMPUTERNAME — $(Get-Date -Format s)`n" -ForegroundColor Cyan }

# ── Root + config ────────────────────────────────────────────────────────────
$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) {
    Check 'byrdhouse_root' 'fail' "BYRDHOUSE_ROOT missing/invalid: '$root'"
    exit 1
}
Check 'byrdhouse_root' 'ok' $root
$cfg = Get-Content (Join-Path $root 'byrdhouse.config.json') -Raw | ConvertFrom-Json
if (-not $cfg -or -not $cfg.services.lmstudio) {
    Check 'config_lmstudio' 'fail' 'byrdhouse.config.json missing services.lmstudio'
    exit 1
}
Check 'config_lmstudio' 'ok' $cfg.services.lmstudio

# ── Repo kit files ───────────────────────────────────────────────────────────
$example = Join-Path $root 'configs\byrdcoder\opencode.example.json'
if (Test-Path $example) {
    $ex = Get-Content $example -Raw | ConvertFrom-Json
    Check 'example_config' 'ok' $example
    $pin = ($ex.plugin | Where-Object { $_ -like 'opencode-lmstudio@*' }) -join ''
    if ($pin) { Check 'bridge_pin' 'ok' $pin } else { Check 'bridge_pin' 'fail' 'opencode-lmstudio plugin pin missing from example config' }
    $profiles = @($ex.agent.PSObject.Properties.Name)
    Check 'profiles' ($(if ($profiles.Count -ge 7) { 'ok' } else { 'fail' })) ("agents: " + ($profiles -join ', '))
} else {
    Check 'example_config' 'fail' "missing $example — pull the repo kit"
}

# ── opencode CLI ─────────────────────────────────────────────────────────────
$oc = Get-Command opencode -ErrorAction SilentlyContinue
if ($oc) {
    $ver = (& opencode --version 2>&1) -join ' '
    Check 'opencode_cli' 'ok' ("{0} ({1})" -f $ver, $oc.Source)
} else {
    Check 'opencode_cli' 'fail' 'opencode not on PATH — install per docs/BYRDCODER_LOCAL.md (record the version in the doc after install)'
}

# ── Generated machine config isolation ───────────────────────────────────────
$machineCfg = Join-Path $root 'LLM\byrdcoder\opencode.json'
if (Test-Path $machineCfg) {
    $mc = Get-Content $machineCfg -Raw
    if ($mc -match '\{\{LMSTUDIO_URL\}\}') {
        Check 'machine_config' 'fail' 'placeholder not substituted — rerun start-byrdcoder.ps1 -Regen'
    } else {
        Check 'machine_config' 'ok' $machineCfg
    }
    Push-Location $root
    $ignored = (& git check-ignore 'LLM/byrdcoder/opencode.json' 2>$null)
    Pop-Location
    Check 'machine_config_gitignored' ($(if ($ignored) { 'ok' } else { 'fail' })) 'generated config must never enter git'
} else {
    Check 'machine_config' 'info' 'not generated yet — start-byrdcoder.ps1 creates it on first run'
}

# ── LM Studio discovery (the Phase 1 verification) ───────────────────────────
$disc = $null
$raw = (& python (Join-Path $root 'scripts\byrdcoder_models.py') --root $root --json 2>$null) -join "`n"
if ($raw) { try { $disc = $raw | ConvertFrom-Json } catch { } }
if ($disc -and $disc.endpoint) {
    $models = @($disc.models)
    Check 'lmstudio_reachable' 'ok' ("{0} via {1}" -f $disc.lmstudio, $disc.endpoint)
    Check 'chat_models' ($(if ($models.Count -gt 0) { 'ok' } else { 'fail' })) ("{0} chat model(s), embeddings excluded" -f $models.Count)
    $withCtx = @($models | Where-Object { $_.context })
    Check 'context_reported' ($(if ($withCtx.Count -gt 0 -or $disc.endpoint -eq '/v1/models') { 'ok' } else { 'fail' })) ("{0}/{1} models report context (native metadata needs the LM Studio REST API)" -f $withCtx.Count, $models.Count)
    $toolCap = @($models | Where-Object { $_.tool_capable })
    $vision  = @($models | Where-Object { $_.vision })
    Check 'capabilities' 'info' ("tool-capable: {0}; vision: {1}" -f $toolCap.Count, $vision.Count)
    $coder = @($models | Where-Object { $_.coder_hint })
    Check 'coder_models' ($(if ($coder.Count -gt 0) { 'ok' } else { 'fail' })) ("qwen/qwopus/coder-family: " + $(if ($coder.Count) { ($coder | ForEach-Object { $_.id }) -join ', ' } else { 'NONE found — load the coder model in LM Studio' }))
    $report.models = $models
} else {
    Check 'lmstudio_reachable' 'fail' ("no response from {0} — is LM Studio running with the local server enabled?" -f $cfg.services.lmstudio)
}

# ── Write report ─────────────────────────────────────────────────────────────
$outDir = Join-Path $root 'logs\byrdcoder'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$outFile = Join-Path $outDir ("preflight_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".json")
$report | ConvertTo-Json -Depth 8 | Set-Content $outFile -Encoding UTF8
if (-not $Quiet) { Write-Host "`nReport: $outFile" -ForegroundColor Cyan }

if ($script:failCount -gt 0) {
    if (-not $Quiet) { Write-Host "$($script:failCount) FAIL check(s) — fix before benchmarking (docs/BYRDCODER_LOCAL.md)" -ForegroundColor Red }
    exit 1
}
if (-not $Quiet) { Write-Host 'ByrdCoder preflight clean.' -ForegroundColor Green }
exit 0
