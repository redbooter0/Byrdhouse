# BYRD-MINI Bring-Up — 2026-07-10

*What got set up today, what state the mini is in, and the exact next fixes in order.*

## What we set up

- **Repo cloned on the mini** at `C:\Users\Byrdh\byrdhouse`, on branch `claude/fable-5-mini-pc-y3kfbm` (PR #2 merges it to main — after merge, switch back: `git checkout main && git pull`).
- **Kit installed to `D:\ByrdHouse`** via `setup-mini.ps1`: full directory map, config template, scripts/docs/recipes/workflows/router/dashboard synced, `BYRDHOUSE_ROOT=D:\ByrdHouse` set, Pillow installed.
- **Two kit bugs fixed along the way** (both would have bitten GAMING re-syncs too):
  1. All `.ps1` files now carry a UTF-8 BOM — PowerShell 5.1 read them as ANSI and parse-crashed on em-dashes. CI now enforces the BOM.
  2. The Pillow check runs via `cmd /c` so a missing module can't kill setup under `$ErrorActionPreference='Stop'`.
- **Router + dashboard live on the mini**: `http://byrd-mini:8787` answers — the router handoff from GAMING has begun.
- **Belt hardening shipped** (router + dashboard, in PR #2): stuck-job reaper (15 min heartbeat silence → retry→dead path), server-computed worker online/offline shown on dashboard chips, `POST /jobs/<id>/requeue` + `POST /jobs/<id>/cancel` with System Room buttons. Integration test grew to 26 checks, all green.

## Status at last byrd-status run

| Check | State | Meaning |
|---|---|---|
| byrdhouse_root, host_gaming, svc_comfyui, svc_qdrant, disk | GREEN | Tailnet works, ComfyUI on GAMING reachable, Qdrant up locally |
| svc_router | was YELLOW | now serving — re-run byrd-status to confirm green |
| svc_lmstudio | RED | GAMING-side: LM Studio server not running or bound to localhost only |
| config | YELLOW | `CHANGE_ME` placeholders remain (admin_token, memory.*) |
| memory_drift | YELLOW | memory.* not filled in config |
| host_vault | YELLOW | BYRD-VAULT not on the tailnet yet — fine for now |
| gpu | YELLOW | expected on the mini (no NVIDIA GPU) |

## Next things to fix (in order)

1. **Merge PR #2** so main carries the fixes, then on the mini: `git checkout main && git pull`, re-run `setup-mini.ps1` to re-sync the kit, restart the router (`start-byrdhouse.ps1`).
2. **Edit `D:\ByrdHouse\byrdhouse.config.json`:**
   - `auth.admin_token` → long random string (`-join ((48..57)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})`)
   - `memory.sqlite_db` / `sqlite_table` / `qdrant_collection` → real values (collections list: `http://byrd-mini:6333/collections`)
   - `startup.run_worker` → `false` (worker is GAMING-only)
3. **Fix svc_lmstudio (on GAMING):** LM Studio → Developer/Server tab → enable "Serve on local network", port 1234 (or `lms server start`). Re-check from the mini.
4. **Finish the router handoff (on GAMING):** set `startup.run_router: false` in `E:\ByrdHouse\byrdhouse.config.json`; copy `E:\ByrdHouse\db\byrdhouse.db` → `D:\ByrdHouse\db\` (skip if no real jobs yet — router makes a fresh db). Same token in both machines' configs.
5. **byrd-status green on both machines**, then the **U0 Definition of Done**: cold-reboot both PCs → one command each (`start-byrdhouse.ps1`) → all green → queue one image from the Image Studio room on the iPad (`http://byrd-mini:8787`) and approve it in the gallery.
6. **Then R0**: first thumbnail for your own channel through `content.thumbnail`.
7. **Later / not blocking:** BYRD-VAULT on the tailnet + `backup.dest` in config + `backup-nightly.ps1 -Install`; check off U0 boxes in STATE.md as each lands.
