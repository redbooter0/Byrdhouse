# CLAUDE_CODE_TASKS — ByrdHouse active work orders

Every task must end with a concrete check. Do not loop on setup/status commands. Log completions in `docs/STATE.md` and decisions in `docs/DECISIONS.md`.

## Current stage

U0 is functionally complete. The active stage is **U1 IMAGE LAB**.

Source of truth:

- MINI router/dashboard: `http://byrd-mini:8787`
- MINI root: `D:\ByrdHouse`
- GAMING root: `E:\ByrdHouse`
- GitHub repo: `https://github.com/redbooter0/Byrdhouse.git`

Known non-blocking yellows:

- BYRD-VAULT offline/unreachable.
- GAMING memory drift not configured because memory belongs on MINI.
- MINI has no NVIDIA GPU.
- Old dead jobs from prior debugging.

## Command-loop prevention

Use this before touching commands:

1. Is the target machine already set up? If yes, do not run setup.
2. Is the yellow status already documented? If yes, do not chase it.
3. Is there a new failing job? If no, do not inspect old dead jobs.
4. Is the dashboard/router reachable? If yes, use the app path instead of manual scripts.
5. Did a command fail twice with the same error? Stop and fix that exact error; do not rerun the same command a third time unchanged.

## Task A — U0 closeout reboot test

Run once, not repeatedly.

1. Reboot BYRD-MINI.
2. Reboot BYRD-GAMING.
3. Open `http://byrd-mini:8787`.
4. Confirm worker `worker-byrd-gaming` returns online.
5. Queue one `rpg_tier_list` image from the dashboard.
6. Confirm it becomes generated, judged, and reviewable.

**Done when:** one new artifact has score/tags/caption and can be approved.

**If it fails:** fix only the failing startup/service. Do not rerun setup unless the root folder is missing.

## Task B — U1 image recipe batch

Use the working router/worker path.

1. Queue 10 CareyRPG images:
   - 3 `rpg_tier_list`
   - 2 `build_guide`
   - 2 `shock_reveal`
   - 2 `vs_matchup`
   - 1 `yt_thumbnail`
2. Approve/reject each from the dashboard gallery.
3. Record bad patterns in recipe/rubric notes.

**Done when:** at least 5 approved artifacts have score, tags, caption, prompt, seed, checkpoint, and purpose.

## Task C — U1 thumbnail truth test

1. Queue at least 2 `content.thumbnail` jobs.
2. Confirm each generated image has no baked-in title text.
3. Confirm each final thumbnail is composited by `scripts/compose_thumbnail.py`.
4. Confirm final PNGs are 1280x720.

**Done when:** two final thumbnails exist and their title text is real composited text.

## Task D — U1 export and review hygiene

1. Run/export approved and rejected artifacts to CSV through the `export.csv` job.
2. Confirm approved/rejected decisions are represented in the export.
3. Ignore old debugging `dead` jobs unless they block new queue work.

**Done when:** one CSV artifact exists under `artifacts\exports`.

## Task E — Code-change gate

Only use this when code changed.

1. Run:

```powershell
python tests\integration_test.py
```

2. If passing, commit and push.
3. If failing, fix the failing test only.

**Done when:** repo main is clean and pushed.

## Frozen until later

- Odysseus/smart-home/Stripe.
- User accounts/credits/newsletters.
- Miner automation.
- U5 video/motion pipeline.
- U6 Godot belt integration.

These can be discussed, but they should not interrupt U1 unless the founder explicitly changes priority.

## Current operating direction

The next product is a private open-source-compatible operator, not a second
queue and not a direct ComfyUI controller. MINI owns router, SQLite/WAL,
dashboard, memory, MCP gateway, audit/events, and an optional small fallback
model. GAMING owns the worker, ComfyUI, LM Studio heavy models, and
image/video/Godot execution. Every connector must call an audited belt endpoint,
default to read-only, use an allowlist, and have an integration test.
