# tune-gaming.ps1 - one-shot performance posture for BYRD-GAMING
# (i9-10850K / 32GB DDR4 / RTX 3070 8GB). Idempotent; run as admin once.
#   powershell -ExecutionPolicy Bypass -File scripts\tune-gaming.ps1
#Requires -Version 5.1
$ErrorActionPreference = 'Continue'

Write-Host "`nByrdHouse GAMING tune - $env:COMPUTERNAME`n" -ForegroundColor Cyan

# 1. High Performance power plan (10850K boost bins stay available; no core parking)
$high = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
powercfg /setactive $high 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host '  [ok]      power plan: High performance' -ForegroundColor Green }
else { Write-Host '  [warn]    could not set power plan (run as admin)' -ForegroundColor Yellow }

# 2. GPU report - the 3070 should be idle near 0% VRAM between jobs
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu,clocks.sm --format=csv,noheader |
        ForEach-Object { Write-Host "  [gpu]     $_" }
} else {
    Write-Host '  [missing] nvidia-smi' -ForegroundColor Yellow
}

# 3. RAM + pagefile sanity (SDXL peaks ~14GB system RAM with batch 4; 32GB is comfortable)
$os = Get-CimInstance Win32_OperatingSystem
$ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
Write-Host "  [ram]     $ramGB GB total, $([math]::Round($os.FreePhysicalMemory / 1MB, 1)) GB free"
$pf = Get-CimInstance Win32_PageFileUsage
if ($pf) { $pf | ForEach-Object { Write-Host "  [pagefile] $($_.Name)  $($_.AllocatedBaseSize) MB" } }

# 4. XMP reminder - DDR4 running at 2133 MT/s means XMP is off in BIOS
$speed = (Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1).ConfiguredClockSpeed
Write-Host "  [ram]     configured speed: $speed MT/s $(if ($speed -le 2400) {'- enable XMP in BIOS for free bandwidth'} else {'(XMP looks active)'})"

Write-Host "`n  Manual once-overs (see docs/PERFORMANCE.md):" -ForegroundColor Cyan
Write-Host '   - LM Studio > model settings: GPU offload = MAX, context 8k, keep-in-memory OFF'
Write-Host '   - Windows Game Mode ON; Hardware-accelerated GPU scheduling ON'
Write-Host '   - Pagefile on the NVMe drive, system managed'
