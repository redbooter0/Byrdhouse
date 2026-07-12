[CmdletBinding()]
param(
    [string]$ByrdHouseRoot,
    [string]$ComfyUIRoot
)

$ErrorActionPreference = 'Stop'

if (-not $ByrdHouseRoot) {
    if ($env:BYRDHOUSE_ROOT) { $ByrdHouseRoot = $env:BYRDHOUSE_ROOT }
    else { $ByrdHouseRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
}
$cfg = Get-Content (Join-Path $ByrdHouseRoot 'byrdhouse.config.json') -Raw | ConvertFrom-Json
if (-not $ComfyUIRoot) { $ComfyUIRoot = Join-Path $ByrdHouseRoot 'Generators\ComfyUI' }

$sourceDir = Join-Path $ByrdHouseRoot 'workflows\flux2_klein'
$workflowDir = Join-Path $ByrdHouseRoot 'Images\Workflows'
New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

$files = @{
    'safe_first_run.json'          = 'ByrdHouse_Flux2_Klein_3070_SAFE_FIRST_RUN.json'
    'production_all_in_one.json'   = 'ByrdHouse_Flux2_Klein_3070_PRODUCTION_ALL_IN_ONE.json'
    'master_operator.json'         = 'ByrdHouse_Flux2_Klein_MASTER_OPERATOR.json'
    'manifest.json'                = 'byrdhouse_flux2_klein_manifest.json'
    'api_adapter.py'               = 'byrdhouse_flux2_klein_api_adapter.py'
}

foreach ($src in $files.Keys) {
    $source = Join-Path $sourceDir $src
    if (-not (Test-Path $source)) { throw "Source file missing: $source" }
    Copy-Item $source (Join-Path $workflowDir $files[$src]) -Force
    Write-Host "COPIED  $($files[$src])" -ForegroundColor Green
}

$modelRoot = Join-Path $ComfyUIRoot 'models'
$requiredModels = @(
    'flux-2-klein-9b-fp8.safetensors',
    'qwen_3_8b_fp8mixed.safetensors',
    'flux2-vae.safetensors',
    '4x_foolhardy_Remacri.pth'
)

Write-Host "`nMODEL CHECK" -ForegroundColor Cyan
if (-not (Test-Path $modelRoot)) {
    Write-Warning "ComfyUI model folder not found: $modelRoot"
} else {
    $inventory = Get-ChildItem $modelRoot -Recurse -File -ErrorAction SilentlyContinue
    foreach ($name in $requiredModels) {
        $match = $inventory | Where-Object Name -eq $name | Select-Object -First 1
        if ($match) {
            Write-Host "YES  $name -> $($match.FullName)" -ForegroundColor Green
        } else {
            Write-Host "NO   $name" -ForegroundColor Yellow
        }
    }
}

Write-Host "`nInstalled to: $workflowDir" -ForegroundColor Cyan
Write-Host 'Load SAFE_FIRST_RUN in ComfyUI first. SeedVR2 remains bypassed.' -ForegroundColor Cyan
