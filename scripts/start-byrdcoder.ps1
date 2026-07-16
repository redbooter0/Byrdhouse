# start-byrdcoder.ps1 — the one command to launch the local coding agent
# (docs/BYRDCODER_LOCAL.md). Generates the isolated machine config on first
# run (example + real LM Studio URL from byrdhouse.config.json — the generated
# copy lives in LLM\byrdcoder\, gitignored), enforces the branch guard for
# byrd-build, then launches OpenCode with the chosen profile.
# Default profile is byrd-ask: every new session starts READ-ONLY.
#   start-byrdcoder.ps1                       # read-only Q&A on the repo
#   start-byrdcoder.ps1 byrd-build            # writes, only on a feature branch
#   start-byrdcoder.ps1 byrd-ask -Workspace D:\some\clone
#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [ValidateSet('byrd-ask', 'byrd-patch', 'byrd-build', 'byrd-test', 'byrd-review', 'byrd-offline', 'byrd-private')]
    [string]$Profile = 'byrd-ask',
    [string]$Workspace,
    [switch]$Regen
)
$ErrorActionPreference = 'Stop'

$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) {
    Write-Host "BYRDHOUSE_ROOT is not set/valid — open a new shell or run setup." -ForegroundColor Red; exit 1
}
if (-not $Workspace) { $Workspace = $root }
$cfg = Get-Content (Join-Path $root 'byrdhouse.config.json') -Raw | ConvertFrom-Json
$lmUrl = $cfg.services.lmstudio
if (-not $lmUrl -or $lmUrl -like '*CHANGE_ME*') {
    Write-Host "services.lmstudio is not configured in byrdhouse.config.json" -ForegroundColor Red; exit 1
}

# ── Generate/refresh the isolated machine config (never committed) ───────────
$cfgDir = Join-Path $root 'LLM\byrdcoder'
$machineCfg = Join-Path $cfgDir 'opencode.json'
$exampleDir = Join-Path $root 'configs\byrdcoder'
if ($Regen -or -not (Test-Path $machineCfg)) {
    New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
    $body = Get-Content (Join-Path $exampleDir 'opencode.example.json') -Raw
    $body = $body.Replace('{{LMSTUDIO_URL}}', $lmUrl)
    Set-Content -Path $machineCfg -Value $body -Encoding UTF8
    Copy-Item (Join-Path $exampleDir 'prompts') $cfgDir -Recurse -Force
    Copy-Item (Join-Path $exampleDir 'allowlist.json') $cfgDir -Force
    Write-Host "generated isolated config: $machineCfg" -ForegroundColor Green
}

# ── Branch guard: byrd-build may never run on a protected branch ─────────────
$allow = Get-Content (Join-Path $exampleDir 'allowlist.json') -Raw | ConvertFrom-Json
Push-Location $Workspace
$branch = (& git rev-parse --abbrev-ref HEAD 2>$null) -join ''
Pop-Location
if ($Profile -eq 'byrd-build') {
    if (-not $branch -or $branch -eq 'HEAD') {
        Write-Host "byrd-build refused: workspace is not on a branch (detached HEAD or not a repo)." -ForegroundColor Red; exit 1
    }
    if (@($allow.branches.protected) -contains $branch) {
        Write-Host "byrd-build refused: '$branch' is protected. Create a feature branch first:" -ForegroundColor Red
        Write-Host "  git checkout -b byrdcoder/<task-name>" -ForegroundColor Yellow
        exit 1
    }
    $prefixOk = $false
    foreach ($p in $allow.branches.allowed_prefixes) { if ($branch.StartsWith($p)) { $prefixOk = $true } }
    if (-not $prefixOk) {
        Write-Host "byrd-build refused: branch '$branch' does not use an approved prefix ($($allow.branches.allowed_prefixes -join ', '))." -ForegroundColor Red
        exit 1
    }
}

# ── Launch ───────────────────────────────────────────────────────────────────
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
    Write-Host "opencode is not installed — see docs/BYRDCODER_LOCAL.md (Phase 1 install)." -ForegroundColor Red; exit 1
}
$logDir = Join-Path $root 'logs\byrdcoder'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Add-Content -Path (Join-Path $logDir 'sessions.log') -Value ("{0} profile={1} branch={2} workspace={3} user={4}" -f (Get-Date -Format s), $Profile, $branch, $Workspace, $env:USERNAME)

Write-Host "ByrdCoder — profile $Profile (default sessions are read-only; writes only via byrd-build on a feature branch)" -ForegroundColor Cyan
$env:OPENCODE_CONFIG = $machineCfg
Push-Location $Workspace
try {
    & opencode --agent $Profile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "opencode exited with $LASTEXITCODE — if '--agent' is not recognized by this version, run 'opencode --help' and select the agent with Tab in the TUI instead." -ForegroundColor Yellow
    }
} finally {
    Pop-Location
    Remove-Item Env:OPENCODE_CONFIG -ErrorAction SilentlyContinue
}
