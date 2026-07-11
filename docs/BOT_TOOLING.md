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
everything, on either machine, over the private network. The current machines
are on LAN; a tailnet is only true after Tailscale is installed and verified:

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
| **Cockpit (iPad / Cherry Studio)** | MCP client → belt + research + godot | LAN today; private overlay required for away-from-home access |

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

- **Keep the bounded core-seven + one weekend Godot server** in `config.mcp`; they match the
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

The bounded eight-server roster now includes `byrdhouse-belt` as a core server
and keeps one real Godot server. The redundant Godot-docs slot is retired;
Fetch supplies documentation without spending a second Godot slot.

## Next: guarded Operator Toolkit

Remote control is another belt capability, not an unaudited shell endpoint.
Implement it in permission tiers:

1. **R0 read:** machine status, process/service list, bounded file search/read,
   web/image search, and attach a selected result to Operator Chat.
2. **R1 reversible:** run named diagnostic scripts, restart an allowlisted
   ByrdHouse service, and apply a reviewed patch inside an approved workspace.
3. **R2 privileged:** install/update software or change machine configuration
   only with a short-lived founder approval.

Every action must target a registered machine worker, carry an idempotency key,
timeout and output cap, remain inside declared path roots, redact secrets, and
write an event. Arbitrary PowerShell, batch, filesystem mutation, or public
router exposure stays disabled until per-device identity and the private remote
overlay are proven.

## Luna Pulse (the control loop beside the belt)

Every queued MCP action returns a `watch_job` handoff. `job_status` reports the
current phase, elapsed time, the local learned expectation, terminal state,
error, and resulting artifacts. `job_updates` is cursor-based so an operator
can recover transitions after sleep or reconnect. The dashboard mirrors
running, retry, overdue, completion, and review-ready transitions into Operator
Chat as trusted system updates; those updates are not fed back to the LLM as if
the founder typed them.
