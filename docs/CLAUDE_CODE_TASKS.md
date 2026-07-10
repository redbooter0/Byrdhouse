# CLAUDE_CODE_TASKS — U0 STABILIZE work orders

Hand each task to a Claude Code session on the named machine. Every task ends in a
testable check. Log completions in docs/STATE.md's Done log and any decisions in
docs/DECISIONS.md.

---

## Task 1 — Config + root + first status (BYRD-MINI)

1. Clone/pull this repo, run `powershell -ExecutionPolicy Bypass -File scripts\setup-mini.ps1`
2. Edit `D:\ByrdHouse\byrdhouse.config.json`: real Tailscale hostnames, LM Studio operator
   model key, memory.* section (sqlite db path, table, Qdrant collection), fresh admin_token.
3. Run `D:\ByrdHouse\scripts\byrd-status.ps1`.

**Done when:** status runs, `D:\ByrdHouse\status.json` exists, and every red has a
known reason (fix or log it).

## Task 2 — De-hardcode all existing scripts (BYRD-MINI)

Search every existing ByrdHouse script (`D:\ByrdHouse\scripts`, importers, byrdimage
submitters) for IP literals (`192.168.`, `100.`, `http://<ip>`), port literals, and absolute
paths to the other machine. Replace each with a read from the config:

```powershell
$cfg = Get-Content "$env:BYRDHOUSE_ROOT\byrdhouse.config.json" -Raw | ConvertFrom-Json
$comfy = $cfg.services.comfyui
```

**Done when:** `grep` for hardcoded IPs across all scripts returns zero hits, and the
remote-generation path still works (submit one job MINI → GAMING).

## Task 3 — Mirror to gaming PC (BYRD-GAMING)

1. Clone/pull this repo, run `powershell -ExecutionPolicy Bypass -File scripts\setup-gaming.ps1`
2. Copy the *tuned* config from MINI (or re-apply the same edits) to `E:\ByrdHouse\byrdhouse.config.json`.
3. Run `byrd-status.ps1` here too.

**Done when:** both machines produce a status.json and each can reach the other's
services by Tailscale name.

## Task 4 — byrdimage-full re-test (BYRD-GAMING)

Run the full pipeline once end-to-end and verify all 7 acceptance checks:

1. Prompt submitted through the standard entry point (no manual ComfyUI clicking)
2. Image generated (fresh file in the ComfyUI output)
3. **Seed was randomized at submit time** (different from previous run's card; not the workflow's baked-in seed)
4. Unique filename prefix per job (no stale-output confusion)
5. Image archived to `artifacts\<project>\<yyyy-mm>\`
6. Sidecar metadata card written next to it (prompt, negative, seed, checkpoint actually loaded, purpose)
7. Gallery/knowledge sync ran (gallery index includes the new image)

**Done when:** 7/7 pass twice in a row. If any fail, fix at the submit layer (v2 §1.4
Action 3) and log the fix in DECISIONS.md.

## Task 5 — Mode ritual dry-run (BYRD-GAMING)

1. With the operator model loaded, run `scripts\use-image-mode.ps1` — must reach
   "IMAGE mode ready" with VRAM verified under threshold.
2. Run `scripts\use-image-mode.ps1 -Restore` — operator model reloads.

**Done when:** both directions work without touching nvidia-smi by hand.

## U0 Definition of Done (from Blueprint v2)

Cold-reboot both PCs → one command each → byrd-status all green → generate one
image end-to-end → nightly backup file exists on BYRD-VAULT (vault can lag; it's the
last box).
