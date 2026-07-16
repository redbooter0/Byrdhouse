# ByrdHouse STATE

*One page of current truth. Update weekly or on any milestone. Paste this to any AI to resume work instantly.*

**Last updated:** 2026-07-16 · **Current unlock: U1 IMAGE LAB · Handoff P0 (baseline & governance) repo-side complete** · **North star: R0 (first thumbnail shipped on Carey's channel)**

**U0 status:** functionally complete on real hardware.

**Image lane handoff:** Before changing the live GAMING image workflow, read `docs/IMAGE_GENERATION_STATE.md`. It records the compact 8 GB anime target-edit lane, model allocations, licensing constraint, and hardware test gate.

## Direction

ByrdHouse is a **creator platform**, not a mining platform. Core lanes: image generation, video generation, video editing, MCP tooling, and Godot automation. Mining stays manual and seasonal; it is not the center of this system.

The system is local-first:

- **BYRD-MINI** owns orchestration: router, dashboard, SQLite ops DB, memory/Qdrant.
- **BYRD-GAMING** owns heavy GPU work: ComfyUI, LM Studio, image/video/game workers.
- **iPad** is the cockpit: dashboard/browser/manual approvals.

Odysseus/smart-home/Stripe is removed from this repo. Cherry Studio remains the local model GUI; ByrdHouse owns the router/worker/dashboard belt.

## What works now (snapshot refreshed 2026-07-11)

- **Dashboard (Phase B)**: Product Recovery Sprint shipped — 16-room admin console
  replaced by 3-tab founder cockpit: Home (WIP, approval queue, recent results,
  weekly stats), Create (image generation with founder-friendly labels), Library
  (all artifacts with filter bar). All diagnostics/admin/workers/events/exports
  behind a System gear icon. Single system dot replaces chip bar.
- **Create tab**: versioned recipes (game-anchored v3/v4 + freeform + 6 "me"
  identity recipes), aspect presets, LoRA/checkpoint override, prompt enhancement,
  BYO-screenshot thumbnails, reference library, upscale/riff on every card,
  tap-to-zoom, in-flight progress, engine controls behind power-user panel
- **Creator V1 foundation**: identity profiles (profiles/me/), subject_profile
  on recipes, worker auto-resolves face reference from profile dir, Flux2 Klein
  workflow package integrated (SAFE + PRODUCTION + MASTER + API adapter)
- **Belt**: reaper, worker liveness, requeue/cancel, previews (downscaled,
  worker→router upload), job timing joins, deterministic artifact dedupe,
  2-PC coordination (version drift, heartbeat, requeue fencing)
- **Guardrails**: 52-check integration suite in CI, BOM enforcement, judge
  fidelity/off-game caps
- **Face Lab (2026-07-15)**: `image.faceswap` job (ReActor direct swap + anime
  style-blend two-pass), dashboard Face Swap panel, `me_as_character` recipe,
  dataset collector + versioned LoRA trainer (7200MB VRAM / 16-thread founder
  limits), `facelab_preflight.py` on-PC proof tool — see docs/FACE_LAB.md
- **Handoff P0 (2026-07-16)**: the 2026-07-15 implementation handoff is adopted
  as spec of record with live-state precedence — response in
  `docs/fable-implementation-report.md`. Governance kit shipped: machine
  inventory, model-license manifest (row required before any install),
  agent-safety policy (tiers 0–4), identity-stack review (research registry
  dispositions), five-target identity benchmark spec. New scripts:
  `byrdhouse-preflight.ps1` (read-only machine/service baseline) and
  `identity-benchmark.ps1` (repeatable scorecard runner). **Next action:** run
  the preflight on both machines and paste results into the inventory; then P1
  Identity Lab (RMBG → facetools → Forbidden Vision, isolated ComfyUI).
- **ByrdCoder Local V0 (2026-07-16)**: permanent local coding agent so work
  continues when Codex/cloud usage is exhausted — OpenCode + pinned
  `opencode-lmstudio@0.3.1` bridge over the existing LM Studio, isolated
  config (`OPENCODE_CONFIG` → gitignored `LLM\byrdcoder\`), seven byrd-*
  profiles defaulting read-only, tiers 0–4 enforced (no push/merge/main/
  secrets/production-ComfyUI), 7-task model benchmark harness, two-agent
  review loop (fail-closed block). See docs/BYRDCODER_LOCAL.md. **Next
  action on GAMING:** install opencode CLI, run `byrdcoder-preflight.ps1` +
  `test-byrdcoder.ps1`, then the acceptance checkpoint and Phase 5 benchmark
  of the installed Qwen/Qwopus models.

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

## Roadmap (detailed) — refreshed 2026-07-12

**P0 hygiene (do regardless of phase):** rotate the admin token — it reached public git history.

**North star = the money gate (R0 → R3).** Phases advance on cash, not vibes.
- **R0** — first output used on Carey's OWN channel (a thumbnail good enough to ship). The real near-term goal.
- **R1 → R2 → R3** — revenue milestones; LLC/trademark unfreeze at R2; hardware cash-only.

**The single biggest R0 lever** is thumbnails that actually look like the game. That is exactly the IP-Adapter reference engine + custom license-clear checkpoints (see below and `docs/MODELS.md`).

### Unlock ladder + acceptance
- **U1 Image Lab (finishing):** 10 router-generated images, ≥5 approved with full cards, ≥2 thumbnails 1280×720 with real composited text, suite green. Recipe-slot contract bug fixed (2026-07-12); IP-Adapter reference route landed. Creator V1 foundation landed (profiles, me-recipes, Flux2 Klein).
- **U2 Command Center (Phase B shipped):** dashboard redesigned as founder cockpit — Home/Create/Library tabs, System behind gear icon. Accept: a full day's work with no terminal.
- **U3 Spine:** harden queue controls only where usage exposes friction (`parent_id`/`run_after` reserved). *Bot pilot unlocks after U3.*
- **U4 Learn Loop:** `GET /learn` already ranks by approval rate; needs enough approve/reject data to steer.
- **U5 Motion/Video:** approved images → `video.i2v` clips + `video.assemble`. After the image lane is reliable.
- **U6 Game Loop:** Godot as belt jobs (`game.godot_task`); weekend lane in Cherry Studio until then.

### Bot-operator track (parallel, gated — Bot Room A0→A3)
The always-on operator that runs the belt while Carey is away. Foundation landed 2026-07-12:
`scripts/byrd_belt_mcp.py` (belt as MCP — the bot's audited hands), `goose/` (Goose runtime + `.goosehints` identity, runs on both PCs on the local Qwen), Playwright MCP + `web_search` (research/eyes), IP-Adapter + `docs/MODELS.md` (game-faithful thumbnails).
- **A0/A1 (suggest-only):** `BYRD_BELT_MCP_READONLY=1`. **Pilot after U3.**
- **A2/A3 (acts):** flip the flag; every action stays carded, judged, audited. Autonomy is a permission, not a new build.
- **Hard line:** the bot only ever QUEUES jobs — never drives ComfyUI/GPU directly (mode ritual on the 8 GB 3070).

### Recommended sequence
1. Rotate token → deploy `main` → run the U1 acceptance test (emotion blank must block; filled must run).
2. **R0 push:** use the IP-Adapter + custom models to make a game-faithful thumbnail → ship one on Carey's channel = R0.
3. U2 (daily-usable) → U3 (spine) → bot A0 pilot (read-only operator).
4. U4 learn → U5 video → U6 Godot. Weekend Realms lane runs in parallel.

## Done log

- 2026-07-15 · RECONCILIATION: merged `agent/face-zone-cpu-first` (the PC's rescued Codex work — byrdfacezone.py CPU mesh/parse/warp/composite, `edit_face_zone` + `face_zone_identity_edit` recipe-runner lane, SD1.5 Meina stack, social swap workflow catalog, handoff docs `IMAGE_GENERATION_STATE.md`/`FACE_ZONE_EDIT_WORKFLOW.md`, target images + July-13 result library) with the merged Face Lab (preview/zone/auto/reactor routes, versioned trainer, collector, preflight). One dispatch table, one test suite (all green), lane map in FACE_LAB.md: quality lane = CPU-first mesh seed (license-clean), fast tier = preview→zone→auto, ReActor/FaceID = private experiments per funded-lane policy. Founder reference library (~300 generated identity photos + real photos under profiles/me/references/) recorded in CLAUDE.md as permanent memory. BOMs added to the nine rescued .ps1 scripts so CI stays green.

- 2026-07-15 · Face Lab shipped (docs/FACE_LAB.md): the belt can now imagine AND face-swap fully locally. `image.faceswap` job type (router+worker+dashboard panel) over two new ReActor graphs — direct swap for photo targets, swap + low-denoise style-blend pass for anime targets (Gojo/Vegeta/Luffy) so the face melts into the art style; `me_as_character.v1` recipe is the generation route (FaceID + anime checkpoint + identity LoRA). LoRA lab: `collect-training-images.ps1` moves the newest ~300 generated images into `training/datasets/<name>/img`, `train-lora.ps1` wraps kohya sd-scripts with 8GB-3070-safe settings and founder limits from config (`training.vram_budget_mb` 7200 verified via nvidia-smi before start, `training.cpu_threads` 16 max 18) and ALWAYS writes a new versioned file (`carey_face_v2`, `_v3`, ... — never overwrites). `facelab_preflight.py` proves the function on the PC against the live ComfyUI (node pack, models, schema cross-check, `--run` = real swap, MINI not needed). `find-codex-work.ps1` locates Codex's local files/sessions/unpushed work; its pushed trail is mapped in FACE_LAB.md (fix/* + agent/* branches, incl. Luna Pulse supervision). Integration suite +8 checks (faceswap direct/blend/honesty/judge, preflight diagnosis), dashboard suite untouched-green. inswapper license flagged: non-commercial — monetized output should use the LoRA/FaceID route. Founder's screenshots then recovered Codex's full trail (sessions 2026-07-14): 300-image dataset audited under `profiles/me/references/generated_real_skit_scenes/` (collector now searches generated_* subfolders; real reference-root photos stay put), a 37.9MB LoRA already trained (1600 steps, step-400 checkpoint gated most personal), CPU mesh-to-mesh seed (`byrdfacezone.py` + UNCOMMITTED `edit_face_zone` edits in the PC's byrdimage.py — rescue branch required before any pull), and the founder zone rule; landed its v1 as the belt's zone route: `image.faceswap` + mask → VAEEncodeForInpaint corridor-clamped denoise (default 0.7), dashboard Edit-zone field, CLI `--swap-mask`, trainer auto-sizes repeats to ~2,500 steps for the 300-image dataset. Suite +2 (zone archive, corridor card). Then the daily driver landed: AUTO route — Impact Pack FaceDetailer graph (`facezone_auto_api.json`) detects the character's face, masks it, redraws it as the founder (LoRA + prompt) in the target's art style, composites back; dashboard Face Swap route picker defaults to it, `payload.route="auto"`, CLI `--auto`, preflight checks Impact Pack/Subpack + detector and `--route auto` runs the real proof. Test targets: Gojo, Vegeta, Luffy, Link. Suite +2 (auto archive, detector card). PR #23 merged to main 2026-07-15; branch restarted from main for follow-ups. Then the CPU pre-step landed (founder asked for Codex's "GPU never decides the mask" idea done better): PREVIEW route — detection-only graph (`facezone_preview_api.json`, runs in ANY mode, no checkpoint) archives the zone overlay + soft mask as approvable artifacts; the approved mask chains into the zone route by artifact id (dashboard "zone from a preview" box). Suite +4 (two-artifact preview, _overlay/_mask naming, detector/threshold card, mask→zone chain).

- 2026-07-12 · Phase B Product Recovery Sprint: dashboard rewritten from 16-room admin console to 3-tab founder cockpit (Home/Create/Library). All diagnostics behind System gear icon. Single system dot replaces chip row. Creator V1 foundation: identity profiles (profiles/me/), 6 "me" recipes (cinematic/founder/fantasy/outfit_transfer/thumbnail/animated), worker face-reference auto-wiring, Flux2 Klein package (SAFE + PRODUCTION + MASTER workflows, API adapter, install script). 2-PC coordination hardening committed separately. Integration suite green. No router/worker behavior changes.
- 2026-07-12 · Recipe-slot contract bug fixed on real hardware (jobs died on `unfilled slots ['emotion']`): dashboard now renders every non-vary slot as a required `*` input and `submitGen` blocks + names missing slots before POST; `byrdimage` guarantees vary slots fill and fails loudly on empty vary arrays; dashboard test suite repaired (PR#18 had crashed it) and expanded with required-slot coverage. Then landed the R0 lever: IP-Adapter reference engine (`game_ref` recipe + `sdxl_ipadapter_api.json` — a real uploaded screenshot steers the checkpoint toward THE game's look), Goose bot-operator foundation (`scripts/byrd_belt_mcp.py` belt-as-MCP + `goose/` runtime/identity + `web_search`), and the custom license-clear model kit (`docs/MODELS.md`: animagine-xl-4.0 / RealVisXL_V5.0 / dreamshaper-xl, all openrail++). Integration 70-check + dashboard 20-check green. PR #19 merged. OPEN (founder): rotate the admin token (public git history).
- 2026-07-11 · Hardening from two-agent review (integrity before the U1 proof, no new features): judging now REQUIRES a vision-capable model (a text model can't invent visual scores — artifact stays honestly unjudged, protecting the learn-loop dataset); checkpoint fallback is recorded on the card (requested-vs-resolved) and flagged yellow in the gallery instead of silently running the wrong model; chat write-tools capped at 3 mutations/request; CI secret-scan job fails the build on a committed token/key; fixed the last config mojibake; docs/BELT.md gained an honest security/trust-boundary section (single-token tailnet system, deferred video-heartbeat + monolith-split). 57-check belt suite green. OPEN ACTION (founder): rotate the admin token — it reached public git history

- 2026-07-11 · Belt strengthening (reverse-engineered durable-execution patterns, see docs/BELT.md): schema migration spine (guarded additive ALTER TABLE — belt schema now evolves on live machine DBs without a wipe), idempotency keys (same key returns the existing job; kills the duplicate-job class at the source), and parent_id/run_after columns migrated in and reserved for the DAG/scheduling rungs. docs/BELT.md maps every canonical job-queue pattern (Temporal/river/event-sourcing) to what the belt already has and the compounding ladder ahead. 55-check belt suite green

- 2026-07-11 · Learn loop + boot fix + UI declutter: GET /learn projects the belt's own approve/reject history into approval-rate rankings by recipe/checkpoint/palette/lighting (reverse-engineered reinforcement signal from data already stored) + "what_works" chat tool + "What's working" panel; FIXED the real GAMING bug — the OPERATOR mode switch force-loaded operator_model even when a usable model (e.g. the VL judge) was already loaded, thrashing LM Studio's CORS/connection and failing the first request; now it uses whatever's loaded (docs/LMSTUDIO_SETUP.md covers the persistent CORS/serve-on-LAN settings); dashboard decluttered — verbose inline field descriptions replaced with clean labels + `?` tooltips, optional fields folded under "More options", and the mobile nav rebuilt from a full-screen stacked room list into a slim horizontal chip strip. 54-check belt suite green

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

