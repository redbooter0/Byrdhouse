# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Current Windows PC handoff — 2026-10-03

2026-10-04 hairline/CPU-mesh update: read
`docs/reviews/2026-10-04-hairline-v2-and-face-mesh.md`. Current queued
likeness reviews bind V2 examiner code/weight hashes; old reports/profiles
remain historical. The existing MediaPipe loader/model and configured paths
work for CPU analysis. Full target-aligned face editing is still unqualified.

2026-10-04 FreeVideo newer-source/licensing follow-up is saved in
`docs/reviews/2026-10-04-freevideo-follow-up.md`. It establishes no AMD
drop-in path and records H3's standard territorial exclusions. No H3
deployment was made; native Wan remains the tested local preview route.

2026-10-04 update: Studio now queues matching-view CPU continuity checks for
illustrated stills and all collected clip frames. Read
`docs/reviews/2026-10-04-studio-continuity-review-validation.md`. The approved
Carey sheets remain canon; new media remains subject to separate visual
approval. Diagnostic report images cannot be animation inputs. CPU review
restart passed locally; do not claim GPU mid-render restart from that test.

The active deployment is `D:\ByrdHouse` on Carey's Windows PC with an RX 7900 XT
20 GB, i9-10850K and 32 GB RAM. The attached 2 TB HDD is D:; the mini PC remains
deferred. The historical RTX 3070 / E: / two-PC descriptions below are not this
machine's current hardware or deployment. Read `docs/STATE.md`,
`docs/IMAGE_GENERATION_STATE.md`, `docs/reviews/README.md` and
`docs/CURRENT_PC_IMPROVEMENT_PLAN.md` before continuing this lane.

Carey explicitly requested that detailed reviews be saved locally so future work
builds on them. Retain dated reviews and add real validation when implementing
their proposals. The correction queue bypass is now fixed; read
`docs/reviews/2026-10-03-queue-recovery-validation.md` for resume behavior and limits.
New stills bind fixed reference inputs and source-preservation pixel checks pass;
read `docs/reviews/2026-10-03-source-preservation-validation.md` for the two
rejected scenes and boundary-quality gap. Current gaps include generated
identity drift, hair-edge/background compositing, a live mid-render restart
test and sustained AMD worker health.
Exact likeness is unapproved; similarity/geometry scores are not identity proof.
Do not restart first-install loops or treat a proposed improvement as completed.

## What ByrdHouse Is

A local-first AI command platform run by one founder (Carey) across three devices: iPad Pro (cockpit/browser), BYRD-MINI (`D:\ByrdHouse` — orchestration: SQLite ops db, Qdrant, memory MCP, future router/dashboard) and BYRD-GAMING (`E:\ByrdHouse` — RTX 3070 heavy worker: ComfyUI, LM Studio, Godot). This repo is the **source of truth for the platform kit**; the machines sync from it via `scripts/setup-*.ps1`.

The governing documents are the Master Blueprint v2 (technical spec: job envelope, SQLite schema, Router API, GPU modes, unlock roadmap U0–U6), v3 (money-gated sequencing) and v3.1 (content engine). Condensed operating state lives in `docs/STATE.md` (current truth — update it on milestones), `docs/DECISIONS.md` (append-only) and `docs/ROOM_MAP.md`.

Before changing any image model, ComfyUI graph, face/identity workflow, or worker image route, read `docs/IMAGE_GENERATION_STATE.md` first. It is the persistent handoff for the live GAMING image lane; update it with the model, VRAM result, and real local test outcome before calling that lane ready.

For uploaded face-zone edits, use the documented belt in `docs/FACE_ZONE_EDIT_WORKFLOW.md`: upload -> CPU 478-point mesh + semantic parser -> detect the neck and keep the connected face/head/ears above it minus hair/headwear/accessories/clothing -> warp the reviewed Carey anime reference through the target mesh -> low-denoise GPU cleanup with `VAEEncode` + `SetLatentNoiseMask` -> CPU soft composite. Do not substitute a rectangle mask, silently guess after semantic failure, or bypass the audited job route. The current ParseNet anime fallback is private-local-evaluation-only pending deployment license review/replacement. Treat every identity LoRA and the local Meina checkpoint as private previews until visual and license gates pass.

## Current Stage: U1 IMAGE LAB

Work orders are in `docs/CLAUDE_CODE_TASKS.md`. U0 is functionally complete on real hardware: BYRD-MINI serves the router/dashboard and owns memory/Qdrant, BYRD-GAMING runs the GPU worker, a router-submitted image was generated, judged, and approved, and `main` was pushed with the final worker/judge fixes. The active work is U1: use the belt to generate/review CareyRPG image and thumbnail assets.

