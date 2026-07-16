# byrdcoder-benchmark.ps1 — Phase 5 model benchmark (docs/byrdcoder-model-benchmark.md).
# Runs the SAME 7-task protocol against each candidate LM Studio model inside a
# DISPOSABLE clone of the repo (the real working tree is never touched), timing
# each task and collecting outputs/diffs/test logs for the scorecard. A primary
# model is chosen from this table, never from subjective chat quality.
#   byrdcoder-benchmark.ps1                       # all discovered coder models
#   byrdcoder-benchmark.ps1 -Models qwen2.5-coder-14b-instruct -Reviewer qwopus
# Requires: machine config generated (run start-byrdcoder.ps1 once), opencode
# CLI, LM Studio running. Load ONE model at a time in LM Studio for fair
# VRAM/RAM numbers (8GB card: never two heavy models at once).
#Requires -Version 5.1
param(
    [string[]]$Models,
    [string]$Reviewer,
    [int[]]$Tasks = @(1, 2, 3, 4, 5, 6, 7)
)
$ErrorActionPreference = 'Stop'

$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) { Write-Host 'BYRDHOUSE_ROOT missing' -ForegroundColor Red; exit 1 }
$machineCfg = Join-Path $root 'LLM\byrdcoder\opencode.json'
if (-not (Test-Path $machineCfg)) { Write-Host 'machine config missing — run start-byrdcoder.ps1 once first' -ForegroundColor Red; exit 1 }
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { Write-Host 'opencode not installed (docs/BYRDCODER_LOCAL.md Phase 1)' -ForegroundColor Red; exit 1 }

# Discover coder models if none named
if (-not $Models) {
    $disc = ((& python (Join-Path $root 'scripts\byrdcoder_models.py') --root $root --json) -join "`n") | ConvertFrom-Json
    $Models = @($disc.models | Where-Object { $_.coder_hint } | ForEach-Object { $_.id })
    if ($Models.Count -eq 0) { Write-Host 'no coder-family models discovered — name one with -Models' -ForegroundColor Red; exit 1 }
}

# The 7-task protocol: same wording for every model. profile = byrd-* agent.
$taskDefs = @(
    @{ n = 1; profile = 'byrd-ask';   text = 'Explain scripts/byrdcast_swap.py: purpose, the 14 pipeline stages, its fail-closed behavior, and how it uses the config. Cite real function names only.' },
    @{ n = 2; profile = 'byrd-ask';   text = 'Find ONE real bug or defect in scripts/byrdcast_swap.py. Do not modify any file. Report the exact location (function + lines), why it is wrong, and a failure scenario.' },
    @{ n = 3; profile = 'byrd-patch'; text = 'Produce a unified diff patch that fixes the bug you found in scripts/byrdcast_swap.py. Do not apply it. The diff must apply cleanly with git apply against the current file.' },
    @{ n = 4; profile = 'byrd-build'; text = 'Apply your fix to scripts/byrdcast_swap.py on the current feature branch, and add or update a regression check for it in tests/integration_test.py following the existing check() style. Run python -m py_compile on both files. Commit with a clear message.' },
    @{ n = 5; profile = 'byrd-test';  text = 'Run python tests/integration_test.py and report the result honestly: total failures and the exact names of any failing checks.' },
    @{ n = 6; profile = 'byrd-review'; text = 'Review your own applied patch (git diff main...HEAD) for risks: correctness, style drift, hidden failures, forbidden paths. Return the verdict JSON: {"verdict": "...", "reasons": [...], "risks": [...]}.' },
    @{ n = 7; profile = 'byrd-ask';   text = 'Summarize: which files changed, what the change does, and the exact rollback commands to undo it.' }
)
$taskDefs = @($taskDefs | Where-Object { $Tasks -contains $_.n })

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$benchDir = Join-Path $root "logs\byrdcoder\bench_$stamp"
New-Item -ItemType Directory -Path $benchDir -Force | Out-Null
$haveSmi = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)

# Disposable clone — the benchmark NEVER runs in the real working tree.
$clone = Join-Path $benchDir 'repo'
Write-Host "cloning disposable workspace: $clone" -ForegroundColor Cyan
& git clone --no-hardlinks --quiet $root $clone
$env:OPENCODE_CONFIG = $machineCfg
$results = New-Object System.Collections.ArrayList

