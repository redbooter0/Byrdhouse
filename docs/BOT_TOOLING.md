# Bot Tooling — the operator that runs the belt

*The founder's dream (2026-07): an always-on operator that lives on both
machines and runs the belt while Carey is away. The belt is the environment the
bot operates in and out of. This doc is the plan and the wiring.*

## The one idea

ByrdHouse already had **two tool systems that never talked to each other**:

1. The belt's in-app chat (`router.py` → `CHAT_TOOLS`): the model could already
   `queue_image`, `list_artifacts`, `get_status`… but only inside the dashboard.
2. The declared MCP roster (`byrdhouse.config.json` → `mcp`): memory, filesystem,
   fetch, brave-search, sqlite, lmstudio-bridge, godot — live in Cherry Studio,
   but blind to the belt.

Same Qwen model, two protocols. **We bridged them** so one shared roster drives
everything, on either machine, over the tailnet:

- **`scripts/byrd_belt_mcp.py`** — the belt as an MCP server. A stdlib, no-pip
  JSON-RPC/stdio server that exposes the router's already-audited endpoints as
  MCP tools (`belt_status`, `list_artifacts`, `what_works`, `recent_events`,
  `queue_image`, `compose_thumbnail`, `review_artifact`). Every tool just calls
  the router on `byrd-mini:8787`; nothing new is trusted, nothing bypasses the
  audit log. Drop it into Cherry Studio / LM Studio and the bot you already use
  gains the belt.
- **`web_search`** added to the in-app `CHAT_TOOLS` — the dashboard chat's
  research tool (config-driven `services.search`), the in-app twin of the
  brave-search MCP the bot uses in Cherry Studio. Both surfaces, one capability.

## The hard line (do not cross)

The bot **never touches ComfyUI or the GPU directly.** Ready-made ComfyUI MCP
servers exist ([artokun/comfyui-mcp](https://github.com/artokun/comfyui-mcp),
[joenorton](https://github.com/joenorton/comfyui-mcp-server)) — we **reject them
on purpose**. They would bypass the job queue, the sidecar cards, and the **GPU
mode ritual** on the 8 GB 3070 (modes are exclusive; two engines on VRAM = crash).
The bot **queues a job**; the worker owns the GPU. Every image the bot makes is a
real, carded, judged, audited belt job.

## The autonomy ladder is a permission, not a build

`BYRD_BELT_MCP_READONLY=1` hides and blocks every write tool
(`queue_image`, `compose_thumbnail`, `review_artifact`) — the bot can look but
not act (A0/A1: suggestions from the event log). Flip it off and the bot acts
(A2+). That single flag *is* the ladder — exactly what the blueprint promised:
"autonomy is a permissions change on audited endpoints, never a separate build."

## Wiring on the two machines

| Machine | Runs | Notes |
|---|---|---|
| **BYRD-MINI** | router + `byrd_belt_mcp` + memory/fetch/brave-search MCP | all CPU, no GPU contention |
| **BYRD-GAMING** | worker (owns ComfyUI + LM Studio via mode ritual) + Godot + godot MCP | the muscle; pulls jobs |
| **Cockpit (iPad / Cherry Studio)** | MCP client → belt + research + godot | one roster, over Tailscale MagicDNS |

Register the belt in an MCP client:

```json
{ "command": "python",
  "args": ["D:/ByrdHouse/scripts/byrd_belt_mcp.py"],
  "env": { "BYRDHOUSE_ROOT": "D:/ByrdHouse" } }
```

## The bot's loop (gather → act)

1. **Gather** with read tools / research MCP: `web_search` or brave-search for
   viral references, `what_works` for the founder's proven settings, `list_artifacts`.
2. **Bring in real pixels**: upload a screenshot via `/sources` (recorded at top
   grade) — the endpoint is already live.
3. **Act** through the belt: `queue_image` (recipe + slots) or `compose_thumbnail`
   (title onto a source). The worker runs it under the mode ritual.
4. **Judge & learn**: the belt auto-judges; `review_artifact` feeds the learn loop.

## Research adopted (PulseMCP / niche scan, 2026-07)

- **Keep the "core six" + weekend two** already in `config.mcp`; they match the
  best-with-LM-Studio picks (SQLite, Brave, Fetch, memory). Source:
  [PulseMCP directory](https://www.pulsemcp.com/servers),
  [Godot MCP servers](https://www.pulsemcp.com/servers?q=godot).
- **Reject** direct ComfyUI-MCP control (see hard line above).
- **Godot MCP** (live-editor control, 120+ tools) is the model for
  `game.godot_task` at U6 — the "godot automation mindset" the founder wants.

## Status

- [x] belt-as-MCP server (`scripts/byrd_belt_mcp.py`) — tested (handshake,
      roster, read proxy, real job queue, read-only gate)
- [x] `web_search` in the in-app chat roster — config-driven, graceful
- [ ] stand up the research + godot MCP servers on the machines (fill
      `config.mcp` ping URLs; register belt-MCP in Cherry Studio)
- [ ] widen `WRITE_TOOLS` permission tiers for the A2 pilot
