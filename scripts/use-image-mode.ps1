# use-image-mode.ps1 (hardened) - GPU mode transition ritual (Blueprint v2 §7.1)
# The 3070 holds an LLM OR SDXL, never both. This script makes the switch
# verified instead of hopeful:
#   IMAGE mode:    unload all LM Studio models, poll nvidia-smi until VRAM is
#                  actually free, then report ready for ComfyUI batch work.
#   -Restore:      reload the operator model (config gpu.operator_model) after
#                  the batch - back to OPERATOR mode.
#Requires -Version 5.1
param(
    [switch]$Restore,
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = 'Stop'
$root = $env:BYRDHOUSE_ROOT
if (-not $root) { throw 'BYRDHOUSE_ROOT not set - run setup-gaming.ps1 first.' }
$cfg = Get-Content (Join-Path $root 'byrdhouse.config.json') -Raw | ConvertFrom-Json
$threshold = [int]$cfg.gpu.vram_free_threshold_mb

function Get-VramUsedMB {
    [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) | Select-Object -First 1)
}

if (-not (Get-Command lms -ErrorAction SilentlyContinue)) {
    throw 'lms CLI not found. Install it from LM Studio (Settings -> Developer -> CLI) - required for mode switching.'
}

if ($Restore) {
    $model = $cfg.gpu.operator_model
    if ($model -like 'CHANGE_ME*') { throw 'Set gpu.operator_model in byrdhouse.config.json first.' }
    Write-Host "OPERATOR mode: loading $model ..." -ForegroundColor Cyan
    lms load $model
    Write-Host 'OPERATOR mode ready.' -ForegroundColor Green
    exit 0
}

Write-Host 'IMAGE mode: unloading all LM Studio models...' -ForegroundColor Cyan
lms unload --all

$deadline = (Get-Date).AddSeconds($TimeoutSec)
do {
    $used = Get-VramUsedMB
    Write-Host ("  VRAM used: {0}MB (target < {1}MB)" -f $used, $threshold)
    if ($used -lt $threshold) {
        Write-Host 'IMAGE mode ready - VRAM verified free. Run your ComfyUI batch, then: use-image-mode.ps1 -Restore' -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)

Write-Error "VRAM still at ${used}MB after ${TimeoutSec}s - something besides LM Studio is holding the GPU (check nvidia-smi processes)."
exit 2
