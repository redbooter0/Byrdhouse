# Runs the audited Carey hybrid LoRA training in a user-visible console and
# keeps a durable transcript under artifacts/lora/logs.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(20, 5000)]
    [int]$Steps = 1600,
    [ValidateRange(4, 128)]
    [int]$Rank = 32,
    [string]$Root = $env:BYRDHOUSE_ROOT
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path $PSScriptRoot -Parent }
$Root = (Resolve-Path -LiteralPath $Root).Path
$logDir = Join-Path $Root 'artifacts\lora\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $logDir "carey_expanded_hybrid_r$Rank`_$($Steps)steps_$stamp.log"

Write-Host "Carey expanded-hybrid training: rank $Rank, $Steps steps" -ForegroundColor Cyan
Write-Host "Live log: $log" -ForegroundColor DarkCyan
try {
    & (Join-Path $Root 'scripts\train-carey-meina-lora.ps1') `
        -Mode expanded-hybrid `
        -Rank $Rank `
        -Steps $Steps `
        -ReplaceDataset `
        -FaceCrops `
        -TrainTextEncoder `
        -StopComfy *>&1 | Tee-Object -FilePath $log
    Write-Host "Training finished. Transcript: $log" -ForegroundColor Green
} catch {
    ($_ | Format-List * | Out-String) | Tee-Object -FilePath $log -Append
    Write-Host "Training failed. Inspect: $log" -ForegroundColor Red
    throw
}
