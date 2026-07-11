$Root = "E:\ByrdHouse"

Write-Host ""
Write-Host "====================================="
Write-Host " BYRD-GAMING MEDIA VERIFY"
Write-Host "====================================="
Write-Host ""

$Checks = @(
    "$Root\Media",
    "$Root\Media\Incoming",
    "$Root\Media\Processing",
    "$Root\Media\Done",
    "$Root\Outputs",
    "$Root\Outputs\Images",
    "$Root\Outputs\Videos",
    "$Root\Outputs\Logs",
    "$Root\Media\process-media-jobs.ps1"
)

foreach ($Path in $Checks) {
    if (Test-Path $Path) {
        Write-Host "OK      $Path"
    } else {
        Write-Host "MISSING $Path"
    }
}

Write-Host ""
Write-Host "Incoming Jobs:"
Get-ChildItem "$Root\Media\Incoming" -File -ErrorAction SilentlyContinue |
Select-Object FullName, LastWriteTime

Write-Host ""
Write-Host "Done Jobs:"
Get-ChildItem "$Root\Media\Done" -File -ErrorAction SilentlyContinue |
Sort-Object LastWriteTime -Descending |
Select-Object -First 10 FullName, LastWriteTime

Write-Host ""
Write-Host "====================================="
Write-Host " VERIFY COMPLETE"
Write-Host "====================================="
Write-Host ""
