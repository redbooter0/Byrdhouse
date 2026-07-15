# bootstrap-sd-scripts.ps1 - isolated SD 1.5 LoRA trainer for BYRD-GAMING.
# This deliberately does not install packages into ComfyUI's virtualenv.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = $env:BYRDHOUSE_ROOT,
    [string]$InstallPath,
    [string]$Ref = 'v0.11.1'
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path $PSScriptRoot -Parent }
$Root = (Resolve-Path -LiteralPath $Root).Path
if (-not $InstallPath) { $InstallPath = Join-Path $Root 'Generators\sd-scripts' }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required to install sd-scripts.'
}

# Windows' py launcher may list a uv-managed 3.11 runtime but not resolve it
# through `py -3.11`.  ComfyUI already proves its base interpreter works, so
# prefer that exact Python without installing anything into ComfyUI itself.
$comfyPython = Join-Path $Root 'Generators\ComfyUI\.venv\Scripts\python.exe'
$pythonPath = $null
if (Test-Path -LiteralPath $comfyPython) {
    $basePrefix = ((& $comfyPython -c "import sys; print(sys.base_prefix)" | Select-Object -First 1).ToString()).Trim()
    $candidate = Join-Path $basePrefix 'python.exe'
    if (Test-Path -LiteralPath $candidate) { $pythonPath = $candidate }
}
if (-not $pythonPath) {
    $candidate = ((& py -0p 2>$null | Select-String -Pattern '[A-Za-z]:\\.*python\.exe$' | Select-Object -First 1).ToString() -replace '^.*?([A-Za-z]:\\.*python\.exe)$', '$1').Trim()
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $pythonPath = $candidate }
}
if (-not $pythonPath) { throw 'A Python 3.11 runtime is required for the isolated trainer.' }

if (Test-Path -LiteralPath $InstallPath) {
    if (-not (Test-Path -LiteralPath (Join-Path $InstallPath '.git'))) {
        throw "Install path exists but is not sd-scripts: $InstallPath"
    }
    $head = (& git -C $InstallPath describe --tags --always 2>$null).Trim()
    if ($head -ne $Ref) {
        throw "sd-scripts already exists at $head. Refusing to replace it automatically."
    }
} else {
    & git clone --depth 1 --branch $Ref https://github.com/kohya-ss/sd-scripts.git $InstallPath
    if ($LASTEXITCODE -ne 0) { throw 'sd-scripts clone failed.' }
}

$venvPath = Join-Path $InstallPath '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $pythonPath -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated sd-scripts virtual environment.' }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
Push-Location $InstallPath
try {
    # requirements.txt includes an editable `-e .`, so its working directory
    # must be the cloned trainer rather than the ByrdHouse application root.
    & $venvPython -m pip install --upgrade -r 'requirements.txt'
    if ($LASTEXITCODE -ne 0) { throw 'sd-scripts Python dependencies failed to install.' }
} finally {
    Pop-Location
}

& $venvPython -c "import torch; assert torch.cuda.is_available(); print('torch=' + torch.__version__); print('gpu=' + torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw 'The isolated trainer cannot see the RTX GPU.' }
$env:PYTHONUTF8 = '1'
& $venvPython (Join-Path $InstallPath 'train_network.py') --help *> $null
if ($LASTEXITCODE -ne 0) { throw 'sd-scripts train_network.py smoke test failed.' }

Write-Host "sd-scripts $Ref is ready at $InstallPath" -ForegroundColor Green
