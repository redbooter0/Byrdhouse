# ByrdCoder ComfyUI MCP Layer — two strictly separated roles

Extends ByrdCoder Local V0 (docs/BYRDCODER_LOCAL.md) so a local coding model
can (A) EXECUTE approved image recipes through the belt and (B) STUDY and
edit workflow graphs in an isolated lab. The roles never mix: the executor
cannot touch graphs, the architect cannot touch production.

Neither role replaces anything: the ByrdHouse **router stays the queue**, the
**artifact system stays the archive**, the **memory system stays on MINI**,
and the blueprint hard line stands — no agent drives production ComfyUI
directly.

## Role A — Approved Recipe Executor (`byrd-comfy`)

**Evaluated basis:** `joenorton/comfyui-mcp-server` (Apache-2.0, Python,
streamable-HTTP :9000). Its tool surface was reviewed and re-implemented as a
narrow, belt-native executor: `scripts/byrd_comfy_mcp.py` (stdlib-only,
stdio transport). Re-implementation over vendoring because ByrdHouse already
owns the queue/artifact/sidecar machinery the upstream re-invents (its
session asset registry, HTTP port, and output-root mutation are exactly the
parts we must not have).

| Upstream feature | Fate here |
|---|---|
| `PARAM_*` constrained overrides | **Kept** — per-recipe typed/bounded param map in the manifest; unmapped names rejected. |
| Workflow discovery | **Kept, curated** — `list_recipes` shows ONLY `configs/byrdcoder/approved_workflows.json`; the repo `workflows/` dir is never auto-exposed. |
| Job polling / cancellation / regeneration | **Kept** — `job_status` / `cancel_job` / `regenerate`, all against router endpoints. |
| Asset metadata | **Kept** — `asset_meta` reads the permanent ByrdHouse artifact registry. |
| ComfyUI error extraction | **Kept** — `last_error` / `job_status` surface the worker-recorded failure text. |
| Session asset registry (24 h TTL) | **Replaced** — jobs are belt jobs; artifacts register immediately in the ByrdHouse artifact + sidecar system. |
| `publish_asset` | **Absent** (structurally removed). |
| `set_comfyui_output_root` (persistent!) | **Absent.** |
| persistent `set_defaults` | **Absent.** |
| `run_workflow` (arbitrary graph execution) | **Absent** — approved recipes only. |
| HTTP :9000 transport | **Replaced by stdio** — nothing binds, nothing to expose; router auth via the config admin token. |

**Requirement compliance:**

1. *Dedicated Python 3.11 env* — the server is stdlib-only; create the venv on
   GAMING: `py -3.11 -m venv E:\ByrdHouse\LLM\byrdcoder\py311` and point the
   machine config's mcp command at
   `E:/ByrdHouse/LLM/byrdcoder/py311/Scripts/python.exe`.
2. *Loopback/policy-plane only* — stdio transport (no socket at all); the only
   network egress is authenticated calls to the router (the policy plane).
3. *Curated directory only* — the `approved_workflows.json` manifest.
4. *No auto-exposure of `workflows/`* — enforced + contract-tested.
5. *Dangerous tools disabled/removed* — absent from the roster; the
   `REMOVED_TOOLS` list in the module is contract-tested to stay out.
6. *Immediate ByrdHouse registration* — every run is a router job; the worker
   cards artifacts as always.
7. *Execution record* — `logs/byrdcoder/comfy_exec/<job>.json`: ByrdHouse job
   ID, recipe id+version, workflow sha256, parameter overrides,
   checkpoint, seed (belt-assigned at submit per the hard rule; recorded
   from the sidecar on completion), source/reference hashes, output path,
   runtime, result status.
8. *Useful features preserved* — table above.
9. *Behind existing tiers* — `BYRD_COMFY_MCP_READONLY=1` is the default in
   the machine config (Tier 0/1: list/describe/status only). Flipping it to
   `0` for a byrd-build/byrd-test session is the founder's Tier 2/3
   permission change. Router-side, every call is token-authenticated and
   audited in the events table like any dashboard action.
10. *Automated tests* — path traversal (absolute, `..`, escape-from-
    `workflows/`) and unmapped/out-of-bounds overrides are rejected;
    proven in `tests/integration_test.py` (byrdcoder comfy section).

## Role B — Isolated Workflow Architect (`comfyui-lab`)

**Evaluated:** `artokun/comfyui-mcp` (MIT; "local-first agent-native control
plane": 108 tools incl. graph editing, node install, model download,
CivitAI/HF, process control, Cloudflare tunnels). Powerful and therefore
gated hard.

**Pin (do not use latest):** `comfyui-mcp@0.34.0` = git tag `v0.34.0` =
commit `6a7ceeb9b578a149b0da65b43e0def708f0b3078` (v0.35.0 exists upstream;
upgrade only by founder decision after re-review).

