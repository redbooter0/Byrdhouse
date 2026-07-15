<#
find-codex-work.ps1 — locate everything Codex (and any other local agent) left
on THIS machine, so no work gets lost.

It reports, touches nothing:
  1. Codex CLI home (%USERPROFILE%\.codex): sessions, history, config —
     newest sessions first, with the project folders (cwd) they worked in.
  2. AGENTS.md files (Codex's instruction files) near the ByrdHouse roots.
  3. Every git repo under the roots: current branch, uncommitted files,
     commits that exist locally but were never pushed.
  4. Files modified in the last N days under the roots (the recent-work trail).

Usage:
    powershell -ExecutionPolicy Bypass -File scripts\find-codex-work.ps1
    -Days 7        how far back the recent-file trail looks
    -Roots <dirs>  extra folders to scan (defaults: BYRDHOUSE_ROOT, D:\ByrdHouse,
                   E:\ByrdHouse, %USERPROFILE%\Documents)

Writes the same report to %BYRDHOUSE_ROOT%\codex_report.txt for the dashboard/chat.
#>
param(
    [int]$Days = 7,
    [string[]]$Roots = @()
)
$ErrorActionPreference = "Continue"
$out = New-Object System.Collections.ArrayList
function Say([string]$t, [string]$color = "Gray") {
    Write-Host $t -ForegroundColor $color
    [void]$out.Add($t)
}

$scanRoots = New-Object System.Collections.ArrayList
foreach ($r in @($env:BYRDHOUSE_ROOT, "D:\ByrdHouse", "E:\ByrdHouse",
                 "$env:USERPROFILE\Documents") + $Roots) {
    if ($r -and (Test-Path $r) -and -not ($scanRoots -contains $r)) { [void]$scanRoots.Add($r) }
}

Say "" ; Say "=== Codex / local-agent work finder ===" "Cyan"
Say ("roots: " + ($scanRoots -join ", "))

# ── 1. Codex CLI home ─────────────────────────────────────────────────────────
$codexHome = Join-Path $env:USERPROFILE ".codex"
Say "" ; Say "[1] Codex CLI home ($codexHome)" "Cyan"
if (Test-Path $codexHome) {
    $sessDir = Join-Path $codexHome "sessions"
    if (Test-Path $sessDir) {
        $sessions = Get-ChildItem $sessDir -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 10
        Say ("  {0} session file(s); newest:" -f @($sessions).Count)
        foreach ($s in $sessions) {
            Say ("   {0}  {1}  ({2:n0} KB)" -f $s.LastWriteTime.ToString("yyyy-MM-dd HH:mm"), $s.Name, ($s.Length/1KB))
            # pull the working directories out of the session so you know WHICH
            # project that session was editing
            try {
                $cwds = Select-String -Path $s.FullName -Pattern '"cwd"\s*:\s*"([^"]+)"' -AllMatches -ErrorAction Stop |
                    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } |
                    Select-Object -Unique -First 3
                foreach ($c in $cwds) { Say ("      worked in: {0}" -f ($c -replace "\\\\", "\")) }
            } catch {}
        }
    } else { Say "  no sessions folder" }
    foreach ($extra in @("history.jsonl", "config.toml", "AGENTS.md", "instructions.md")) {
        $p = Join-Path $codexHome $extra
        if (Test-Path $p) {
            $fi = Get-Item $p
            Say ("  {0} — last touched {1}" -f $extra, $fi.LastWriteTime.ToString("yyyy-MM-dd HH:mm"))
        }
    }
} else {
    Say "  not found — Codex CLI never ran (or ran as another user) on this machine"
}

# ── 2. AGENTS.md instruction files ────────────────────────────────────────────
Say "" ; Say "[2] AGENTS.md files (Codex reads these per-project)" "Cyan"
$found = 0
foreach ($root in $scanRoots) {
    Get-ChildItem $root -Recurse -Filter "AGENTS.md" -File -Depth 4 -ErrorAction SilentlyContinue |
        ForEach-Object {
            $found++
            Say ("  {0}  (modified {1})" -f $_.FullName, $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm"))
        }
}
if ($found -eq 0) { Say "  none found under the roots" }

# ── 2b. known Codex work files (seen in its sessions on 2026-07-14) ──────────
Say "" ; Say "[2b] Known Codex files: byrdfacezone.py (CPU mask pipeline), build-100-* dataset builders" "Cyan"
$hits = 0
foreach ($root in $scanRoots) {
    Get-ChildItem $root -Recurse -File -Depth 5 -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "byrdfacezone.py" -or $_.Name -like "build-100-*.ps1" `
                       -or $_.Name -like "*skit*manifest*" } |
        ForEach-Object {
            $hits++
            Say ("  {0}  (modified {1})" -f $_.FullName, $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm")) "Yellow"
        }
}
if ($hits -eq 0) { Say "  none found — check the session logs in [1] for where they were written" }
# Codex also edited byrdimage.py IN PLACE (edit_face_zone) — flag any copy carrying it
foreach ($root in $scanRoots) {
    Get-ChildItem $root -Recurse -Filter "byrdimage.py" -File -Depth 4 -ErrorAction SilentlyContinue |
        ForEach-Object {
            if (Select-String -Path $_.FullName -Pattern "edit_face_zone" -Quiet -ErrorAction SilentlyContinue) {
                Say ("  {0} contains Codex's edit_face_zone work — commit it to a branch before pulling!" -f $_.FullName) "Yellow"
            }
        }
}

# ── 3. git repos: branch, dirty files, unpushed commits ───────────────────────
Say "" ; Say "[3] Git repos — where work is sitting uncommitted/unpushed" "Cyan"
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Say "  git not on PATH — skipping"
} else {
    foreach ($root in $scanRoots) {
        Get-ChildItem $root -Recurse -Directory -Filter ".git" -Depth 3 -ErrorAction SilentlyContinue |
            ForEach-Object {
                $repo = $_.Parent.FullName
                $branch = (& git -C $repo rev-parse --abbrev-ref HEAD 2>$null)
                $dirty = @(& git -C $repo status --porcelain 2>$null)
                $unpushed = @(& git -C $repo log --branches --not --remotes --oneline 2>$null)
                Say ("  {0}  [branch: {1}]" -f $repo, $branch)
                if ($dirty.Count)    { Say ("      {0} uncommitted change(s):" -f $dirty.Count) "Yellow"
                                       $dirty | Select-Object -First 8 | ForEach-Object { Say ("        {0}" -f $_) "Yellow" } }
                if ($unpushed.Count) { Say ("      {0} commit(s) never pushed:" -f $unpushed.Count) "Yellow"
                                       $unpushed | Select-Object -First 8 | ForEach-Object { Say ("        {0}" -f $_) "Yellow" } }
                if (-not $dirty.Count -and -not $unpushed.Count) { Say "      clean and pushed" "Green" }
            }
    }
}

# ── 4. recent-work trail ──────────────────────────────────────────────────────
Say "" ; Say ("[4] Files modified in the last {0} day(s) under the roots" -f $Days) "Cyan"
$cut = (Get-Date).AddDays(-$Days)
$codeExt = @(".py", ".ps1", ".js", ".html", ".json", ".md", ".toml", ".yaml", ".yml", ".safetensors")
foreach ($root in $scanRoots) {
    Get-ChildItem $root -Recurse -File -Depth 5 -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cut -and $codeExt -contains $_.Extension.ToLower() `
                       -and $_.FullName -notmatch "\\(\.git|node_modules|venv|__pycache__)\\" } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 25 |
        ForEach-Object { Say ("  {0}  {1}" -f $_.LastWriteTime.ToString("MM-dd HH:mm"), $_.FullName) }
}

# ── save the report ───────────────────────────────────────────────────────────
if ($env:BYRDHOUSE_ROOT) {
    $dest = Join-Path $env:BYRDHOUSE_ROOT "codex_report.txt"
    $out | Set-Content $dest -Encoding UTF8
    Say "" ; Say ("report saved: {0}" -f $dest) "Green"
}
Say ""
Say "Also on GitHub (pushed but never merged — review or fold into main):" "Cyan"
Say "  fix/operator-endpoints-and-studio-config  (2026-07-11: Luna Pulse job supervision, studio endpoints, operator MCP integrations)"
Say "  fix/belt-contract-and-private-operator    (2026-07-11: belt contract hardening + private operator MCP)"
Say "  fix/recipe-contract-safety                (2026-07-11: recipe slot contract at queue boundary)"
Say "  fix/dashboard-draft-persistence           (2026-07-10/11: draft persistence variant)"
Say "  agent/byrdhouse-gaming-windows-safe       (2026-07-10: gaming U0 worker/judge flow)"
