# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What ByrdHouse Is

A local-first AI command platform run by one founder (Carey) across three devices: iPad Pro (cockpit/browser), BYRD-MINI (`D:\ByrdHouse` — orchestration: SQLite ops db, Qdrant, memory MCP, future router/dashboard) and BYRD-GAMING (`E:\ByrdHouse` — RTX 3070 heavy worker: ComfyUI, LM Studio, Godot). This repo is the **source of truth for the platform kit**; the machines sync from it via `scripts/setup-*.ps1`.

The governing documents are the Master Blueprint v2 (technical spec: job envelope, SQLite schema, Router API, GPU modes, unlock roadmap U0–U6), v3 (money-gated sequencing) and v3.1 (content engine). Condensed operating state lives in `docs/STATE.md` (current truth — update it on milestones), `docs/DECISIONS.md` (append-only) and `docs/ROOM_MAP.md`.

## Current Stage: U0 STABILIZE

Work orders are in `docs/CLAUDE_CODE_TASKS.md`. The U0 Definition of Done: cold-reboot both PCs → one command each → `byrd-status` all green → one image generated end-to-end. Do not build ahead of the unlock ladder (U1 Image Lab → U2 Command Surface → U3 Spine/job queue → …). Frozen until real demand: user accounts, credits, newsletters, monetization surfaces, Unreal, video generation.

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
- `backend/` + `odysseus/` — auxiliary smart-home/AI-hub stack (see `docs/SMART_HOME_HUB.md`): Express + Stripe proxy (port 3001) → Odysseus FastAPI gateway (port 3000, OpenAI-compatible `/v1/*` + Home Assistant `/api/home/*`) → Ollama. Run via `docker-compose up -d`, or `npm start` in `backend/` and `uvicorn main:app --port 3000` in `odysseus/`. The Stripe/monetization surface is frozen; don't extend it.
- No test suite yet. Sanity checks: `node --check backend/server.js`; `python -c "from main import app"` in `odysseus/`; JSON validity for config/recipes.

## Conventions

- Scripts target Windows PowerShell 5.1 (both machines are Windows). Keep them dependency-free.
- `.env` is gitignored; never commit tokens (Stripe, HA, HF, admin_token).
- When completing a work order: check the box in `docs/STATE.md`, add a Done-log line, and record any decision in `docs/DECISIONS.md` (append-only, one line, with date and why).
- The founder prefers GUI-first workflows (Cherry Studio, dashboards); terminal commands are backend/maintenance tools. Provide exact copy-paste commands when instructing.