try {
    foreach ($model in $Models) {
        Write-Host "`n=== model: $model ===" -ForegroundColor Cyan
        $modelDir = Join-Path $benchDir ($model -replace '[^\w\.-]', '_')
        New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
        Push-Location $clone
        & git checkout --quiet -B "byrdcoder/bench-$stamp" # fresh branch per model
        & git reset --hard --quiet; & git clean -fdq       # disposable clone only

        foreach ($t in $taskDefs) {
            Write-Host ("task {0} ({1})..." -f $t.n, $t.profile)
            $outFile = Join-Path $modelDir ("task{0}.txt" -f $t.n)
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            # -c continues the model's session so later tasks see earlier context
            $cliArgs = @('run', '--agent', $t.profile, '--model', "lmstudio/$model")
            if ($t.n -gt 1) { $cliArgs += '--continue' }
            $cliArgs += $t.text
            & opencode @cliArgs *> $outFile
            $exit = $LASTEXITCODE
            $sw.Stop()
            $vram = $null
            if ($haveSmi) { $vram = (& nvidia-smi --query-gpu=memory.used --format=csv,noheader) -join '' }
            $ram = [math]::Round((Get-CimInstance Win32_OperatingSystem |
                ForEach-Object { ($_.TotalVisibleMemorySize - $_.FreePhysicalMemory) / 1MB }), 1)
            [void]$results.Add([ordered]@{ model = $model; task = $t.n; profile = $t.profile
                                           seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1)
                                           exit = $exit; vram = $vram; ram_used_gb = $ram
                                           output = $outFile })
        }

        # Preserve what the model actually changed, then reset the clone
        & git diff main | Set-Content (Join-Path $modelDir 'applied.diff') -Encoding UTF8
        & git log main..HEAD --oneline | Set-Content (Join-Path $modelDir 'commits.txt') -Encoding UTF8
        Pop-Location

        # Optional cross-model review (two-agent loop, Phase 6)
        if ($Reviewer -and $Reviewer -ne $model) {
            $taskFile = Join-Path $modelDir 'task4.txt'
            $diffFile = Join-Path $modelDir 'applied.diff'
            $testFile = Join-Path $modelDir 'task5.txt'
            if ((Test-Path $diffFile) -and (Get-Item $diffFile).Length -gt 0) {
                Write-Host "cross-review by $Reviewer..." -ForegroundColor Cyan
                & python (Join-Path $root 'scripts\byrdcoder_review.py') --root $root `
                    --task $taskFile --diff $diffFile --tests $testFile --model $Reviewer
                [void]$results.Add([ordered]@{ model = $model; task = 'cross-review'
                                               profile = 'byrdcoder_review.py'; reviewer = $Reviewer
                                               exit = $LASTEXITCODE })
            }
        }
    }
} finally {
    if ((Get-Location).Path -eq $clone) { Pop-Location }
    Remove-Item Env:OPENCODE_CONFIG -ErrorAction SilentlyContinue
}

# Scorecard skeleton — measured columns filled, judgment columns founder-scored
$results | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $benchDir 'bench.json') -Encoding UTF8
$md = @("### $(Get-Date -Format 'yyyy-MM-dd HH:mm') — ByrdCoder benchmark ($($Models -join ', '))", '',
        '| Model | Task | Profile | Time (s) | Exit | VRAM | Tool calls OK | Paths real | Patch applies | Tests pass | Hallucinations | Recovered from failure |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|')
foreach ($row in $results) {
    $md += ("| {0} | {1} | {2} | {3} | {4} | {5} |  |  |  |  |  |  |" -f
        $row.model, $row.task, $row.profile, $row.seconds, $row.exit, $row.vram)
}
$md += ''
$md += "Transcripts, applied.diff and commits.txt per model are under $benchDir — fill the judgment columns from them (docs/byrdcoder-model-benchmark.md scoring guide), then paste this table into that doc. The disposable clone can be deleted: Remove-Item -Recurse -Force $clone"
$md -join "`r`n" | Set-Content (Join-Path $benchDir 'benchmark.md') -Encoding UTF8
Write-Host "`nbenchmark table: $(Join-Path $benchDir 'benchmark.md')" -ForegroundColor Green
