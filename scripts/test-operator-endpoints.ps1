#Requires -Version 5.1
<#
.SYNOPSIS
Read-only, Windows PowerShell 5.1-compatible proof of the complete ByrdHouse
operator path: router, Pulse, LM Studio, CORS, ComfyUI and Belt MCP STDIO.
#>
param(
    [string]$Root = '',
    [switch]$RequireRemoteOverlay
)

$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if ($env:BYRDHOUSE_ROOT) { $env:BYRDHOUSE_ROOT }
            elseif (Test-Path 'E:\ByrdHouse\byrdhouse.config.json') { 'E:\ByrdHouse' }
            else { 'D:\ByrdHouse' }
}
$Root = [System.IO.Path]::GetFullPath($Root)
$configPath = Join-Path $Root 'byrdhouse.config.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw "Missing $configPath" }
$cfg = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    $results.Add([pscustomobject]@{ Check = $Name; OK = $Ok; Detail = $Detail })
}
function Test-JsonEndpoint([string]$Name, [string]$Uri) {
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 12
        $null = $r.Content | ConvertFrom-Json
        Add-Result $Name ($r.StatusCode -eq 200) "HTTP $($r.StatusCode) $Uri"
    } catch { Add-Result $Name $false $_.Exception.Message }
}

$router = $cfg.services.router.TrimEnd('/')
$lm = $cfg.services.lmstudio.TrimEnd('/')
$comfy = $cfg.services.comfyui.TrimEnd('/')
Test-JsonEndpoint 'router.health' "$router/health"
Test-JsonEndpoint 'router.capabilities' "$router/capabilities"
Test-JsonEndpoint 'router.recipes' "$router/recipes"
Test-JsonEndpoint 'luna.pulse' "$router/job-updates?after=0&limit=1"
Test-JsonEndpoint 'lmstudio.models' "$lm/models"
Test-JsonEndpoint 'comfyui.system_stats' "$comfy/system_stats"

$tailscale = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
if ($RequireRemoteOverlay) {
    Add-Result 'remote.private_overlay' ($tailscale -and $tailscale.Status -eq 'Running') `
        $(if ($tailscale) { "Tailscale service=$($tailscale.Status)" } else { 'Tailscale is not installed' })
} elseif (-not $tailscale) {
    Write-Warning 'Tailscale is not installed; this machine is LAN-only, not remotely reachable through a private overlay.'
}

try {
    $cors = Invoke-WebRequest -Uri "$lm/models" -Headers @{ Origin = $router } -UseBasicParsing -TimeoutSec 12
    $allow = [string]$cors.Headers['Access-Control-Allow-Origin']
    Add-Result 'lmstudio.cors' ([bool]$allow) "Access-Control-Allow-Origin=$allow"
} catch { Add-Result 'lmstudio.cors' $false $_.Exception.Message }

$belt = Join-Path $Root 'scripts\byrd_belt_mcp.py'
$lmMcpPath = Join-Path $env:USERPROFILE '.lmstudio\mcp.json'
if (Test-Path -LiteralPath $lmMcpPath) {
    try {
        $lmMcp = Get-Content -LiteralPath $lmMcpPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $beltEntry = $lmMcp.mcpServers.'byrdhouse-belt'
        $entryScript = if ($beltEntry -and $beltEntry.args) { [string]$beltEntry.args[0] } else { '' }
        $entryRoot = if ($beltEntry -and $beltEntry.env) { [string]$beltEntry.env.BYRDHOUSE_ROOT } else { '' }
        $entryReadonly = if ($beltEntry -and $beltEntry.env) { [string]$beltEntry.env.BYRD_BELT_MCP_READONLY } else { '' }
        $entryOk = $entryScript -and (Test-Path -LiteralPath $entryScript) `
            -and ([IO.Path]::GetFullPath($entryRoot) -eq $Root) -and $entryReadonly -eq '1'
        Add-Result 'lmstudio.mcp.belt_config' $entryOk "script=$entryScript root=$entryRoot readonly=$entryReadonly"
    } catch { Add-Result 'lmstudio.mcp.belt_config' $false $_.Exception.Message }
} else {
    Add-Result 'lmstudio.mcp.belt_config' $false "missing $lmMcpPath"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Add-Result 'belt.mcp.initialize' $false 'python is not on PATH'
} elseif (-not (Test-Path -LiteralPath $belt)) {
    Add-Result 'belt.mcp.initialize' $false "missing $belt"
} else {
    $oldRoot = $env:BYRDHOUSE_ROOT
    $oldReadonly = $env:BYRD_BELT_MCP_READONLY
    try {
        $env:BYRDHOUSE_ROOT = $Root
        $env:BYRD_BELT_MCP_READONLY = '1'
        $request = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
        $raw = $request | & $python.Source $belt 2>$null | Select-Object -First 1
        $reply = $raw | ConvertFrom-Json
        $server = [string]$reply.result.serverInfo.name
        Add-Result 'belt.mcp.initialize' ($server -eq 'byrd-belt') "server=$server"
    } catch { Add-Result 'belt.mcp.initialize' $false $_.Exception.Message }
    finally {
        $env:BYRDHOUSE_ROOT = $oldRoot
        $env:BYRD_BELT_MCP_READONLY = $oldReadonly
    }
}

$results | Format-Table -AutoSize
$failed = @($results | Where-Object { -not $_.OK })
if ($failed.Count) {
    Write-Host "$($failed.Count) operator check(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "All $($results.Count) operator checks passed." -ForegroundColor Green
