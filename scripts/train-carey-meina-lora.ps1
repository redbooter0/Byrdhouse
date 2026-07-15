# train-carey-meina-lora.ps1 - explicit local training entrypoint for BYRD-GAMING.
# The trainer stays isolated from ComfyUI. It never activates a LoRA in the
# production image lane; candidates are written under artifacts/lora first.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('identity', 'studio-core', 'anime-mix', 'expanded-hybrid')]
    [string]$Mode = 'identity',
    [int]$Steps = 900,
    [ValidateRange(4, 128)]
    [int]$Rank = 16,
    [int]$MaxAnime = 18,
    [switch]$IncludeOptionalReal,
    [switch]$PrepareOnly,
    [switch]$ReplaceDataset,
    [switch]$FaceCrops,
    [switch]$TrainTextEncoder,
    [switch]$SmokeTest,
    [switch]$StopComfy,
    [string]$Root = $env:BYRDHOUSE_ROOT
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path $PSScriptRoot -Parent }
$Root = (Resolve-Path -LiteralPath $Root).Path
$comfyPython = Join-Path $Root 'Generators\ComfyUI\.venv\Scripts\python.exe'
$trainerRoot = Join-Path $Root 'Generators\sd-scripts'
$trainerPython = Join-Path $trainerRoot '.venv\Scripts\python.exe'
$accelerate = Join-Path $trainerRoot '.venv\Scripts\accelerate.exe'
$checkpoint = Join-Path $Root 'Generators\ComfyUI\models\checkpoints\Meina V5.1 - Baked VAE.safetensors'

foreach ($path in @($comfyPython, $trainerPython, $accelerate, $checkpoint)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing $path. Run scripts\bootstrap-sd-scripts.ps1 first."
    }
}

$prepareArgs = @((Join-Path $Root 'scripts\prepare-carey-lora-dataset.py'), '--root', $Root,
                 '--mode', $Mode)
if ($Mode -eq 'anime-mix') { $prepareArgs += @('--max-anime', $MaxAnime) }
if ($IncludeOptionalReal) { $prepareArgs += '--include-optional-real' }
if ($ReplaceDataset) { $prepareArgs += '--replace' }
& $comfyPython @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Dataset staging failed.' }
if ($FaceCrops) {
    & $trainerPython (Join-Path $Root 'scripts\build-carey-face-crops.py') --root $Root --dataset-mode $Mode --replace
    if ($LASTEXITCODE -ne 0) { throw 'Face-crop staging failed.' }
}
if ($PrepareOnly) { exit 0 }

if ($SmokeTest) { $Steps = 20 }
if ($Steps -lt 1) { throw 'Steps must be positive.' }

$cfg = Get-Content -LiteralPath (Join-Path $Root 'byrdhouse.config.json') -Raw | ConvertFrom-Json
$comfyRunning = $false
try {
    $null = Invoke-WebRequest -Uri "$($cfg.services.comfyui)/system_stats" -UseBasicParsing -TimeoutSec 3
    $comfyRunning = $true
} catch {
    # The request failed, which is the desired precondition: ComfyUI is down.
}
if ($comfyRunning) {
    if (-not $StopComfy) {
        throw 'ComfyUI is running. Re-run with -StopComfy, or stop it manually, so the 8 GB RTX 3070 has enough VRAM.'
    }
    $comfyProcesses = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -like '*ComfyUI*' -and $_.CommandLine -like '*main.py*'
    }
    if (-not $comfyProcesses) {
        throw 'ComfyUI answered but its process could not be identified safely. Stop it manually, then retry.'
    }
    $comfyProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-WebRequest -Uri "$($cfg.services.comfyui)/system_stats" -UseBasicParsing -TimeoutSec 1
        } catch {
            break
        }
    }
    $comfyStillRunning = $false
    try {
        $null = Invoke-WebRequest -Uri "$($cfg.services.comfyui)/system_stats" -UseBasicParsing -TimeoutSec 1
        $comfyStillRunning = $true
    } catch {
        # A connection failure is the expected proof that ComfyUI has stopped.
    }
    if ($comfyStillRunning) {
        throw 'ComfyUI did not stop; refusing to share the 8 GB GPU with training.'
    }
    Write-Host 'ComfyUI stopped; the RTX 3070 is reserved for LoRA training.' -ForegroundColor Yellow
}

if (Get-Command lms -ErrorAction SilentlyContinue) {
    # LM Studio's CLI writes "No models to unload" to stderr even on success,
    # which is unsafe under strict PowerShell error handling. It has no loaded
    # model here, so leave the app alone rather than risking a false training failure.
    Write-Host 'LM Studio detected; no loaded model will be touched before training.' -ForegroundColor DarkGray
}

$outputDir = Join-Path $Root 'artifacts\lora\candidates'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$name = "carey_meina_sd15_$($Mode.Replace('-', '_'))_r$Rank`_$stamp"
$datasetRoot = Join-Path $Root "profiles\me\lora_dataset\$Mode"
$warmup = [Math]::Min(100, [Math]::Max(1, [int]($Steps / 10)))

$trainArgs = @(
    'launch', '--num_cpu_threads_per_process', '8', '--mixed_precision', 'fp16', (Join-Path $trainerRoot 'train_network.py'),
    '--pretrained_model_name_or_path', $checkpoint,
    '--train_data_dir', $datasetRoot,
    '--output_dir', $outputDir,
    '--output_name', $name,
    '--save_model_as', 'safetensors',
    '--network_module', 'networks.lora',
    '--network_dim', "$Rank", '--network_alpha', "$Rank",
    '--resolution', '512,512', '--enable_bucket', '--min_bucket_reso', '384',
    '--max_bucket_reso', '768', '--bucket_reso_steps', '64',
    '--caption_extension', '.txt',
    '--train_batch_size', '1', '--max_train_steps', "$Steps",
    '--unet_lr', '1e-4', '--lr_scheduler', 'cosine', '--lr_warmup_steps', "$warmup",
    '--mixed_precision', 'fp16', '--save_precision', 'fp16',
    '--cache_latents', '--cache_latents_to_disk',
    '--gradient_checkpointing', '--sdpa', '--optimizer_type', 'AdamW',
    '--save_every_n_steps', '200', '--save_state'
)

if ($TrainTextEncoder) {
    # The custom identity trigger needs a learned CLIP association as well as
    # U-Net features.  Keep this deliberately conservative for the 8 GB 3070.
    $trainArgs += @('--text_encoder_lr', '5e-5')
} else {
    $trainArgs += '--network_train_unet_only'
}

$trainScope = if ($TrainTextEncoder) { 'U-Net + text encoder' } else { 'U-Net only' }
Write-Host "Training $name for $Steps step(s) on the local RTX 3070 ($trainScope)..." -ForegroundColor Cyan
$env:PYTHONUTF8 = '1'
Push-Location $trainerRoot
try {
    # accelerate writes its non-fatal default-value notice to stderr. Under the
    # script's strict error preference that is otherwise promoted to a false
    # terminating error, so evaluate the real native exit code explicitly.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $accelerate @trainArgs
        $accelerateExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($accelerateExitCode -ne 0) { throw "LoRA training exited with $accelerateExitCode." }
} finally {
    Pop-Location
}

Write-Host "Candidate saved in $outputDir" -ForegroundColor Green
Write-Host 'It is intentionally not active in ComfyUI yet. Validate it on all four targets before promotion.' -ForegroundColor Yellow
