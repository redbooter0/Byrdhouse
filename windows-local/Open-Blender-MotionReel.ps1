param([string]$File)
$ErrorActionPreference='Stop'
$byrdConfig=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'byrdhouse-local.json') -Raw | ConvertFrom-Json
if (-not $File) {
    $byrdLatest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'media\packs\latest.json') -Raw | ConvertFrom-Json
    $File=$byrdLatest.project
}
if (-not (Test-Path -LiteralPath $byrdConfig.blender_exe)) { throw 'The configured Blender executable is missing.' }
if (-not (Test-Path -LiteralPath $File)) { throw "Blend file was not found at $File" }
Start-Process -FilePath $byrdConfig.blender_exe -ArgumentList ('"'+$File+'"') -WindowStyle Hidden
