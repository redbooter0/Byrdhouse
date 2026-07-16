$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " STARTING COMFYUI - RTX 3070 OPTIMIZED" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

$ComfyRoot = "E:\ByrdHouse\Generators\ComfyUI"
$Python = "E:\ByrdHouse\Generators\ComfyUI\.venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $ComfyRoot "main.py"))) {
    Write-Host "ComfyUI main.py not found at:" -ForegroundColor Red
    Write-Host $ComfyRoot -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $Python)) {
    Write-Host "ComfyUI .venv Python not found at:" -ForegroundColor Red
    Write-Host $Python -ForegroundColor Yellow
    exit 1
}

Set-Location $ComfyRoot

Write-Host ""
Write-Host "ComfyUI root:" -ForegroundColor Green
Write-Host $ComfyRoot -ForegroundColor Yellow

Write-Host ""
Write-Host "Using ComfyUI Python:" -ForegroundColor Green
Write-Host $Python -ForegroundColor Yellow

Write-Host ""
Write-Host "Checking required imports..." -ForegroundColor Cyan

$Missing = $false

try {
    & $Python -c "import sqlalchemy; print('SQLAlchemy OK')"
} catch {
    Write-Host "SQLAlchemy missing." -ForegroundColor Yellow
    $Missing = $true
}

try {
    & $Python -c "import alembic; print('Alembic OK')"
} catch {
    Write-Host "Alembic missing." -ForegroundColor Yellow
    $Missing = $true
}

try {
    & $Python -c "import comfy_aimdo; print('comfy_aimdo OK')"
} catch {
    Write-Host "comfy_aimdo missing." -ForegroundColor Yellow
    $Missing = $true
}

if ($Missing) {
    Write-Host ""
    Write-Host "Installing/updating ComfyUI requirements into the correct .venv..." -ForegroundColor Cyan
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r "$ComfyRoot\requirements.txt"
}

Write-Host ""
Write-Host "Starting ComfyUI on LAN..." -ForegroundColor Cyan
Write-Host "LAN URL: http://15.2.2.5:8188" -ForegroundColor Yellow
Write-Host ""

$Args = @(
    "main.py",
    "--listen", "0.0.0.0",
    "--port", "8188",
    "--cuda-device", "0",
    "--cuda-malloc",
    "--enable-dynamic-vram",
    "--reserve-vram", "0.8",
    "--preview-method", "auto",
    "--preview-size", "512"
)

& $Python @Args
