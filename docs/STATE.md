# ByrdHouse STATE

*One page of current truth. Update weekly or on any milestone. Paste this to any AI to resume work instantly.*

**Last updated:** 2026-07-10 · **Current unlock: U0 STABILIZE** (in progress)

## Direction (decided 2026-07-08)

ByrdHouse is a **creator platform**, not a mining platform. Core lanes: image generation, video generation, video editing, MCP tooling, Godot automation. Mining stays manual and seasonal — it is NOT the center of this system.

## Snapshot — what works today

- LM Studio serving local models on BYRD-GAMING (Qwen 3.5 9B operator / Gemma fallback)
- Memory MCP on BYRD-MINI (save/search/recent/status) — verified via Cherry Studio
- SQLite + Qdrant (Docker: byrdhouse-qdrant) memory stack
- Conversation importer (Inbox → Cleaned → Processed)
- ComfyUI on BYRD-GAMING, remote job submission from BYRD-MINI proven
- byrdimage-full pipeline: prompt → generate → archive → metadata card → knowledge sync → gallery

## U0 work order (current)

- [ ] 1. byrdhouse.config.json installed on BOTH machines (edit host + memory placeholders)
- [ ] 2. `setx BYRDHOUSE_ROOT "D:\ByrdHouse"` on MINI / `"E:\ByrdHouse"` on GAMING (reopen terminal)
- [ ] 3. All scripts converted to read config — zero hardcoded IPs (see docs/CLAUDE_CODE_TASKS.md)
- [ ] 4. byrd-status.ps1 v2 running on both machines
- [ ] 5. status.json generating at root (dashboard-ready)
- [ ] 6. byrdimage-full re-tested end-to-end — all 7 acceptance checks pass
- [x] 7. STATE.md live (this file) + DECISIONS.md logging
- [~] 8. Miner automation: **deferred by decision** — see Money & Miners below

## Constraints (real, respected)

- Apartment: 2BR/1BA, one small opening window, shared with girlfriend + dog
- Heat + noise budget limited → ASIC miners run manually, on/off with weather
- GPU work (3070) is the right tool: schedule heavy image batches for out-of-house / headphone hours

## Creator assets (the distribution ByrdHouse feeds)

- TikTok: **9,000** followers · YouTube: **1,500** subs · Twitch: **500** followers
- **First client = these channels.** U1's first outputs are MY thumbnails, MY clips, MY channel art.

## Money & Miners (tracked, not built around — per decision 2026-07-08)

- Debt total: **~$24,982** · target: Capital One **$693** first, then 15.49% card
- 5080 order: **let expire** (kept $1,456) · Hardware rule: **cash only**
- Miners: manual on/off as heat allows; no automation yet; revisit after U1
- ByrdHouse revenue: **$0** → goal R0 = first output used on my own channel, then first paid output

## Next actions (gaming PC — everything below is config or debugging, no building)

1. Clone repo, run `scripts\setup-gaming.ps1` (creates E:\ByrdHouse, installs full kit, runs first status)
2. Edit `E:\ByrdHouse\byrdhouse.config.json` placeholders: hosts, operator_model, judge_model (a Qwen-VL build in LM Studio), ComfyUI dir, admin_token, backup dest
3. Run `scripts\start-byrdhouse.ps1` — boots LM Studio + ComfyUI + router + worker + status. Fix reds. Then `install-startup-task.ps1` and `backup-nightly.ps1 -Install` (both admin, once)
4. Open the dashboard on the iPad: `http://byrd-gaming:8787` (tailnet) — paste admin token, queue a generation with two taps, approve/reject from the gallery
5. Cold-reboot test = U0 DoD. When BYRD-MINI arrives: run setup-mini.ps1, flip startup.run_router (false on GAMING, true on MINI), point services.router at byrd-mini, copy db\byrdhouse.db over

## Done log

- 2026-07-10 · Content engine (v3.1) shipped: content.thumbnail two-pass (art via recipe → REAL text composited by Pillow, 1280x720), content.package (voice-pack packaging via local Qwen), content.research (outlier CSV → ranked ideas), export.csv. Dashboard rebuilt as the room-based Command Center (14 rooms, stats, per-room views). Permanent test suite (tests/integration_test.py, 22 checks) + GitHub Actions CI (belt test, PowerShell parse, JSON validation, node check). set-router-host.ps1 ready for MINI day
- 2026-07-10 · Full belt shipped and integration-tested in repo (mock ComfyUI + mock LM Studio): router API v1 (v2 §6 contract, SQLite schema §5, stdlib-only), worker daemon with mode shifts + auto-judge enqueue, byrdjudge (Qwen-VL scoring vs recipe rubric), iPad dashboard (health/queue/generate/approve/events), backup-nightly, retry→dead job path verified, dashboard screenshot-verified in Chromium
- 2026-07-10 · Gaming-PC side completed in repo: start-byrdhouse.ps1 (one command), install-startup-task.ps1 (logon task), byrdimage.py submit layer (random seed per job, unique filename prefix, verified prompt injection into every CLIPTextEncode, checkpoint recorded on card) + sdxl_base_api workflow — pipeline smoke-tested end-to-end against a mock ComfyUI
- 2026-07-10 · U0 kit committed to the GitHub repo (config template, byrd-status v2, setup scripts, mode script, docs trio, starter recipes) — repo is now the kit distribution channel
- 2026-07-08 · U0 kit designed (config, byrd-status v2, state/decisions docs, Claude Code task briefs)
