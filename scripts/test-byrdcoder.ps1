# test-byrdcoder.ps1 — ByrdCoder configuration / permission / allowlist
# behavior tests (docs/BYRDCODER_LOCAL.md). Static contract checks run
# anywhere; live checks (LM Studio discovery, opencode CLI) SKIP cleanly when
# the service is down so this can run on either machine at any time.
# Exit 0 = all passed (skips allowed), 1 = any FAIL.
#Requires -Version 5.1
param([switch]$Quiet)

$ErrorActionPreference = 'SilentlyContinue'
$script:pass = 0; $script:fail = 0; $script:skip = 0

function T([string]$Name, [string]$State, [string]$Detail = '') {
    switch ($State) {
        'pass' { $script:pass++ }
        'fail' { $script:fail++ }
        'skip' { $script:skip++ }
    }
    if (-not $Quiet) {
        $color = @{ pass = 'Green'; fail = 'Red'; skip = 'Yellow' }[$State]
        Write-Host ("  [{0,-4}] {1}{2}" -f $State.ToUpper(), $Name, $(if ($Detail) { " — $Detail" } else { '' })) -ForegroundColor $color
    }
}

$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) { Write-Host 'BYRDHOUSE_ROOT missing' -ForegroundColor Red; exit 1 }
$exDir = Join-Path $root 'configs\byrdcoder'
if (-not $Quiet) { Write-Host "`nByrdCoder tests — $(Get-Date -Format s)`n== static contract ==" -ForegroundColor Cyan }

