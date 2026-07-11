#Requires -Version 5.1
<#
.SYNOPSIS
Installs the ByrdHouse Belt MCP entry for LM Studio and prints the matching
Cherry Studio STDIO configuration without exposing the router token.
#>
param(
    [ValidateSet('gaming', 'mini')]
    [string]$Machine = 'gaming',
    [string]$Root = '',
    [switch]$InstallLmStudio,
    [switch]$CopyCherryJson
)

$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if ($env:BYRDHOUSE_ROOT) { $env:BYRDHOUSE_ROOT }
            elseif ($Machine -eq 'mini') { 'D:\ByrdHouse' }
            else { 'E:\ByrdHouse' }
}
$Root = [System.IO.Path]::GetFullPath($Root)
$repo = Split-Path $PSScriptRoot -Parent
$name = "byrdhouse-belt-$Machine.mcp.json"
$template = @(
    (Join-Path $Root "integrations\$name"),
    (Join-Path $repo "integrations\$name")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $template) { throw "Missing $name. Run the ByrdHouse setup sync first." }
$belt = Join-Path $Root 'scripts\byrd_belt_mcp.py'
if (-not (Test-Path -LiteralPath $belt)) {
    throw "Missing $belt. The live machine has not received the belt MCP script yet."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is not on PATH.'
}

$entryDoc = Get-Content -LiteralPath $template -Raw -Encoding UTF8 | ConvertFrom-Json
$entry = $entryDoc.mcpServers.'byrdhouse-belt'
if (-not $entry) { throw "$template has no mcpServers.byrdhouse-belt entry." }
$entry.args[0] = $belt
$entry.env.BYRDHOUSE_ROOT = $Root
$entry.env.BYRD_BELT_MCP_READONLY = '1'

Write-Host "ByrdHouse Studio integration for $Machine ($Root)" -ForegroundColor Cyan
Write-Host "  belt MCP: $belt"
Write-Host '  router/API token stays in the machine-local ByrdHouse config.'

if ($InstallLmStudio) {
    $targetDir = Join-Path $env:USERPROFILE '.lmstudio'
    $target = Join-Path $targetDir 'mcp.json'
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    if (Test-Path -LiteralPath $target) {
        try {
            $doc = Get-Content -LiteralPath $target -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            throw "LM Studio MCP JSON is invalid; left untouched: $target ($($_.Exception.Message))"
        }
        $backup = "$target.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $target -Destination $backup
        Write-Host "  backed up existing LM Studio config: $backup"
    } else {
        $doc = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
    }
    if (-not $doc.mcpServers) {
        $doc | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    $doc.mcpServers | Add-Member -NotePropertyName 'byrdhouse-belt' -NotePropertyValue $entry -Force
    $json = $doc | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($target, $json + [Environment]::NewLine, $utf8NoBom)
    Write-Host "  installed read-only ByrdHouse Belt entry: $target" -ForegroundColor Green
    Write-Host '  restart LM Studio before testing MCP tools.' -ForegroundColor Yellow
}

if ($CopyCherryJson) {
    $json = $entryDoc | ConvertTo-Json -Depth 20
    if (Get-Command Set-Clipboard -ErrorAction SilentlyContinue) {
        Set-Clipboard -Value $json
        Write-Host '  Cherry Studio STDIO JSON copied to the clipboard.' -ForegroundColor Green
    } else {
        Write-Host $json
    }
    Write-Host '  Cherry Studio: Settings -> MCP Servers -> Add Server -> STDIO.'
}

if (-not $InstallLmStudio -and -not $CopyCherryJson) {
    Write-Host '  no files changed (use -InstallLmStudio and/or -CopyCherryJson).' -ForegroundColor Yellow
}
