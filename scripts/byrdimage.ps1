# byrdimage.ps1 - thin wrapper so image generation is one PowerShell command.
#   byrdimage -Recipe rpg_tier_list -Project careyrpg -Purpose "tier list test" `
#             -Slot subject="armored paladin",game="Last Epoch"
#Requires -Version 5.1
param(
    [Parameter(Mandatory)][string]$Recipe,
    [Parameter(Mandatory)][string]$Purpose,
    [string]$Project = 'sandbox',
    [string[]]$Slot = @(),
    [int]$Batch,
    [string]$Checkpoint,
    [switch]$DryRun
)

$root = $env:BYRDHOUSE_ROOT
if (-not $root) { Write-Error 'BYRDHOUSE_ROOT not set - run setup-gaming.ps1 first.'; exit 2 }
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Error 'python not on PATH (any Python 3.8+ works - byrdimage is stdlib-only).'; exit 2 }

$argv = @((Join-Path $root 'scripts\byrdimage.py'), '--recipe', $Recipe, '--project', $Project, '--purpose', $Purpose)
foreach ($s in $Slot) { $argv += @('--set', $s) }
if ($Batch)      { $argv += @('--batch', $Batch) }
if ($Checkpoint) { $argv += @('--checkpoint', $Checkpoint) }
if ($DryRun)     { $argv += '--dry-run' }

& python @argv
exit $LASTEXITCODE
