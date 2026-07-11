Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " BYRDHOUSE IMAGE MODE" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Unloading all LM Studio models to free VRAM for ComfyUI..." -ForegroundColor Yellow
lms unload --all

Write-Host ""
Write-Host "Current LM Studio loaded models:" -ForegroundColor Yellow
lms ps

Write-Host ""
Write-Host "LM VRAM cleared for image generation." -ForegroundColor Green
