# identity-benchmark.ps1 — repeatable five-target identity benchmark
# (docs/identity-benchmark.md). Runs every image in -TargetsDir through the
# selected branch and writes a scorecard the founder pastes back into the doc.
#   Branch S (default): ByrdCast Swap V0 (scripts/byrdcast_swap.py), synchronous
#     — collects each run's sidecar.json score/route/accepted + runtime + a
#     VRAM-peak sample into logs\benchmarks\identity_<stamp>\benchmark.{json,md}.
#   Branch A: submits belt image.faceswap jobs via facelab.ps1 swap — results
#     are reviewed in the dashboard (the belt cards/judges them); the runner
#     records what was submitted.
#   Branches B/C/D (facetools / FaceShaper / Forbidden Vision) are gated on
#     Identity Lab installs — see docs/identity-stack-review.md.
# Repeat runs (-Repeat) before declaring any winner. Never train on the
# evaluation targets; using them as swap TARGETS here is the intended use.
#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)][string]$TargetsDir,
    [string]$Identity = "Carey",
    [ValidateSet("fast", "balanced", "best")][string]$Quality = "balanced",
    [string]$Refs,
    [ValidateSet("S", "A")][string]$Branch = "S",
    [int]$Repeat = 1
)
$ErrorActionPreference = "Stop"

$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) {
    Write-Host "BYRDHOUSE_ROOT is not set/valid — open a new shell or run setup." -ForegroundColor Red; exit 1
}
if (-not (Test-Path $TargetsDir)) {
    Write-Host "targets folder not found: $TargetsDir" -ForegroundColor Red; exit 1
}
$targets = @(Get-ChildItem $TargetsDir -File | Where-Object { $_.Extension -match '\.(png|jpe?g|webp)$' } | Sort-Object Name)
if ($targets.Count -eq 0) {
    Write-Host "no images in $TargetsDir" -ForegroundColor Red; exit 1
}
if ($targets.Count -ne 5) {
    Write-Host "note: benchmark spec is 5 targets (front/45deg/profile/occlusion/smallface); found $($targets.Count)" -ForegroundColor Yellow
}

$comfyPython = Join-Path $root "Generators\ComfyUI\.venv\Scripts\python.exe"
if (-not (Test-Path $comfyPython)) { $comfyPython = "python" }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$benchDir = Join-Path $root ("logs\benchmarks\identity_" + $stamp)
New-Item -ItemType Directory -Path $benchDir -Force | Out-Null
$haveSmi = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)

$runs = New-Object System.Collections.ArrayList
Write-Host "`nIdentity benchmark — branch $Branch, quality $Quality, identity $Identity, repeat $Repeat" -ForegroundColor Cyan
Write-Host "results: $benchDir`n"

if ($Branch -eq "A") {
    # Belt submission: the belt judges/cards each job; review in the dashboard.
    $facelab = Join-Path $root "scripts\facelab.ps1"
    foreach ($t in $targets) {
        Write-Host "submitting belt swap: $($t.Name)"
        & $facelab swap -Image $t.FullName -Purpose "identity-benchmark $stamp"
        [void]$runs.Add([ordered]@{ case = $t.Name; branch = "A"; submitted = $true })
    }
    ([pscustomobject][ordered]@{ generated = (Get-Date -Format s); branch = "A"; quality = $Quality
                                 identity = $Identity; runs = $runs }) |
        ConvertTo-Json -Depth 6 | Set-Content (Join-Path $benchDir 'benchmark.json') -Encoding UTF8
    Write-Host "`n5 belt jobs submitted — score them in the dashboard, then record the table in docs/identity-benchmark.md." -ForegroundColor Green
    exit 0
}

# Branch S — synchronous ByrdCast Swap V0 runs
$swapScript = Join-Path $root "scripts\byrdcast_swap.py"
for ($r = 1; $r -le $Repeat; $r++) {
    foreach ($t in $targets) {
        $caseOut = Join-Path $benchDir ("swaps\" + [IO.Path]::GetFileNameWithoutExtension($t.Name) + "_r$r")
        Write-Host ("run {0}/{1} — {2}" -f $r, $Repeat, $t.Name) -ForegroundColor Cyan
        $swapArgs = @($swapScript, "--identity", $Identity, "--target", $t.FullName,
                      "--out", $caseOut, "--quality", $Quality)
        if ($Refs) { $swapArgs += @("--refs", $Refs) }

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        & $comfyPython @swapArgs
        $exit = $LASTEXITCODE
        $sw.Stop()
        $vram = $null
        if ($haveSmi) { $vram = (& nvidia-smi --query-gpu=memory.used --format=csv,noheader) -join '; ' }

        $row = [ordered]@{ case = $t.Name; repeat = $r; branch = "S"; quality = $Quality
                           runtime_s = [math]::Round($sw.Elapsed.TotalSeconds, 1)
                           vram_after_run = $vram; exit_code = $exit }
        $sidecarFile = Get-ChildItem $caseOut -Recurse -Filter sidecar.json -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($sidecarFile) {
            $sc = Get-Content $sidecarFile.FullName -Raw | ConvertFrom-Json
            $row.job_dir = $sidecarFile.DirectoryName
            $row.route = $sc.swap_route
            $row.accepted = $sc.accepted
            $row.score_overall = $sc.score.overall
            $row.weakest = ($sc.score.weakest -join ', ')
            $row.reasons = ($sc.reasons -join ' | ')
        } else {
            $row.error = "no sidecar.json produced — run failed before scoring (see console output above)"
        }
        [void]$runs.Add($row)
    }
}

# Scorecard: benchmark.json (machine) + benchmark.md (paste into the doc)
([pscustomobject][ordered]@{ generated = (Get-Date -Format s); branch = "S"; quality = $Quality
                             identity = $Identity; repeat = $Repeat; targets_dir = $TargetsDir
                             runs = $runs }) |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $benchDir 'benchmark.json') -Encoding UTF8

$md = New-Object System.Collections.ArrayList
[void]$md.Add("### $((Get-Date -Format 'yyyy-MM-dd HH:mm')) — branch S (ByrdCast Swap V0), quality $Quality, repeat $Repeat")
[void]$md.Add("")
[void]$md.Add("| Case | Run | Route | Accepted | Score | Weakest factors | Runtime (s) | Notes |")
[void]$md.Add("|---|---|---|---|---|---|---|---|")
foreach ($row in $runs) {
    $note = $row.reasons; if ($row.error) { $note = $row.error }
    [void]$md.Add(("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |" -f
        $row.case, $row.repeat, $row.route, $row.accepted, $row.score_overall, $row.weakest, $row.runtime_s, $note))
}
[void]$md.Add("")
[void]$md.Add("Visual fields (identity/jaw/eyes/mouth/skin/lighting/seams/background, 0-5) are founder-scored from each job_dir's final.png. Results folder: $benchDir")
$md -join "`r`n" | Set-Content (Join-Path $benchDir 'benchmark.md') -Encoding UTF8

Write-Host "`nScorecard written:" -ForegroundColor Green
Write-Host "  $(Join-Path $benchDir 'benchmark.md')"
Write-Host "Paste it into docs/identity-benchmark.md (Results section) and add the founder visual scores." -ForegroundColor Green
