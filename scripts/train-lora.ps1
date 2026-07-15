<#
train-lora.ps1 — Face Lab step 2 (docs/FACE_LAB.md).

Trains an SDXL identity LoRA from a collected dataset, sized for the 8GB 3070:
batch 1, gradient checkpointing, Adafactor, bf16, UNet-only, latents cached to
disk. Founder limits are enforced from byrdhouse.config.json `training`:
  - vram_budget_mb (7200): training REFUSES to start with less free VRAM
  - cpu_threads (16, max 18 of the 20): passed to the trainer

VERSIONING: output is always a NEW file — carey_face_v2, _v3, ... scanned
across both the training output dir and ComfyUI's models\loras. Nothing is
ever overwritten; yesterday's run stays on disk.

Usage (on BYRD-GAMING, after collect-training-images.ps1):
    powershell -ExecutionPolicy Bypass -File scripts\train-lora.ps1 -Dataset carey_face

    -Dataset carey_face  dataset under training\datasets (trigger word = this name)
    -BaseModel ""        checkpoint file or loose name; default: juggernaut from ComfyUI
    -Repeats 12          kohya repeats per image per epoch
    -Epochs 8            training epochs (a save every 2 so you can pick the best)
    -NetworkDim 32       LoRA rank (32 fits the 3070; 64 needs more VRAM)
    -DryRun              print the full training command, run nothing

