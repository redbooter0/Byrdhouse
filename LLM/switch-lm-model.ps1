param(
    [Parameter(Mandatory=$true)]
    [string]$Model,

    [string]$Gpu = "0.75",

    [int]$ContextLength = 8192
)

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " BYRDHOUSE LM MODEL SWITCHER" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "[1] Starting LM Studio server..." -ForegroundColor Yellow
lms server start

Write-Host ""
Write-Host "[2] Unloading currently loaded models..." -ForegroundColor Yellow
lms unload --all

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[3] Loading requested model..." -ForegroundColor Yellow
Write-Host "Model: $Model" -ForegroundColor Green
Write-Host "GPU:   $Gpu" -ForegroundColor Green
Write-Host "Ctx:   $ContextLength" -ForegroundColor Green

lms load $Model --gpu=$Gpu --context-length=$ContextLength

Write-Host ""
Write-Host "[4] Loaded model status..." -ForegroundColor Yellow
lms ps

