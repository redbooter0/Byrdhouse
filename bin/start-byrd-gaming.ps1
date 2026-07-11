param(
    [switch]$NoLMStudio
)

$ErrorActionPreference = "Continue"

$ComfyDir = "E:\ByrdHouse\Generators\ComfyUI"
$ComfyMain = "$ComfyDir\main.py"
$ComfyPython = "$ComfyDir\.venv\Scripts\python.exe"

function Test-Url {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )

    try {
        Invoke-RestMethod $Url -TimeoutSec $TimeoutSec | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Start-ComfyUI {
    Write-Host ""
    Write-Host "[1] ComfyUI" -ForegroundColor Cyan

    if (Test-Url "http://127.0.0.1:8188/system_stats") {
        Write-Host "ComfyUI already running." -ForegroundColor Green
        return
    }

    if (-not (Test-Path $ComfyDir)) {
        Write-Host "ComfyUI folder missing: $ComfyDir" -ForegroundColor Red
        return
    }

    if (-not (Test-Path $ComfyMain)) {
        Write-Host "main.py missing: $ComfyMain" -ForegroundColor Red
        return
    }

    if (-not (Test-Path $ComfyPython)) {
        Write-Host "venv python missing: $ComfyPython" -ForegroundColor Red
        return
    }

    Write-Host "Starting ComfyUI from:" -ForegroundColor Green
    Write-Host $ComfyDir -ForegroundColor Yellow

    $Cmd = "Set-Location -LiteralPath '$ComfyDir'; & '$ComfyPython' '$ComfyMain' --listen 0.0.0.0 --port 8188"
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $Cmd)

    Start-Sleep -Seconds 10

    if (Test-Url "http://127.0.0.1:8188/system_stats" 5) {
        Write-Host "ComfyUI local: YES" -ForegroundColor Green
    } else {
        Write-Host "ComfyUI local: not reachable yet. It may still be loading." -ForegroundColor Yellow
        Write-Host "Leave the ComfyUI PowerShell window open." -ForegroundColor Yellow
    }
}

function Start-LMStudio {
    Write-Host ""
    Write-Host "[2] LM Studio" -ForegroundColor Cyan

    if ($NoLMStudio) {
        Write-Host "Skipping LM Studio." -ForegroundColor Yellow
        return
    }

    if (Test-Url "http://127.0.0.1:1234/v1/models") {
        Write-Host "LM Studio server already reachable." -ForegroundColor Green
        return
    }

    $Known = @(
        "$env:LOCALAPPDATA\Programs\LM Studio\LM Studio.exe",
        "$env:LOCALAPPDATA\Programs\LMStudio\LM Studio.exe",
        "$env:ProgramFiles\LM Studio\LM Studio.exe"
    )

    $Exe = $null

    foreach ($Path in $Known) {
        if (Test-Path $Path) {
            $Exe = $Path
            break
        }
    }

    if (-not $Exe) {
        $Found = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs" -Filter "LM Studio.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1

        if ($Found) {
            $Exe = $Found.FullName
        }
    }

    if ($Exe) {
        Write-Host "Starting LM Studio:" -ForegroundColor Green
        Write-Host $Exe -ForegroundColor Yellow
        Start-Process $Exe
        Start-Sleep -Seconds 5
    } else {
        Write-Host "LM Studio executable not found automatically." -ForegroundColor Yellow
    }

    if (Test-Url "http://127.0.0.1:1234/v1/models") {
        Write-Host "LM Studio local server: YES" -ForegroundColor Green
    } else {
        Write-Host "LM Studio app may be open, but server is not active yet." -ForegroundColor Yellow
        Write-Host "Start LM Studio local server on port 1234 when needed." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " STARTING BYRDHOUSE GPU BRAIN" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

Start-ComfyUI
Start-LMStudio

Write-Host ""
Write-Host "[3] Final local checks" -ForegroundColor Cyan

if (Test-Url "http://127.0.0.1:8188/system_stats") {
    Write-Host "ComfyUI local: YES" -ForegroundColor Green
} else {
    Write-Host "ComfyUI local: NO" -ForegroundColor Red
}

if (Test-Url "http://127.0.0.1:1234/v1/models") {
    Write-Host "LM Studio local: YES" -ForegroundColor Green
} else {
    Write-Host "LM Studio local: NO" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "BYRD-GAMING startup complete." -ForegroundColor Green
