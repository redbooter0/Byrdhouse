$ErrorActionPreference='Stop'
$byrdRoot=$PSScriptRoot
$cfg=Get-Content "$byrdRoot\byrdhouse-local.json" -Raw | ConvertFrom-Json
foreach($name in 'studio','comfy') {
    $pidFile=Join-Path $byrdRoot "logs\$name.pid"
    if(Test-Path -LiteralPath $pidFile) {
        $byrdPid=[int](Get-Content -LiteralPath $pidFile)
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$byrdPid"
        $expected=if($name -eq 'studio'){Join-Path $byrdRoot 'studio\server.py'}else{Join-Path $cfg.comfy_dir 'main.py'}
        if($process -and $process.CommandLine.Contains($expected)) {
            Stop-Process -Id $byrdPid -Force
            foreach($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$byrdPid")) {
                if($child.Name -eq 'python.exe') { Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue }
            }
        }
        Remove-Item -LiteralPath $pidFile
    }
}
