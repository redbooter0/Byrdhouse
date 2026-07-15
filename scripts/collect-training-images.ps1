<#
collect-training-images.ps1 — Face Lab step 1 (docs/FACE_LAB.md).

Finds your recent generated images (ComfyUI output + belt artifacts) and MOVES
them into the training dataset folder so train-lora.ps1 can use them:

    %BYRDHOUSE_ROOT%\training\datasets\<Name>\img\

Usage (on BYRD-GAMING):
    powershell -ExecutionPolicy Bypass -File scripts\collect-training-images.ps1
    # defaults: newest 300 images -> training\datasets\carey_face\img

    -Name carey_face   dataset name (also the LoRA trigger word)
    -Newest 300        how many of the most recent images to take
    -From <dir,...>    extra folders to search (e.g. a manual export folder)
    -Copy              copy instead of move (originals stay put)
    -MinKB 200         skip files smaller than this (previews/temp junk)
    -DryRun            show what WOULD move, touch nothing

Sidecar .json cards travel with their image so the dataset keeps its metadata.
A manifest.json in the dataset folder records where every file came from.
#>
param(
    [string]$Name = "carey_face",
    [int]$Newest = 300,
    [string[]]$From = @(),
    [switch]$Copy,
    [int]$MinKB = 200,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

if (-not $env:BYRDHOUSE_ROOT) {
    Write-Host "BYRDHOUSE_ROOT is not set — run setup or open a new shell." -ForegroundColor Red
    exit 1
}
$root = $env:BYRDHOUSE_ROOT
$cfg = Get-Content (Join-Path $root "byrdhouse.config.json") -Raw | ConvertFrom-Json

# ── where to look: ComfyUI output, belt artifacts, anything passed in ─────────
$searchDirs = New-Object System.Collections.ArrayList
if ($cfg.startup -and $cfg.startup.comfyui_dir) {
    [void]$searchDirs.Add((Join-Path $cfg.startup.comfyui_dir "ComfyUI\output"))
}
[void]$searchDirs.Add((Join-Path $root "Generators\ComfyUI\output"))
[void]$searchDirs.Add((Join-Path $root "artifacts"))
# generated identity batches (e.g. generated_real_skit_scenes) live in SUBFOLDERS
# of the profile references — include those, but never the references root
# itself: front.jpg etc. must stay put or FaceID auto-wiring breaks.
$refRoot = Join-Path $root "profiles\me\references"
if (Test-Path $refRoot) {
    Get-ChildItem $refRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "generated*" } |
        ForEach-Object { [void]$searchDirs.Add($_.FullName) }
}
foreach ($f in $From) { [void]$searchDirs.Add($f) }
$searchDirs = $searchDirs | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

$datasetsRel = "training/datasets"
if ($cfg.training -and $cfg.training.datasets_dir) { $datasetsRel = $cfg.training.datasets_dir }
$destDir = Join-Path $root (Join-Path ($datasetsRel -replace "/", "\") (Join-Path $Name "img"))

Write-Host ""
Write-Host "ByrdHouse dataset collector" -ForegroundColor Cyan
Write-Host "  dataset : $destDir"
Write-Host "  searching:"
$searchDirs | ForEach-Object { Write-Host "    $_" }
if (-not $searchDirs) {
    Write-Host "  no source folders exist — pass one with -From D:\path\to\images" -ForegroundColor Red
    exit 1
}

# ── gather candidates: real generated images only ─────────────────────────────
$exts = @(".png", ".jpg", ".jpeg", ".webp")
$minBytes = $MinKB * 1KB
$candidates = foreach ($dir in $searchDirs) {
    Get-ChildItem -Path $dir -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $exts -contains $_.Extension.ToLower() -and
        $_.Length -ge $minBytes -and
        $_.FullName -notmatch "\\training\\" -and       # never re-collect a dataset
        $_.FullName -notmatch "\\_sources\\" -and        # uploaded refs, not generations
        $_.Name -notmatch "_final\.png$"                 # composited thumbnails have text
    }
}
$picked = $candidates | Sort-Object LastWriteTime -Descending |
    Select-Object -First $Newest
if (-not $picked) {
    Write-Host "  found nothing to collect — check the folders above or use -From/-MinKB" -ForegroundColor Red
    exit 1
}
Write-Host ("  found {0} candidate(s); taking the newest {1}" -f @($candidates).Count, @($picked).Count)

# ── move (or copy) with collision-safe names + manifest ───────────────────────
if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
$verb = if ($Copy) { "copy" } else { "move" }
$manifest = New-Object System.Collections.ArrayList
$i = 0
foreach ($f in $picked) {
    $i++
    $destName = $f.Name
    if (Test-Path (Join-Path $destDir $destName)) {
        $destName = "{0:d4}_{1}" -f $i, $f.Name
    }
    $destPath = Join-Path $destDir $destName
    if ($DryRun) {
        Write-Host ("  [dry] {0} {1}" -f $verb, $f.FullName)
    } else {
        if ($Copy) { Copy-Item $f.FullName $destPath } else { Move-Item $f.FullName $destPath }
        $card = "$($f.FullName).json"                    # sidecar rides along
        if (Test-Path $card) {
            if ($Copy) { Copy-Item $card "$destPath.json" -ErrorAction SilentlyContinue }
            else { Move-Item $card "$destPath.json" -ErrorAction SilentlyContinue }
        }
    }
    [void]$manifest.Add(@{ from = $f.FullName; to = $destName
                           modified = $f.LastWriteTime.ToString("s"); bytes = $f.Length })
}

if (-not $DryRun) {
    @{ dataset = $Name; collected = $manifest.Count; action = $verb
       date = (Get-Date).ToString("s"); host = $env:COMPUTERNAME
       files = $manifest } |
        ConvertTo-Json -Depth 4 | Set-Content (Join-Path (Split-Path $destDir) "manifest.json") -Encoding UTF8
}

Write-Host ""
Write-Host ("DONE — {0} image(s) {1}d into the '{2}' dataset." -f $manifest.Count, $verb, $Name) -ForegroundColor Green
Write-Host "Next step (new LoRA file, never overwrites the old one):" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\train-lora.ps1 -Dataset $Name"