Requires kohya sd-scripts (auto-detected, or set training.sd_scripts_dir in the
config). If it is missing the script prints the exact one-time install steps.
#>
param(
    [string]$Dataset = "carey_face",
    [string]$BaseModel = "",
    [int]$Repeats = 12,
    [int]$Epochs = 8,
    [int]$NetworkDim = 32,
    [int]$NetworkAlpha = 16,
    [string]$Resolution = "1024,1024",
    [string]$LearningRate = "1e-4",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

if (-not $env:BYRDHOUSE_ROOT) {
    Write-Host "BYRDHOUSE_ROOT is not set — run setup or open a new shell." -ForegroundColor Red
    exit 1
}
$root = $env:BYRDHOUSE_ROOT
$cfg = Get-Content (Join-Path $root "byrdhouse.config.json") -Raw | ConvertFrom-Json
$train = $cfg.training
$vramBudget = 7200
$cpuThreads = 16
$datasetsRel = "training/datasets"
$lorasRel = "training/loras"
if ($train) {
    if ($train.vram_budget_mb) { $vramBudget = [int]$train.vram_budget_mb }
    if ($train.cpu_threads)    { $cpuThreads = [int]$train.cpu_threads }
    if ($train.datasets_dir)   { $datasetsRel = $train.datasets_dir }
    if ($train.loras_dir)      { $lorasRel = $train.loras_dir }
}
if ($cpuThreads -gt 18) { $cpuThreads = 18 }   # founder rule: leave 2+ of the 20 threads
if ($cpuThreads -lt 1)  { $cpuThreads = 1 }

# ── dataset must exist (collect-training-images.ps1 makes it) ────────────────
$dsDir = Join-Path $root (Join-Path ($datasetsRel -replace "/", "\") $Dataset)
$imgDir = Join-Path $dsDir "img"
$images = @()
if (Test-Path $imgDir) {
    $images = Get-ChildItem $imgDir -File | Where-Object {
        @(".png", ".jpg", ".jpeg", ".webp") -contains $_.Extension.ToLower() }
}
if (-not $images) {
    Write-Host "No images in $imgDir" -ForegroundColor Red
    Write-Host "Run collect-training-images.ps1 first:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\collect-training-images.ps1 -Name $Dataset"
    exit 1
}
Write-Host ""
Write-Host "ByrdHouse LoRA trainer" -ForegroundColor Cyan
$imgCount = @($images).Count
Write-Host ("  dataset : {0} ({1} images)" -f $Dataset, $imgCount)

# Auto-size repeats to ~2,500 total steps (identity-LoRA sweet spot) unless the
# founder pinned -Repeats. 300 collected images at the small-dataset default of
# 12 repeats x 8 epochs would be ~29k steps — days of GPU and an overbaked LoRA.
if (-not $PSBoundParameters.ContainsKey('Repeats')) {
    $Repeats = [Math]::Max(1, [Math]::Round(2500 / ([Math]::Max(1, $imgCount) * $Epochs)))
}
$estSteps = $imgCount * $Repeats * $Epochs
Write-Host ("  steps   : ~{0} ({1} images x {2} repeats x {3} epochs, batch 1)" -f $estSteps, $imgCount, $Repeats, $Epochs)
if ($estSteps -gt 6000) {
    Write-Host "  WARNING: very high step count for an identity LoRA — overtraining bakes in artifacts. Lower -Repeats or -Epochs." -ForegroundColor Yellow
}

# ── VERSION: always a new file, never overwrite (scan BOTH output dirs) ──────
$outDir = Join-Path $root ($lorasRel -replace "/", "\")
$comfyLoras = Join-Path $root "Generators\ComfyUI\models\loras"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$maxV = 0
foreach ($dir in @($outDir, $comfyLoras)) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Filter "$Dataset`_v*.safetensors" -ErrorAction SilentlyContinue |
            ForEach-Object {
                if ($_.BaseName -match "_v(\d+)$" -and [int]$Matches[1] -gt $maxV) {
                    $maxV = [int]$Matches[1]
                }
            }
    }
}
$outName = "{0}_v{1}" -f $Dataset, ($maxV + 1)
Write-Host ("  output  : {0}\{1}.safetensors (previous versions kept)" -f $outDir, $outName)

# ── VRAM preflight: verify, never assume (belt rule) ──────────────────────────
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
$smiPath = if ($smi) { $smi.Source } elseif (Test-Path "C:\Windows\System32\nvidia-smi.exe") { "C:\Windows\System32\nvidia-smi.exe" } else { $null }
if ($smiPath) {
    $q = & $smiPath --query-gpu=memory.used,memory.total --format=csv,noheader,nounits
    $used, $total = ($q -split ",") | ForEach-Object { [int]$_.Trim() }
    $free = $total - $used
    Write-Host ("  vram    : {0}MB free of {1}MB (budget {2}MB)" -f $free, $total, $vramBudget)
    if ($free -lt $vramBudget) {
        Write-Host ""
        Write-Host ("ABORT: only {0}MB VRAM free but training needs the card to itself (budget {1}MB)." -f $free, $vramBudget) -ForegroundColor Red
        Write-Host "Free it first: close ComfyUI, then 'lms unload --all' to drop LM Studio models." -ForegroundColor Yellow
        exit 1
    }
} elseif (-not $DryRun) {
    Write-Host ""
    Write-Host "ABORT: nvidia-smi not found — VRAM cannot be verified (never assume)." -ForegroundColor Red
    exit 1
}

# ── find kohya sd-scripts + its python ────────────────────────────────────────
$sdCandidates = @()
if ($train -and $train.sd_scripts_dir -and -not $train.sd_scripts_dir.StartsWith("CHANGE_ME")) {
    $sdCandidates += $train.sd_scripts_dir
}
$sdCandidates += @(
    (Join-Path $root "Training\sd-scripts"),
    (Join-Path $root "Generators\sd-scripts"),
    (Join-Path $root "Generators\kohya_ss\sd-scripts"),
    "$env:USERPROFILE\kohya_ss\sd-scripts",
    "$env:USERPROFILE\sd-scripts"
)
$sdDir = $sdCandidates | Where-Object { $_ -and (Test-Path (Join-Path $_ "sdxl_train_network.py")) } | Select-Object -First 1
if (-not $sdDir) {
    Write-Host ""
    Write-Host "kohya sd-scripts not found. One-time install (PowerShell, on GAMING):" -ForegroundColor Yellow
    Write-Host ("  git clone https://github.com/kohya-ss/sd-scripts " + (Join-Path $root "Training\sd-scripts"))
    Write-Host ("  cd " + (Join-Path $root "Training\sd-scripts"))
    Write-Host "  python -m venv venv; .\venv\Scripts\activate"
    Write-Host "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
    Write-Host "  pip install -r requirements.txt"
    Write-Host "Then rerun this script. (Or set training.sd_scripts_dir in byrdhouse.config.json"
    Write-Host " to wherever yesterday's trainer lives — find-codex-work.ps1 can help locate it.)"
    exit 1
}
$py = $null
if ($train -and $train.trainer_python -and -not $train.trainer_python.StartsWith("CHANGE_ME") -and (Test-Path $train.trainer_python)) {
    $py = $train.trainer_python
} elseif (Test-Path (Join-Path $sdDir "venv\Scripts\python.exe")) {
    $py = Join-Path $sdDir "venv\Scripts\python.exe"
} else {
    $py = "python"
}
Write-Host ("  trainer : {0}" -f $sdDir)
Write-Host ("  python  : {0}" -f $py)
Write-Host ("  threads : {0}" -f $cpuThreads)

# ── base model: explicit path, or loose-match in ComfyUI checkpoints ──────────
$base = $BaseModel
if (-not $base -or -not (Test-Path $base)) {
    $ckptDir = Join-Path $root "Generators\ComfyUI\models\checkpoints"
    $want = if ($BaseModel) { $BaseModel } else { "juggernaut" }
    $norm = ($want -replace "[^a-zA-Z0-9]", "").ToLower()
    $hit = $null
    if (Test-Path $ckptDir) {
        $all = Get-ChildItem $ckptDir -Filter *.safetensors
        $hit = $all | Where-Object { ($_.BaseName -replace "[^a-zA-Z0-9]", "").ToLower().Contains($norm) } |
            Select-Object -First 1
        if (-not $hit -and -not $BaseModel) { $hit = $all | Select-Object -First 1 }
    }
    if (-not $hit) {
        Write-Host "No base checkpoint found (looked for '$want' in $ckptDir). Pass -BaseModel." -ForegroundColor Red
        exit 1
    }
    $base = $hit.FullName
}
Write-Host ("  base    : {0}" -f $base)

# ── kohya folder layout: kohya\<repeats>_<dataset> (hardlinks, fallback copy) ─
$kohyaRoot = Join-Path $dsDir "kohya"
$bucketDir = Join-Path $kohyaRoot ("{0}_{1}" -f $Repeats, $Dataset)
if (-not $DryRun) {
    if (Test-Path $kohyaRoot) { Remove-Item $kohyaRoot -Recurse -Force }  # rebuilt each run from img\
    New-Item -ItemType Directory -Force -Path $bucketDir | Out-Null
    foreach ($f in $images) {
        $link = Join-Path $bucketDir $f.Name
        try { New-Item -ItemType HardLink -Path $link -Target $f.FullName -ErrorAction Stop | Out-Null }
        catch { Copy-Item $f.FullName $link }
        $cap = [System.IO.Path]::ChangeExtension($f.FullName, ".txt")
        if (Test-Path $cap) { Copy-Item $cap ([System.IO.Path]::ChangeExtension($link, ".txt")) }
    }
}

# ── the 8GB-safe training command (≤7200MB target) ────────────────────────────
$logDir = Join-Path $dsDir "logs"
$trainArgs = @(
    "-m", "accelerate.commands.launch",
    "--num_cpu_threads_per_process", "$cpuThreads",
    (Join-Path $sdDir "sdxl_train_network.py"),
    "--pretrained_model_name_or_path", $base,
    "--train_data_dir", $kohyaRoot,
    "--output_dir", $outDir,
    "--output_name", $outName,
    "--resolution", $Resolution,
    "--enable_bucket", "--min_bucket_reso", "512", "--max_bucket_reso", "1280", "--bucket_reso_steps", "64",
    "--network_module", "networks.lora",
    "--network_dim", "$NetworkDim", "--network_alpha", "$NetworkAlpha",
    "--network_train_unet_only",
    "--train_batch_size", "1",
    "--max_train_epochs", "$Epochs",
    "--learning_rate", "$LearningRate",
    "--lr_scheduler", "constant_with_warmup", "--lr_warmup_steps", "100",
    "--optimizer_type", "Adafactor",
    "--optimizer_args", "scale_parameter=False", "relative_step=False", "warmup_init=False",
    "--mixed_precision", "bf16", "--save_precision", "bf16",
    "--gradient_checkpointing",
    "--cache_latents", "--cache_latents_to_disk",
    "--max_data_loader_n_workers", "2", "--persistent_data_loader_workers",
    "--sdpa", "--no_half_vae",
    "--save_model_as", "safetensors", "--save_every_n_epochs", "2",
    "--caption_extension", ".txt",
    "--seed", "42",
    "--logging_dir", $logDir
)
Write-Host ""
Write-Host "Training command:" -ForegroundColor Cyan
Write-Host ("  {0} {1}" -f $py, ($trainArgs -join " "))
if ($DryRun) { Write-Host "(dry run — nothing started)"; exit 0 }

Write-Host ""
Write-Host ("Training '{0}' — expect a few hours on the 3070. Trigger word: {1}" -f $outName, $Dataset) -ForegroundColor Green
Push-Location $sdDir
try { & $py @trainArgs; $code = $LASTEXITCODE } finally { Pop-Location }
if ($code -ne 0) {
    Write-Host "Training FAILED (exit $code) — scroll up for the trainer's error." -ForegroundColor Red
    exit $code
}

# ── install the NEW file next to the others (originals untouched) ─────────────
$made = Join-Path $outDir "$outName.safetensors"
if (Test-Path $made) {
    New-Item -ItemType Directory -Force -Path $comfyLoras | Out-Null
    Copy-Item $made (Join-Path $comfyLoras "$outName.safetensors")
    Write-Host ""
    Write-Host ("DONE — {0}.safetensors saved and installed into ComfyUI loras." -f $outName) -ForegroundColor Green
    Write-Host "Use it: dashboard Create tab LoRA field, or the Face Swap 'Identity LoRA' box:" -ForegroundColor Cyan
    Write-Host ("  {0}" -f $outName)
} else {
    Write-Host "Trainer exited 0 but $made was not produced — check $logDir." -ForegroundColor Red
    exit 1
}
