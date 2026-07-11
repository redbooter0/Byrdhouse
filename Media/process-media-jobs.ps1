$Incoming = "E:\ByrdHouse\Media\Incoming"
$Processing = "E:\ByrdHouse\Media\Processing"
$Done = "E:\ByrdHouse\Media\Done"
$Logs = "E:\ByrdHouse\Outputs\Logs"

New-Item -ItemType Directory -Force -Path $Incoming, $Processing, $Done, $Logs | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = "$Logs\media-router_$Timestamp.log"

"ByrdHouse Media Router Run: $Timestamp" | Set-Content $LogPath -Encoding UTF8

$Jobs = Get-ChildItem $Incoming -Filter *.json -File -ErrorAction SilentlyContinue

if (-not $Jobs) {
    "No media jobs found." | Add-Content $LogPath
    Write-Host "No media jobs found."
    Write-Host "Log: $LogPath"
    exit
}

foreach ($Job in $Jobs) {
    $ProcessingPath = Join-Path $Processing $Job.Name
    Move-Item $Job.FullName $ProcessingPath -Force
    "Moved to processing: $ProcessingPath" | Add-Content $LogPath

    $Content = Get-Content $ProcessingPath -Raw
    "Job content:" | Add-Content $LogPath
    $Content | Add-Content $LogPath

    $DonePath = Join-Path $Done $Job.Name
    Move-Item $ProcessingPath $DonePath -Force
    "Marked done: $DonePath" | Add-Content $LogPath

    Write-Host "Processed job skeleton:"
    Write-Host $DonePath
}

Write-Host "Log: $LogPath"
