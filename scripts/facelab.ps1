<#
facelab.ps1 — ONE entry point for the whole Face Lab (docs/FACE_OPS.md).

Every lane, by hand, for the founder or Codex:

    powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 <command> [options]

    preflight                       what's installed / what's missing (told exactly)
    examine  -Image X [-Quick]      the examiner: verdicts, flags, feature plan
                                    (thorough scrutiny is the default)
    quality  -Image X [-Preset gojo] [-FaceIndex 0] [-Lora name]
                                    THE MAIN LANE: examiner gate -> CPU mesh seed ->
                                    cleanup -> composite (recipe anime_face_zone_edit)
    zone     -Image X -Mask M [-Lora name] [-Prompt "..."]
                                    backup: GPU edits ONLY inside your mask
    auto     -Image X [-Lora name] [-Prompt "..."]
                                    backup: detector finds the face, redraws as you
    swap     -Image X [-Blend 0.35] backup (private experiments): ReActor + blend
    collect  [-Dataset carey_face]  move newest generated images into the dataset
    train    [-Dataset carey_face]  new versioned LoRA (never overwrites)
    help                            this text

All 100% local. GPU lanes need ComfyUI running (start-byrdhouse.ps1).
#>
param(
    [Parameter(Position = 0)][string]$Command = "help",
    [string]$Image,
    [string]$Mask,
    [string]$Preset = "auto",
    [string]$Workflow,
    [int]$FaceIndex = 0,
    [string]$Lora,
    [string]$Prompt,
    [double]$Blend = 0.35,
    [double]$Denoise = 0,
    [string]$Dataset = "carey_face",
    [string]$Project = "careyrpg",
    [string]$Purpose = "",
    [switch]$Quick
)
$ErrorActionPreference = "Stop"
if (-not $env:BYRDHOUSE_ROOT) {
    Write-Host "BYRDHOUSE_ROOT is not set — run setup or open a new shell." -ForegroundColor Red
    exit 1
}
$root = $env:BYRDHOUSE_ROOT
$sysPython = "python"
$comfyPython = Join-Path $root "Generators\ComfyUI\.venv\Scripts\python.exe"
if (-not (Test-Path $comfyPython)) { $comfyPython = $sysPython }
$zoneScript = Join-Path $root "scripts\byrdfacezone.py"
$byrdimage = Join-Path $root "scripts\byrdimage.py"
$preflightPy = Join-Path $root "scripts\facelab_preflight.py"

function Need-Image {
    if (-not $Image) { Write-Host "-Image <path> is required for this command" -ForegroundColor Red; exit 1 }
    if (-not (Test-Path $Image)) { Write-Host "image not found: $Image" -ForegroundColor Red; exit 1 }
}
if (-not $Purpose) { $Purpose = "$Command via facelab.ps1" }

switch ($Command.ToLower()) {
    "preflight" {
        & $sysPython $preflightPy
        exit $LASTEXITCODE
    }
    "examine" {
        Need-Image
        $args2 = @($zoneScript, "--root", $root, "analyze", "--input", $Image)
        if (-not $Quick) { $args2 += "--thorough" }
        & $comfyPython @args2
        exit $LASTEXITCODE
    }
    "quality" {
        Need-Image
        $args2 = @($byrdimage, "--edit-face-zone", $Image, "--face-preset", $Preset,
                   "--face-index", "$FaceIndex", "--project", $Project, "--purpose", $Purpose)
        if ($Workflow) { $args2 += @("--workflow", $Workflow) }
        if ($Lora) { $args2 += @("--lora", $Lora) }
        & $sysPython @args2
        exit $LASTEXITCODE
    }
    "zone" {
        Need-Image
        if (-not $Mask) { Write-Host "-Mask <path> is required (white = change zone)" -ForegroundColor Red; exit 1 }
        $args2 = @($byrdimage, "--swap-target", $Image, "--swap-mask", $Mask,
                   "--project", $Project, "--purpose", $Purpose)
        if ($Lora) { $args2 += @("--lora", $Lora) }
        if ($Prompt) { $args2 += @("--prompt", $Prompt) }
        if ($Denoise -gt 0) { $args2 += @("--denoise", "$Denoise") }
        & $sysPython @args2
        exit $LASTEXITCODE
    }
    "auto" {
        Need-Image
        $args2 = @($byrdimage, "--swap-target", $Image, "--auto",
                   "--project", $Project, "--purpose", $Purpose)
        if ($Lora) { $args2 += @("--lora", $Lora) }
        if ($Prompt) { $args2 += @("--prompt", $Prompt) }
        & $sysPython @args2
        exit $LASTEXITCODE
    }
    "swap" {
        Need-Image
        & $sysPython $preflightPy --run $Image --blend $Blend
        exit $LASTEXITCODE
    }
    "collect" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\collect-training-images.ps1") -Name $Dataset
        exit $LASTEXITCODE
    }
    "train" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\train-lora.ps1") -Dataset $Dataset
        exit $LASTEXITCODE
    }
    default {
        Get-Content $PSCommandPath | Select-Object -First 28 | ForEach-Object { $_ -replace "^#? ?", "" }
    }
}
