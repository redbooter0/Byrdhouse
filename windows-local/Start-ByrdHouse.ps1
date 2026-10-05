param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$byrdRoot=$PSScriptRoot
$cfg=Get-Content -LiteralPath (Join-Path $byrdRoot 'byrdhouse-local.json') -Raw | ConvertFrom-Json
if($cfg.python_site_packages) {
    if(-not (Test-Path -LiteralPath $cfg.python_site_packages -PathType Container)) {
        throw 'Configured Python dependency folder is missing.'
    }
    $env:PYTHONPATH=$cfg.python_site_packages
}
function Test-ByrdProcess($name,$expected) {
    $pidFile=Join-Path $byrdRoot "logs\$name.pid"
    if(-not (Test-Path -LiteralPath $pidFile)){return $false}
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content -LiteralPath $pidFile))"
    return ($process -and $process.CommandLine.Contains($expected))
}
function Test-LocalService($url) {
    try { $null=Invoke-RestMethod -Uri $url -TimeoutSec 3; return $true } catch { return $false }
}
$trainingActive=Test-ByrdProcess 'training' (Join-Path $byrdRoot 'training\train_carey.py')
if(-not $trainingActive -and -not (Test-ByrdProcess 'comfy' (Join-Path $cfg.comfy_dir 'main.py')) -and -not (Test-LocalService ($cfg.comfy_url+'/system_stats'))) {
    $args=@('-u',('"'+$cfg.comfy_dir+'\main.py"'),'--listen',([uri]$cfg.comfy_url).Host,'--port',([uri]$cfg.comfy_url).Port,'--disable-api-nodes','--extra-model-paths-config',('"'+$byrdRoot+'\extra-model-paths.yaml"'),'--output-directory',('"'+$byrdRoot+'\media\comfy"'))
    if($null -ne $cfg.comfy_cache_active_gb -and $null -ne $cfg.comfy_cache_inactive_gb) {
        $args += @('--cache-ram', [string]$cfg.comfy_cache_active_gb, [string]$cfg.comfy_cache_inactive_gb)
    }
    if($cfg.comfy_disable_async_offload) { $args += '--disable-async-offload' }
    if($cfg.comfy_disable_dynamic_vram) { $args += '--disable-dynamic-vram' }
    $proc=Start-Process -FilePath $cfg.python -ArgumentList $args -WorkingDirectory $cfg.comfy_dir -WindowStyle Hidden -RedirectStandardOutput "$byrdRoot\logs\comfy.out.log" -RedirectStandardError "$byrdRoot\logs\comfy.err.log" -PassThru
    $proc.Id | Set-Content "$byrdRoot\logs\comfy.pid"
}
$studioUrl='http://'+$cfg.studio_host+':'+$cfg.studio_port
if(-not (Test-ByrdProcess 'studio' (Join-Path $byrdRoot 'studio\server.py')) -and -not (Test-LocalService ($studioUrl+'/api/jobs'))) {
    $proc=Start-Process -FilePath $cfg.python -ArgumentList @('-u',('"'+$byrdRoot+'\studio\server.py"'),'--config',('"'+$byrdRoot+'\byrdhouse-local.json"')) -WorkingDirectory $byrdRoot -WindowStyle Hidden -RedirectStandardOutput "$byrdRoot\logs\studio.out.log" -RedirectStandardError "$byrdRoot\logs\studio.err.log" -PassThru
    $proc.Id | Set-Content "$byrdRoot\logs\studio.pid"
}
if(-not $NoBrowser) { Start-Process $studioUrl }
Write-Output "ByrdHouse Studio: $studioUrl"
