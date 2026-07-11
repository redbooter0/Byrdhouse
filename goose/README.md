# The BYRD operator (Goose) — setup

The bot runtime. You don't build an agent in Python — [Goose](https://github.com/aaif-goose/goose)
(Block, Apache-2.0) is MCP-native, runs on your local Qwen via LM Studio, and has
a headless CLI so it lives on both PCs while they're on.

## What's in here
- **`.goosehints`** — the bot's identity, role, the belt, and the hard lines. Goose
  reads this so BYRD already knows what it can and can't do.
- **`config.yaml`** — provider (LM Studio/Qwen) + the extension roster: `byrd-belt`
  (the belt as MCP), `playwright` (browser), `memory`, `developer` (files).

## Install (each machine, Windows)
1. Install Goose (desktop or CLI): `winget install Block.Goose`.
2. Run `goose configure` once → choose an **OpenAI-compatible** provider, host =
   your LM Studio (`http://byrd-gaming:1234`), model = `qwen/qwen3.5-9b`. This lets
   Goose write the correct provider keys for your version.
3. Copy `config.yaml`'s `extensions:` block into `%USERPROFILE%\.config\goose\config.yaml`.
4. Copy `.goosehints` next to it (or into the working dir you launch Goose from).
5. Set `BYRDHOUSE_ROOT` in the `byrd-belt` extension to this machine's root
   (`D:/ByrdHouse` on MINI, `E:/ByrdHouse` on GAMING).
6. Node is required for Playwright MCP: `npx @playwright/mcp@latest` (first run
   pulls it). Chromium installs on first browser use.

## Run
- Interactive: `goose session`
- Headless / away-from-home (one task): `goose run -t "make three Palworld
  thumbnail options from a fresh screenshot and queue them"`
- Persistent operator: wrap `goose run` in a Windows Scheduled Task (or the
  existing `install-startup-task.ps1` pattern) so BYRD wakes on logon.

## The autonomy ladder (no rebuild)
- **A0/A1 — suggest only:** set `BYRD_BELT_MCP_READONLY: "1"`. The write tools
  (`queue_image`, `compose_thumbnail`, `review_artifact`) disappear from the
  roster; BYRD can look and recommend but not act.
- **A2+ — act:** flip it to `"0"`. Everything BYRD does is still a real, carded,
  judged, **audited** belt job (it shows in the event log and the dashboard).

## The hard line
BYRD **never** drives ComfyUI or the GPU directly — it queues jobs the worker
pulls under the mode ritual. That's why the belt is exposed as MCP (`byrd-belt`)
and the ready-made ComfyUI MCP servers are deliberately NOT used. See
`docs/BOT_TOOLING.md`.
