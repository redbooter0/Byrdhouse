# set-router-host.ps1 — move the belt's home between machines (MINI handoff).
# Run ON EACH machine after BYRD-MINI is set up:
#   scripts\set-router-host.ps1 mini      (on BOTH machines)
# It updates the local byrdhouse.config.json: services.router points at the
# chosen host, and startup.run_router turns on only where the router lives.
# The worker keeps running on GAMING either way.
#Requires -Version 5.1
param(
    [Parameter(Mandatory)][ValidateSet('gaming','mini')][string]$RouterHost,
    [ValidateSet('gaming','mini','auto')][string]$ThisMachine = 'auto'
)

$root = $env:BYRDHOUSE_ROOT
if (-not $root) { Write-Error 'BYRDHOUSE_ROOT not set.'; exit 2 }
$cfgPath = Join-Path $root 'byrdhouse.config.json'
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json

if ($ThisMachine -eq 'auto') {
    # Blueprint roles: GAMING lives on E:, MINI on D:
    $ThisMachine = if ($root -like 'E:*') { 'gaming' } elseif ($root -like 'D:*') { 'mini' } else { '' }
    if (-not $ThisMachine) { Write-Error "Can't infer role from $root — pass -ThisMachine gaming|mini"; exit 2 }
}

$hostName = $cfg.hosts.$RouterHost
$cfg.services.router = "http://${hostName}:8787"
$cfg.startup.run_router = ($ThisMachine -eq $RouterHost)
$cfg | ConvertTo-Json -Depth 8 | Set-Content $cfgPath -Encoding UTF8

Write-Host "Router home: $RouterHost ($($cfg.services.router))" -ForegroundColor Green
Write-Host "This machine ($ThisMachine): run_router = $($cfg.startup.run_router)"
if ($RouterHost -eq 'mini' -and $ThisMachine -eq 'mini') {
    Write-Host @"

Belt-move checklist (do once, in order):
  1. Stop the router on GAMING (close its python window or reboot it later)
  2. Copy the belt database from GAMING to MINI (keeps all history):
       robocopy \\$($cfg.hosts.gaming)\ByrdHouse\db $root\db byrdhouse.db
     (or copy E:\ByrdHouse\db\byrdhouse.db over however you like)
  3. Run set-router-host.ps1 mini on GAMING too
  4. start-byrdhouse.ps1 on MINI, then on GAMING — dashboard is now http://$hostName:8787
"@ -ForegroundColor Cyan
}
