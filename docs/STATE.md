# ByrdHouse STATE

*One page of current truth. Update weekly or on any milestone. Paste this to any AI to resume work instantly.*

**Last updated:** 2026-07-10 · **Current unlock: U1 IMAGE LAB**

**U0 status:** functionally complete on real hardware.

## Direction

ByrdHouse is a **creator platform**, not a mining platform. Core lanes: image generation, video generation, video editing, MCP tooling, and Godot automation. Mining stays manual and seasonal; it is not the center of this system.

The system is local-first:

- **BYRD-MINI** owns orchestration: router, dashboard, SQLite ops DB, memory/Qdrant.
- **BYRD-GAMING** owns heavy GPU work: ComfyUI, LM Studio, image/video/game workers.
- **iPad** is the cockpit: dashboard/browser/manual approvals.

Odysseus/smart-home/Stripe is removed from this repo. Cherry Studio remains the local model GUI; ByrdHouse owns the router/worker/dashboard belt.

## What works now (snapshot refreshed 2026-07-11)

- **Image Studio**: versioned recipes (game-anchored v3/v4 + freeform), aspect
  presets, LoRA field, checkpoint override, ✨ LLM prompt enhancement, seed pin,
  BYO-screenshot thumbnails, viral compositor (banner/accent), reference
  library (judge grades against founder-loved thumbnails), ⬆ upscale / ≈ riff
  on every card, tap-to-zoom, in-flight placeholders with ages, ⏱ durations
- **Operator Chat**: agent with belt tools (status, artifacts, queue_image,
  refine_image, events), model interchangeability, mini-fallback slot for
  always-on chat, answering model shown per reply
- **Belt**: reaper, worker liveness, requeue/cancel, previews (downscaled,
  worker→router upload), job timing joins, deterministic artifact dedupe
- **Guardrails**: 52-check integration suite + 13-check dashboard suite in CI,
  BOM enforcement, judge fidelity/off-game caps

## What worked before (U0 foundation)

- Dashboard/router are served from BYRD-MINI at `http://byrd-mini:8787`.
- Memory/Qdrant live on BYRD-MINI and drift check is green there.
- BYRD-GAMING worker is online against the MINI router.
- ComfyUI on BYRD-GAMING accepts router-submitted jobs.
- LM Studio on BYRD-GAMING serves operator and vision judge models.
- Image job path is proven end-to-end: queue → generate → archive PNG → sidecar card → auto-judge → approve.
- U0 smoke artifact approved:
  `E:\ByrdHouse\artifacts\careyrpg\2026-07\20260710_rpg_tier_list_job_19f4df7994cy1iwb6_00001_.png`
- Integration test passes on repo main: `python tests\integration_test.py`.
- GitHub main is source of truth: `https://github.com/redbooter0/Byrdhouse.git`.

## Known non-blocking yellow states

These are not reasons to rerun setup:

- `host_vault` yellow when BYRD-VAULT is off/unreachable.
- GAMING `memory_drift` yellow because memory belongs on MINI.
- MINI `gpu` yellow because MINI has no NVIDIA GPU.
- Old `dead` jobs in the queue from previous debugging. Ignore unless a new job cannot run.

## Anti-command-loop rules

1. Do not rerun `setup-gaming.ps1` or `setup-mini.ps1` unless a machine was wiped or a setup script changed.
2. Run `byrd-status.ps1` once before a work block and once after. Do not use it as a loop.
3. If the same yellow appears twice and is listed above, log it and move on.
4. Do not debug historical `dead` jobs unless they block new jobs.
5. Do not rebuild router/worker/dashboard for U1. Use them.
6. A phase advances when its acceptance test passes once on real hardware and once in repo tests.
7. GitHub push comes after a bounded change and verification, not after every command.

## U0 STABILIZE closeout

U0 is considered complete for forward progress.

Acceptance evidence:

- MINI router/dashboard reachable.
- GAMING worker online.
- Real image generated from a router job.
- Real vision judge completed after worker fix.
- Artifact approved through router review endpoint.
- Repo main pushed with fixes and Odysseus removal.

Remaining U0-adjacent hardening:

- Cold-reboot both machines and confirm startup tasks bring the belt back.
- Install/verify BYRD-VAULT nightly backup when vault is available.

These are maintenance checks, not blockers for U1.

