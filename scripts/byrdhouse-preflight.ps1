# byrdhouse-preflight.ps1 — read-only machine/service preflight (handoff §15).
# Run on each machine. Answers "what is this box, and can it see the belt?"
# without changing anything: host + OS, IPv4, drives, roots, DNS for the
# configured hosts, port + HTTP health for the configured services, GPU,
# git state, belt processes, and hashes of the protected Swap V0 files.
# Hosts/ports come ONLY from %BYRDHOUSE_ROOT%\byrdhouse.config.json (hard
# rule: zero hardcoded IPs/hosts). Writes console report + machine-readable
# logs\preflight\<timestamp>\preflight.json. Exit 0 = no failures, 1 = FAILs.
#Requires -Version 5.1
param([switch]$Quiet)

$ErrorActionPreference = 'SilentlyContinue'
$report = [ordered]@{
    generated = (Get-Date -Format s)
    computer  = $env:COMPUTERNAME
    sections  = [ordered]@{}
}
$script:failCount = 0

function Say([string]$Text, [string]$Color = 'Gray') {
    if (-not $Quiet) { Write-Host $Text -ForegroundColor $Color }
}
function Check([string]$Section, [string]$Name, [bool]$Ok, $Detail) {
    if (-not $report.sections.Contains($Section)) {
        $report.sections[$Section] = [ordered]@{}
    }
    $report.sections[$Section][$Name] = [ordered]@{ ok = $Ok; detail = $Detail }
    if (-not $Ok) { $script:failCount++ }
    $state = 'OK  '; $color = 'Green'
    if (-not $Ok) { $state = 'FAIL'; $color = 'Red' }
    Say ("  [{0}] {1} — {2}" -f $state, $Name, $Detail) $color
}

Say ("`nByrdHouse preflight — {0} — {1}" -f $env:COMPUTERNAME, (Get-Date -Format s)) 'Cyan'
Say "  (read-only: nothing is started, stopped, or modified)`n"

# ── Root + config (the only source of hosts/services) ────────────────────────
$root = $env:BYRDHOUSE_ROOT
if (-not $root -or -not (Test-Path $root)) {
    Check 'root' 'byrdhouse_root' $false "BYRDHOUSE_ROOT missing or invalid: '$root'. setx BYRDHOUSE_ROOT and re-run."
    $report | ConvertTo-Json -Depth 8 | Write-Output
    exit 1
}
Check 'root' 'byrdhouse_root' $true $root

$cfgPath = Join-Path $root 'byrdhouse.config.json'
$cfg = $null
if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
}
Check 'root' 'config' ($null -ne $cfg) $cfgPath
if ($null -eq $cfg) {
    $report | ConvertTo-Json -Depth 8 | Write-Output
    exit 1
}

# ── Host + OS ────────────────────────────────────────────────────────────────
Say "`n=== HOST ===" 'Cyan'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = $null
if ($cs) { $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1) }
Check 'host' 'os' ($null -ne $os) ("{0} {1} — last boot {2}" -f $os.Caption, $os.Version, $os.LastBootUpTime)
Check 'host' 'ram_gb' ($null -ne $ramGB) $ramGB
Check 'host' 'cpu' $true (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)

# ── IPv4 (records what this box actually owns — resolves handoff conflicts) ──
Say "`n=== IPV4 ===" 'Cyan'
$ips = @(Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    ForEach-Object { [ordered]@{ interface = $_.InterfaceAlias; ip = $_.IPAddress; prefix = $_.PrefixLength } })
Check 'network' 'ipv4' ($ips.Count -gt 0) (($ips | ForEach-Object { "$($_.interface)=$($_.ip)" }) -join ', ')
$report.sections['network']['addresses'] = $ips

# ── Drives + roots ───────────────────────────────────────────────────────────
Say "`n=== DRIVES ===" 'Cyan'
$drives = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    [ordered]@{ name = $_.Name; root = "$($_.Root)"
                used_gb = [math]::Round($_.Used / 1GB, 1); free_gb = [math]::Round($_.Free / 1GB, 1) } })
$report.sections['drives'] = $drives
foreach ($d in $drives) { Say ("  {0}: used {1} GB, free {2} GB" -f $d.name, $d.used_gb, $d.free_gb) }
foreach ($sub in @('db', 'workflows', 'recipes', 'scripts')) {
    Check 'roots' $sub (Test-Path (Join-Path $root $sub)) (Join-Path $root $sub)
}

# ── DNS for configured hosts ─────────────────────────────────────────────────
Say "`n=== DNS (hosts from config) ===" 'Cyan'
if ($cfg.hosts) {
    foreach ($p in $cfg.hosts.PSObject.Properties) {
        $name = $p.Value
        if (-not $name -or $name -like '*CHANGE_ME*') { continue }
        $resolved = Resolve-DnsName $name -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress } | Select-Object -First 1 -ExpandProperty IPAddress
        Check 'dns' $p.Name ($null -ne $resolved) ("{0} -> {1}" -f $name, $resolved)
    }
}