# ── Config contract ──────────────────────────────────────────────────────────
$ex = $null
try { $ex = Get-Content (Join-Path $exDir 'opencode.example.json') -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
T 'example config parses' ($(if ($ex) { 'pass' } else { 'fail' }))
if ($ex) {
    $profiles = @('byrd-ask', 'byrd-patch', 'byrd-build', 'byrd-test', 'byrd-review', 'byrd-offline', 'byrd-private')
    $have = @($ex.agent.PSObject.Properties.Name)
    $missing = @($profiles | Where-Object { $have -notcontains $_ })
    T 'all 7 profiles defined' ($(if ($missing.Count -eq 0) { 'pass' } else { 'fail' })) ($missing -join ', ')
    T 'global default read-only (edit deny)' ($(if ($ex.permission.edit -eq 'deny') { 'pass' } else { 'fail' }))
    T 'global default read-only (bash * deny)' ($(if ($ex.permission.bash.'*' -eq 'deny') { 'pass' } else { 'fail' }))
    T 'global webfetch deny' ($(if ($ex.permission.webfetch -eq 'deny') { 'pass' } else { 'fail' }))
    T 'bridge plugin pinned' ($(if (@($ex.plugin) -match '^opencode-lmstudio@\d') { 'pass' } else { 'fail' })) (@($ex.plugin) -join ', ')
    T 'share disabled + autoupdate off' ($(if ($ex.share -eq 'disabled' -and $ex.autoupdate -eq $false) { 'pass' } else { 'fail' }))
    T 'LM Studio URL is a placeholder (no hardcoded host in git)' ($(if ($ex.provider.lmstudio.options.baseURL -eq '{{LMSTUDIO_URL}}') { 'pass' } else { 'fail' }))
    foreach ($ro in @('byrd-ask', 'byrd-review', 'byrd-offline', 'byrd-private')) {
        $a = $ex.agent.$ro
        $ok = ($a.permission.edit -eq 'deny' -and $a.tools.write -eq $false -and $a.tools.edit -eq $false)
        T "$ro is read-only" ($(if ($ok) { 'pass' } else { 'fail' }))
    }
    $b = $ex.agent.'byrd-build'.permission.bash
    $ok = ($b.'git push*' -eq 'deny' -and $b.'git merge*' -eq 'deny' -and $b.'*' -eq 'deny' -and $b.'git checkout main*' -eq 'deny')
    T 'byrd-build cannot push/merge/switch to main' ($(if ($ok) { 'pass' } else { 'fail' }))
    T 'byrd-patch cannot edit' ($(if ($ex.agent.'byrd-patch'.permission.edit -eq 'deny') { 'pass' } else { 'fail' }))
    $t = $ex.agent.'byrd-test'
    $ok = ($t.permission.edit -eq 'deny' -and $t.permission.bash.'python tests/integration_test.py' -eq 'allow' -and $t.permission.bash.'*' -eq 'deny')
    T 'byrd-test runs only allowlisted tests' ($(if ($ok) { 'pass' } else { 'fail' }))
}

# ── Allowlist contract ───────────────────────────────────────────────────────
$al = $null
try { $al = Get-Content (Join-Path $exDir 'allowlist.json') -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
T 'allowlist parses' ($(if ($al) { 'pass' } else { 'fail' }))
if ($al) {
    T 'main is protected' ($(if (@($al.branches.protected) -contains 'main') { 'pass' } else { 'fail' }))
    $needDeny = @('git push', 'git merge', 'git reset --hard', 'rm', 'Remove-Item', 'pip install', 'Invoke-WebRequest')
    $missingDeny = @($needDeny | Where-Object { @($al.commands.deny) -notcontains $_ })
    T 'deny list covers push/merge/delete/net/install' ($(if ($missingDeny.Count -eq 0) { 'pass' } else { 'fail' })) ($missingDeny -join ', ')
    $badAllow = @($al.commands.allow | Where-Object { $_ -match 'push|merge|rm|del|install|curl|wget' })
    T 'allow list contains no escape hatches' ($(if ($badAllow.Count -eq 0) { 'pass' } else { 'fail' })) ($badAllow -join ', ')
    $needForbidden = @('.env', 'secrets', 'credentials', 'profiles/*/references', 'Generators/ComfyUI', 'db')
    $missingF = @($needForbidden | Where-Object { @($al.directories.forbidden) -notcontains $_ })
    T 'forbidden dirs cover secrets/identity/production' ($(if ($missingF.Count -eq 0) { 'pass' } else { 'fail' })) ($missingF -join ', ')
}

# ── Prompts present ──────────────────────────────────────────────────────────
foreach ($p in @('byrd-ask', 'byrd-patch', 'byrd-build', 'byrd-test', 'byrd-review', 'byrd-offline', 'byrd-private')) {
    $f = Join-Path $exDir "prompts\$p.md"
    $ok = (Test-Path $f) -and ((Get-Item $f).Length -gt 200)
    T "prompt $p.md exists" ($(if ($ok) { 'pass' } else { 'fail' }))
}

# ── Branch guard behavior (same rules start-byrdcoder.ps1 enforces) ──────────
if (-not $Quiet) { Write-Host "== branch guard behavior ==" -ForegroundColor Cyan }
function Test-BranchAllowed([string]$Branch, $Allow) {
    if (-not $Branch -or $Branch -eq 'HEAD') { return $false }
    if (@($Allow.branches.protected) -contains $Branch) { return $false }
    foreach ($p in $Allow.branches.allowed_prefixes) { if ($Branch.StartsWith($p)) { return $true } }
    return $false
}
if ($al) {
    T 'guard refuses main' ($(if (-not (Test-BranchAllowed 'main' $al)) { 'pass' } else { 'fail' }))
    T 'guard refuses detached HEAD' ($(if (-not (Test-BranchAllowed 'HEAD' $al)) { 'pass' } else { 'fail' }))
    T 'guard refuses unknown prefix' ($(if (-not (Test-BranchAllowed 'random-branch' $al)) { 'pass' } else { 'fail' }))
    T 'guard allows byrdcoder/*' ($(if (Test-BranchAllowed 'byrdcoder/task-x' $al) { 'pass' } else { 'fail' }))
    T 'guard allows feature/*' ($(if (Test-BranchAllowed 'feature/task-y' $al) { 'pass' } else { 'fail' }))
}

# ── Generated machine config (only if present) ───────────────────────────────
$machineCfg = Join-Path $root 'LLM\byrdcoder\opencode.json'
if (Test-Path $machineCfg) {
    $mcRaw = Get-Content $machineCfg -Raw
    T 'machine config placeholder substituted' ($(if ($mcRaw -notmatch '\{\{LMSTUDIO_URL\}\}') { 'pass' } else { 'fail' }))
    Push-Location $root
    $ignored = (& git check-ignore 'LLM/byrdcoder/opencode.json' 2>$null)
    Pop-Location
    T 'machine config is gitignored' ($(if ($ignored) { 'pass' } else { 'fail' }))
} else {
    T 'machine config checks' 'skip' 'not generated yet (start-byrdcoder.ps1 creates it)'
}

# ── Live checks (skip when services are down) ────────────────────────────────
if (-not $Quiet) { Write-Host "== live (skips if service down) ==" -ForegroundColor Cyan }
$oc = Get-Command opencode -ErrorAction SilentlyContinue
if ($oc) { T 'opencode CLI present' 'pass' ((& opencode --version 2>&1) -join ' ') }
else { T 'opencode CLI present' 'skip' 'not installed on this machine' }

$raw = (& python (Join-Path $root 'scripts\byrdcoder_models.py') --root $root --json 2>$null) -join "`n"
$disc = $null
if ($raw) { try { $disc = $raw | ConvertFrom-Json } catch { } }
if ($disc -and $disc.endpoint) {
    T 'LM Studio discovery' 'pass' ("{0} model(s) via {1}" -f @($disc.models).Count, $disc.endpoint)
    $emb = @($disc.models | Where-Object { $_.type -match 'embed' })
    T 'embeddings excluded' ($(if ($emb.Count -eq 0) { 'pass' } else { 'fail' })) ("{0} embedding record(s) leaked" -f $emb.Count)
} else {
    T 'LM Studio discovery' 'skip' 'LM Studio unreachable from this machine right now'
}

if (-not $Quiet) { Write-Host ("`n{0} passed, {1} failed, {2} skipped" -f $script:pass, $script:fail, $script:skip) -ForegroundColor $(if ($script:fail) { 'Red' } else { 'Green' }) }
exit $(if ($script:fail) { 1 } else { 0 })
