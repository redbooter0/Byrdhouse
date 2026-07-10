# ByrdHouse

Local-first AI command platform: iPad Pro cockpit · BYRD-MINI nervous system · BYRD-GAMING heavy worker.

This repo is the **source of truth for the ByrdHouse platform kit** — config, status tooling, docs, and recipes that get synced onto the machines. The full vision lives in the Master Blueprint docs (v2 technical spec, v3 Money Map, v3.1 Content Engine); the current build stage is **U0 STABILIZE** (see `docs/STATE.md`).

## Quick start — BYRD-GAMING (E:\ByrdHouse)

```powershell
git clone https://github.com/redbooter0/Byrdhouse C:\src\Byrdhouse
cd C:\src\Byrdhouse
powershell -ExecutionPolicy Bypass -File scripts\setup-gaming.ps1
```

The setup script creates the `E:\ByrdHouse` directory map, installs the config template (edit the `CHANGE_ME` placeholders!), sets `BYRDHOUSE_ROOT`, reports missing tools (Tailscale, LM Studio CLI, nvidia-smi), and runs the first `byrd-status`.

For BYRD-MINI, same thing with `scripts\setup-mini.ps1` (roots at `D:\ByrdHouse`, hosts the ops database).

## What's in here

| Path | What |
|------|------|
| `byrdhouse.config.json` | ONE config: hosts (Tailscale names, never IPs), services, GPU modes, MCP roster, memory drift settings |
| `scripts/byrd-status.ps1` | Green/yellow/red health report + `status.json` (hosts, services, VRAM, disk, Qdrant drift, MCP pings) |
| `scripts/setup-gaming.ps1` / `setup-mini.ps1` | Idempotent machine bootstrap |
| `scripts/use-image-mode.ps1` | GPU mode ritual: unload LLMs, verify VRAM free, `-Restore` reloads the operator model |
| `scripts/start-byrdhouse.ps1` | THE one command: LM Studio server + operator model + ComfyUI + status report |
| `scripts/install-startup-task.ps1` | Registers start-byrdhouse as a logon scheduled task (run as admin, once) |
| `scripts/byrdimage.py` / `.ps1` | Image submit layer: recipe → filled prompt → random seed → unique prefix → ComfyUI → archived PNG + metadata card (stdlib-only Python) |
| `workflows/sdxl_base_api.json` | SDXL text2img graph (ComfyUI API format) the submit layer fills at runtime |
| `scripts/rag_system.py` | Lightweight local RAG (document chunks + index on disk) |
| `docs/STATE.md` | One page of current truth — update weekly |
| `docs/DECISIONS.md` | Append-only decision log |
| `docs/ROOM_MAP.md` | The 14 rooms, two lanes, MCP roster |
| `docs/CLAUDE_CODE_TASKS.md` | U0 work orders to hand to Claude Code on each machine |
| `recipes/` | Versioned image recipes: `yt_thumbnail` + the CareyRPG pack (tier list, build guide, shock reveal, vs matchup) |
| `backend/` + `odysseus/` + `docker-compose.yml` | Auxiliary smart-home/AI-hub stack (Node Stripe backend + FastAPI HA/Ollama gateway) — see `docs/SMART_HOME_HUB.md`. Monetization surface **frozen** per Blueprint v2 §1.8 until real external demand |

## The operating rules (from the blueprints)

- **One belt, three loops:** everything is a job → artifact → judged → learned from. Rooms are views onto the belt.
- **Zero hardcoded IPs:** every script reads `byrdhouse.config.json`; hosts are Tailscale MagicDNS names.
- **No artifact without a metadata card; no card without a purpose.**
- **GPU modes are exclusive:** the 3070 is in OPERATOR, IMAGE, or VIDEO mode — transitions are verified rituals, not hope.
- **Cash-gate law:** hardware is bought with cash after a measured bottleneck, never financed.
- **Nothing public:** all cross-machine traffic rides the tailnet. Nothing is ever exposed to the internet.

## Roadmap (unlocks)

U0 STABILIZE → U1 IMAGE LAB → U2 COMMAND SURFACE → U3 SPINE → U4 LEARN LOOP → U5 MOTION → U6 GAME LOOP. Definitions of Done in Blueprint v2 §12; live progress in `docs/STATE.md`.
