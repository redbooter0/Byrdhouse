param([Parameter(Mandatory=$true)][string]$PackPath, [switch]$NoWindow)
$ErrorActionPreference = 'Stop'
$byrdCfg = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'byrdhouse-local.json') -Raw | ConvertFrom-Json
$byrdPack = (Resolve-Path -LiteralPath $PackPath).Path
if ([IO.Path]::GetExtension($byrdPack) -eq '.zip') {
    $byrdDestination = Join-Path $PSScriptRoot ('media\packs\' + [IO.Path]::GetFileNameWithoutExtension($byrdPack))
    $byrdDestination = [IO.Path]::GetFullPath($byrdDestination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $byrdArchive = [IO.Compression.ZipFile]::OpenRead($byrdPack)
    try {
        foreach ($byrdEntry in $byrdArchive.Entries) {
            $byrdTarget = [IO.Path]::GetFullPath((Join-Path $byrdDestination $byrdEntry.FullName))
            if (-not $byrdTarget.StartsWith($byrdDestination + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid path inside pack.' }
        }
    } finally { $byrdArchive.Dispose() }
    Expand-Archive -LiteralPath $byrdPack -DestinationPath $byrdDestination -Force
    $byrdPack = $byrdDestination
}
if (-not (Test-Path -LiteralPath (Join-Path $byrdPack 'manifest.json'))) { throw 'Choose an extracted Carey pack or its ZIP.' }
if (-not (Test-Path -LiteralPath $byrdCfg.blender_exe)) { throw 'The configured Blender executable is missing.' }
& $byrdCfg.blender_exe --background --python (Join-Path $PSScriptRoot 'studio\pack_to_blender.py') -- $byrdPack
if ($LASTEXITCODE -ne 0) { throw 'Blender could not build the project.' }
$byrdProject = Join-Path $byrdPack 'Carey-animation-stills.blend'
$byrdLatest = @{ purpose='Latest editable Carey still animatic'; project=$byrdProject; pack=$byrdPack } | ConvertTo-Json
$byrdLatest | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'media\packs\latest.json') -Encoding UTF8
if (-not $NoWindow) { Start-Process -FilePath $byrdCfg.blender_exe -ArgumentList ('"' + $byrdProject + '"') -WindowStyle Hidden }
Write-Output $byrdProject