The belt in this repo: `router/router.py` (API v1 per v2 §6 + SQLite schema per §5, serves `dashboard/index.html`) ← `scripts/worker.py` (pull-based daemon on GAMING: mode ritual, image.generate via `byrdimage.generate()`, image.judge via `byrdjudge.judge_card()`, auto-enqueues judge jobs after generation). BYRD-MINI is the router/memory home; BYRD-GAMING is the heavy worker.

Do not restart setup loops. `setup-gaming.ps1` and `setup-mini.ps1` are for first install or repair after a material setup-script change. For normal work, use the dashboard/router, run `byrd-status.ps1` once before and once after, and ignore documented non-blocking yellows (`host_vault`, GAMING memory drift placeholder, MINI no GPU, old dead jobs).

## Hard Rules (from the blueprints — enforce these in any code you touch)

- **Zero hardcoded IPs/hosts/ports.** Every script reads `%BYRDHOUSE_ROOT%\byrdhouse.config.json`; hosts are Tailscale MagicDNS names (`byrd-gaming`, `byrd-mini`, `byrd-vault`). PowerShell: `$cfg = Get-Content "$env:BYRDHOUSE_ROOT\byrdhouse.config.json" -Raw | ConvertFrom-Json`.
- **Everything is a job** (canonical envelope in Blueprint v2 §3): `queued → claimed → running → needs_review → approved/rejected`, failures retry then go `dead`. Workers PULL from the router; MINI never pushes into GAMING.
- **No artifact without a sidecar metadata card; no card without a purpose** (v2 §8: prompt, negative, seed, checkpoint, recipe, score, tags).
- **GPU modes are exclusive** on the 8GB 3070: OPERATOR (LLM) / IMAGE (ComfyUI) / VIDEO. Transitions must verify VRAM via nvidia-smi (`scripts/use-image-mode.ps1`), never assume.
- **Recipes over prompts:** image generation goes through versioned recipe JSONs in `recipes/` with variation lists and rubrics. Seeds are randomized at submit time; filename prefixes are unique per job.
- **Dashboard contains no logic** — every button is an API endpoint first. Bot autonomy is a permissions change on audited endpoints, never a separate build.
- **Nothing is exposed to the public internet.** Tailnet only.
- **SQLite (WAL) is the queue and database** — do not introduce Redis, brokers, or heavier infra at this scale.

## Repo Layout & Commands

- `byrdhouse.config.json` — config template (placeholders say `CHANGE_ME`; real values live only on the machines).
- `scripts/` — PowerShell kit: `setup-gaming.ps1` / `setup-mini.ps1` (idempotent bootstrap), `byrd-status.ps1` (health report + `status.json`, exit 0/1/2 = green/yellow/red), `start-byrdhouse.ps1` (the one startup command), `install-startup-task.ps1` (logon task), `use-image-mode.ps1` (mode ritual). Python is stdlib-only by design (`byrdimage.py` submit layer, `rag_system.py`) — no pip installs on the machines.
- `workflows/` — ComfyUI API-format graphs; `byrdimage.py` fills checkpoint/prompt/seed/prefix at submit time and aborts if any CLIPTextEncode node would go stale. Test changes against a mock ComfyUI (`/prompt`, `/history/{id}`, `/view`) rather than live.
- `recipes/` — versioned image recipes. Thumbnail text is NEVER diffused — art is generated, text is composited afterward (v3.1 §3).
- Odysseus/smart-home/Stripe code is intentionally not part of this repo. Do not reintroduce it without a new founder decision; the active local model GUI is Cherry Studio, while ByrdHouse owns the router/worker/dashboard belt.
- **Tests:** `python tests/integration_test.py` runs the whole belt (real router + worker against mock ComfyUI/LM Studio, including requeue/cancel/liveness/status checks) with zero GPU — run it after touching router/worker/byrdimage/judge/compositor code. CI (`.github/workflows/ci.yml`) runs it on every push plus PowerShell syntax parsing and JSON validation. Pillow is the kit's only pip dependency (thumbnail compositor).
- **Content engine (v3.1):** `content.thumbnail` is two-pass — recipe art via ComfyUI, then REAL text composited by `scripts/compose_thumbnail.py`; never let a model diffuse title text. `content.package` injects `recipes/voice_carey.json` few-shots so output sounds like Carey. `content.research` ranks outlier CSVs.

## Conventions

- Scripts target Windows PowerShell 5.1 (both machines are Windows). Keep them dependency-free.
- `.env` is gitignored; never commit tokens (HF, admin_token, local service credentials).
- When completing a work order: check the box in `docs/STATE.md`, add a Done-log line, and record any decision in `docs/DECISIONS.md` (append-only, one line, with date and why).
- The founder prefers GUI-first workflows (Cherry Studio, dashboards); terminal commands are backend/maintenance tools. Provide exact copy-paste commands when instructing.