## U1 IMAGE LAB plan

Goal: turn the working image belt into a repeatable CareyRPG asset factory.

### U1 work orders

1. Generate 10 CareyRPG test images through the dashboard/router, not manual ComfyUI clicks.
2. Approve/reject every image from the gallery.
3. Record recipe weaknesses in sidecar/rubric notes.
4. Improve the starter recipes:
   - `rpg_tier_list`
   - `build_guide`
   - `shock_reveal`
   - `vs_matchup`
   - `yt_thumbnail`
5. Validate two-pass thumbnails: model generates art only, Pillow composites real text.
6. Export a CSV of approved/rejected artifacts.

### U1 acceptance test

U1 is complete when:

- 10 images generated from router jobs.
- At least 5 approved.
- Every approved image has score, tags, caption, prompt, seed, checkpoint, and purpose.
- At least 2 thumbnail finals exist at 1280x720 with real composited text.
- `python tests\integration_test.py` passes after any code changes.

## Next unlock after U1

U2/U3 are already partially built, but they should be treated as usage/hardening phases now:

- **U2 Command Center:** make dashboard daily-usable, not prettier.
- **U3 Spine:** harden queue controls only when real usage exposes friction.
- **U4 Learn Loop:** starts after there are enough approved/rejected artifacts to learn from.
- **U5 Motion/Video:** starts after U1 thumbnail/image flow is reliable.
- **U6 Game Loop:** Godot/Realms integration stays weekend lane until image/content lane is stable.

## Done log

- 2026-07-11 · Night polish: brand pass (hawk logo in-app, room icons, glow layer — mockup in branding/ is the U2 target), compatibility audit green (py_compile, JSON+BOM, PS1 BOM, UTF-8, 51-check belt), full browser proof of chat-tool→generation→gallery loop, docs/WAKE_UP.md with morning update prompts for both machines

- 2026-07-11 · Image Studio capability sprint: aspect presets (16:9/9:16/1:1/2:3/3:2/21:9, SDXL-native snapping), image.refine runner (img2img: upscale at low strength, variations at high — POST /artifacts/id/refine + upscale/riff buttons on every card), LoRA support (loose-matched from models/loras, graph-spliced LoraLoader — the "any game accurately" unlock once game LoRAs are downloaded), content.enhance (operator model rewrites a freeform prompt in OPERATOR mode then auto-enqueues generation — GPU modes stay exclusive), negative/seed payload overrides, sdxl_img2img workflow + mock upload support. Integration test 44 checks

- 2026-07-10 · U0 polish sprint (9 root-cause fixes, one commit each): charset=utf-8 on all responses; artifact dedupe via deterministic IDs + latest-per-(job,path) query; state-aware approve/reject buttons; adaptive auto-refresh (4s active / 15s idle / paused hidden); PNG previews via worker→router byte upload (files live on GAMING, router on MINI); manual GPU-mode buttons removed (worker self-schedules); in-flight job placeholders; mobile Safari cleanup; worker/router dedup refactor + live transition logging. Integration test now 29 checks

- 2026-07-10 · U0 real-hardware belt completed: MINI router + memory home, GAMING worker online, ComfyUI image generated, Qwen-VL judge scored it, artifact approved, GitHub main pushed at `861ef4a`.
- 2026-07-10 · Removed Odysseus/smart-home/Stripe stack from repo; Cherry Studio remains the local model GUI.
- 2026-07-10 · Belt hardening: router reaper thread requeues jobs stuck on a dead worker, worker liveness computed server-side, `/jobs/{id}/requeue` and `/jobs/{id}/cancel` added. Integration test includes requeue/cancel/liveness/status checks.
- 2026-07-10 · BYRD-MINI bootstrapped: router + dashboard serving from `http://byrd-mini:8787`; memory/Qdrant lives on MINI.
- 2026-07-10 · Content engine shipped: `content.thumbnail`, `content.package`, `content.research`, `export.csv`.
- 2026-07-10 · Full belt shipped and integration-tested: router API, worker daemon, judge loop, dashboard, backup script, retry/dead path.
- 2026-07-10 · Gaming-PC side completed: startup command, logon task, image submit layer, SDXL workflow.
- 2026-07-10 · U0 kit committed to GitHub; repo is the kit distribution channel.
- 2026-07-08 · U0 kit designed.