**Environment** (`configs/byrdcoder/comfyui-mcp-lab.env.example`):
`COMFYUI_MCP_PANEL_AUTOINSTALL=0`, `COMFYUI_MCP_AUTOUPDATE=0`,
`COMFYUI_MCP_TOOL_MODE=compact` (3 meta-tools instead of 108),
`COMFYUI_URL` = the **isolated Workflow Lab** ComfyUI (separate install,
loopback port, e.g. `:8189`) — never production `:8188`. No CivitAI/HF/Cloud
tokens exist in the environment; `--tunnel` is forbidden.

**Initial permissions — read-only:** inspect workflow, summarize graph, list
node types, inspect node definitions, view status, diagnose workflow errors.
**Explicitly denied initially:** custom-node install, model download,
ComfyUI restart/stop, tunnels/public HTTP, CivitAI operations, deleting
nodes/workflows, changing production files, publishing, automatic promotion.
(Denial mechanism: tokens absent + autoinstall/autoupdate off + lab-only URL
+ the OpenCode server entry ships `"enabled": false` until the lab exists +
graph edits restricted to `workflows/experiments/comfyui-mcp-lab/` copies.)

After the read-only verification pass is recorded here, graph editing is
allowed **only against copies** under `workflows/experiments/comfyui-mcp-lab/`
(gitignored scratch, rules in its README). Candidates move to
`workflows/candidates/` only through the 7-gate checklist in that folder's
README (JSON validation → required-node validation → dry-run → visual review
→ dependency/license manifest → rollback doc → founder approval).

## Setup on BYRD-GAMING

```powershell
cd $env:BYRDHOUSE_ROOT
git pull origin main
py -3.11 -m venv LLM\byrdcoder\py311          # Role A dedicated env
powershell -ExecutionPolicy Bypass -File scripts\start-byrdcoder.ps1 -Regen   # regenerate machine config (wires byrd-comfy MCP)
powershell -ExecutionPolicy Bypass -File scripts\test-byrdcoder.ps1
```

Then edit `LLM\byrdcoder\opencode.json`: set the byrd-comfy mcp command to
the py311 venv python. Role B stays `"enabled": false` until the Workflow
Lab ComfyUI instance exists; enable it then and fill `COMFYUI_URL`.

## Acceptance checkpoint (record results + log paths here)

1. Local LM Studio model via OpenCode lists approved recipes (`list_recipes`). — *(pending)*
2. It submits one harmless approved workflow (`fast_preview`) through the executor (founder flips `BYRD_COMFY_MCP_READONLY=0` for the session). — *(pending)*
3. Job recorded by ByrdHouse; result archived with full metadata (belt sidecar + `logs/byrdcoder/comfy_exec/<job>.json`). — *(pending)*
4. Agent inspects a copied workflow through artokun compact mode in the lab. — *(pending)*
5. It proposes one graph correction inside the lab folder. — *(pending)*
6. It cannot install nodes, download models, publish assets, or touch production (attempts fail; no tokens, no tools, lab URL only). — *(pending)*
7. Router/queue/archive/memory unchanged — both servers are clients of the belt, not replacements. — *(structural; verified by design + tests)*
8. Everything ran without Codex or another paid coding model. — *(pending)*

## Risks

- **Manifest drift** — an approved entry pointing at a changed workflow file
  changes behavior silently; the recorded workflow sha256 in every execution
  card + `list_recipes` makes this visible and auditable.
- **artokun surface is huge** — compact mode + absent tokens + lab-only URL +
  disabled-by-default bound it, but treat every lab session as an experiment;
  never run it against production, even read-only, until a founder decision
  says otherwise.
- **npx supply chain** — the pinned `comfyui-mcp@0.34.0` is fetched by npx;
  the version is pinned but the first fetch should happen while online on
  GAMING and be reviewed (`npx -y comfyui-mcp@0.34.0 --help`), then npx cache
  serves it. Autoupdate is off.
- **Token leakage into the lab env** — the env example forbids CivitAI/HF/
  Cloud keys; the contract test asserts the example contains none.

## Rollback

Role A: remove the `byrd-comfy` mcp block from the machine config (or
`-Regen` after reverting the repo commit); delete `logs/byrdcoder/comfy_exec/`.
Role B: set `"enabled": false` (or delete the block), delete the lab env
file and the npx cache entry. Repo side: `git revert` of the delivery
commit. Nothing in the belt, router, archive, or memory changes either way.

## Current phase → next action → checkpoint

- **Phase:** repo-side complete (executor + manifest + lab kit + gates +
  tests); nothing verified on hardware yet.
- **Next action:** GAMING setup block above, then run the acceptance
  checkpoint top to bottom during a byrd-build session.
- **Checkpoint:** all 8 items above recorded here with log paths; Role B
  graph editing stays locked until the read-only verification pass is
  recorded.