# ── Ports + HTTP health for configured services ──────────────────────────────
Say "`n=== SERVICES (from config) ===" 'Cyan'
$healthPaths = @{ comfyui = '/system_stats'; router = '/health'; qdrant = '/readyz'; lmstudio = '/models' }
if ($cfg.services) {
    foreach ($p in $cfg.services.PSObject.Properties) {
        $svc = $p.Name; $url = $p.Value
        if (-not $url -or $url -like '*CHANGE_ME*') { continue }
        $uri = $null
        try { $uri = [System.Uri]$url } catch { }
        if ($null -eq $uri) { Check 'services' $svc $false "unparseable URL: $url"; continue }
        $tcp = Test-NetConnection -ComputerName $uri.Host -Port $uri.Port -WarningAction SilentlyContinue
        $portOk = ($tcp -and $tcp.TcpTestSucceeded)
        $healthUrl = $url.TrimEnd('/')
        if ($healthPaths.ContainsKey($svc)) { $healthUrl = $healthUrl + $healthPaths[$svc] }
        $httpOk = $false; $status = 'no response'
        if ($portOk) {
            try {
                $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 15
                $httpOk = ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
                $status = "HTTP $($r.StatusCode)"
            } catch { $status = "HTTP error: $($_.Exception.Message)" }
        } else { $status = "port $($uri.Port) closed/unreachable" }
        Check 'services' $svc ($portOk -and $httpOk) ("{0} — {1}" -f $healthUrl, $status)
    }
}

# ── GPU ──────────────────────────────────────────────────────────────────────
Say "`n=== GPU ===" 'Cyan'
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    $gpuLine = (& nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader) -join '; '
    Check 'gpu' 'nvidia_smi' ($LASTEXITCODE -eq 0) $gpuLine
} else {
    # Expected yellow on BYRD-MINI (no NVIDIA GPU) — recorded, not failed.
    Check 'gpu' 'nvidia_smi' $true 'nvidia-smi not present (expected on MINI)'
}

# ── Repository state ─────────────────────────────────────────────────────────
Say "`n=== REPOSITORY ===" 'Cyan'
Push-Location $root
$gitTop = (& git rev-parse --show-toplevel 2>$null)
if ($gitTop) {
    Check 'git' 'toplevel' $true $gitTop
    Check 'git' 'branch' $true ((& git rev-parse --abbrev-ref HEAD) -join '')
    Check 'git' 'last_commit' $true ((& git log -1 --oneline) -join '')
    $dirty = @(& git status --short)
    Check 'git' 'clean' ($dirty.Count -eq 0) ("{0} uncommitted change(s)" -f $dirty.Count)
    $report.sections['git']['remotes'] = @(& git remote -v)
} else {
    Check 'git' 'toplevel' $false "$root is not a git repository — STOP: do not make changes here until resolved."
}
Pop-Location

# ── Protected Swap V0 hashes (production protection checkpoint) ──────────────
Say "`n=== PROTECTED FILES ===" 'Cyan'
$protected = @('scripts\byrdcast_swap.py', 'configs\byrdcast_swap_v0.json', 'workflows\byrdcast_swap_v0.json',
               'scripts\worker.py', 'router\router.py')
$hashes = [ordered]@{}
foreach ($rel in $protected) {
    $fp = Join-Path $root $rel
    if (Test-Path $fp) {
        $h = (Get-FileHash $fp -Algorithm SHA256).Hash
        $hashes[$rel] = $h
        Say ("  {0}  {1}" -f $h.Substring(0, 12), $rel)
    } else {
        $hashes[$rel] = 'MISSING'
        Check 'protected' $rel $false 'file missing'
    }
}
$report.sections['protected_sha256'] = $hashes

# ── Belt processes ───────────────────────────────────────────────────────────
Say "`n=== PROCESSES ===" 'Cyan'
$procs = @(Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match 'ComfyUI|LM Studio|worker\.py|router\.py|qdrant' } |
    ForEach-Object {
        $cmd = ($_.CommandLine -replace '\s+', ' ')
        if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 160) }
        [ordered]@{ pid = $_.ProcessId; name = $_.Name; cmd = $cmd } })
$report.sections['processes'] = $procs
if ($procs.Count -eq 0) { Say '  (no belt processes running)' 'Yellow' }
foreach ($pr in $procs) { Say ("  {0,-7} {1}" -f $pr.pid, $pr.cmd) }

# ── Write machine-readable output (logs/ is gitignored) ──────────────────────
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir = Join-Path $root ("logs\preflight\" + $stamp)
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$outFile = Join-Path $outDir 'preflight.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $outFile -Encoding UTF8

Say ("`nReport: {0}" -f $outFile) 'Cyan'
if ($script:failCount -gt 0) {
    Say ("{0} FAIL check(s) — paste the report into docs/current-machine-inventory.md and resolve before P1 work." -f $script:failCount) 'Red'
    exit 1
}
Say 'All checks passed — paste the report summary into docs/current-machine-inventory.md.' 'Green'
exit 0
