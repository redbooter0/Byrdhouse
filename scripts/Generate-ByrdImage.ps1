param(
    [Parameter(Mandatory=$true)]
    [string]$Prompt,

    [string]$Negative = "text, watermark, blurry, low quality, distorted, deformed, bad anatomy",

    [string]$ComfyUrl = "http://127.0.0.1:8188",

    [string]$WorkflowPath = "E:\ByrdHouse\Images\Workflows\byrdhouse_sdxl_api_v1.json",

    [string]$ComfyRoot = "E:\ByrdHouse\Generators\ComfyUI"
)

$ErrorActionPreference = "Stop"

Write-Host "`n[1] Checking ComfyUI..." -ForegroundColor Cyan
Invoke-RestMethod "$ComfyUrl/system_stats" | Out-Null
Write-Host "ComfyUI API reachable." -ForegroundColor Green

Write-Host "`n[2] Loading ByrdHouse workflow..." -ForegroundColor Cyan
$workflow = Get-Content $WorkflowPath -Raw | ConvertFrom-Json

$clipNodes = @($workflow.PSObject.Properties | Where-Object {
    $_.Value.class_type -eq "CLIPTextEncode" -and
    ($_.Value.inputs.PSObject.Properties.Name -contains "text")
})

Write-Host "Prompt-capable CLIPTextEncode nodes found: $($clipNodes.Count)" -ForegroundColor Yellow

if ($clipNodes.Count -lt 2) {
    throw "Could not find 2 prompt text nodes. Re-save the workflow as API format from ComfyUI."
}

$clipNodes[0].Value.inputs.text = $Prompt
$clipNodes[1].Value.inputs.text = $Negative

Write-Host "`n[3] Prompt injected." -ForegroundColor Green
Write-Host "Positive: $Prompt"
Write-Host "Negative: $Negative"

$clientId = "byrdhouse-runner-$([guid]::NewGuid().ToString())"

$body = @{
    prompt = $workflow
    client_id = $clientId
} | ConvertTo-Json -Depth 100

Write-Host "`n[4] Sending job to ComfyUI..." -ForegroundColor Cyan

$response = Invoke-RestMethod `
    -Uri "$ComfyUrl/prompt" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

$promptId = $response.prompt_id

Write-Host "API job submitted." -ForegroundColor Green
Write-Host "Prompt ID: $promptId" -ForegroundColor Yellow

Write-Host "`n[5] Waiting for output..." -ForegroundColor Cyan

$deadline = (Get-Date).AddMinutes(20)
$entry = $null

do {
    Start-Sleep -Seconds 3

    try {
        $history = Invoke-RestMethod "$ComfyUrl/history/$promptId"
    } catch {
        $history = Invoke-RestMethod "$ComfyUrl/history"
    }

    $entryProp = $history.PSObject.Properties | Where-Object { $_.Name -eq $promptId } | Select-Object -First 1

    if ($entryProp) {
        $entry = $entryProp.Value
    }

    Write-Host "." -NoNewline

} while (-not $entry -and (Get-Date) -lt $deadline)

if (-not $entry) {
    throw "Timed out waiting for ComfyUI output."
}

$outputPaths = @()

$entry.outputs.PSObject.Properties | ForEach-Object {
    if ($_.Value.images) {
        $_.Value.images | ForEach-Object {
            $folder = Join-Path $ComfyRoot "output"

            if ($_.subfolder -and $_.subfolder.Trim() -ne "") {
                $folder = Join-Path $folder $_.subfolder
            }

            $outputPath = Join-Path $folder $_.filename
            $outputPaths += $outputPath
        }
    }
}

Write-Host "`n`nDone." -ForegroundColor Green

$outputPaths | ForEach-Object {
    Write-Host "Output: $_" -ForegroundColor Green
}

if ($outputPaths.Count -gt 0 -and (Test-Path $outputPaths[0])) {
    Start-Process $outputPaths[0]
}
