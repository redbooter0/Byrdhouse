# Fable Implementation Report — Handoff of 2026-07-15

Response of record to the **ByrdHouse Implementation Handoff** (uploaded
2026-07-15). Per the handoff's own rule — *"If the live state differs from this
document, report the difference and use the live verified state"* — this report
maps every handoff requirement onto the live repository and records what was
implemented, what already existed, what is deferred, and why.

Work was done in a remote repo session (no access to the physical machines), so
this covers the **repo side of Phase P0**. Everything that requires BYRD-GAMING
or BYRD-MINI hardware is packaged as runnable scripts + exact commands below.

## 1. Verified live repository state

- Repo root: `Byrdhouse` (GitHub `redbooter0/Byrdhouse`), branch
  `claude/local-face-swap-lora-68v0sq` (open PR #24), CI green
  (secret-scan, belt-integration, powershell-parse, dashboard-tests).
- Service/host registry **already exists**: `byrdhouse.config.json` at repo
  root — `hosts` (byrd-gaming / byrd-mini / byrd-vault MagicDNS names) +
  `services` (comfyui 8188, lmstudio 1234, qdrant 6333, router 8787).
  Zero-hardcoded-IPs is an enforced hard rule in CLAUDE.md.
- The belt (router/worker/dashboard/SQLite WAL queue/sidecar cards) is live and
  proven end-to-end on real hardware (U0 closeout in `docs/STATE.md`).
- **Stable Swap V0** = `scripts/byrdcast_swap.py` + `configs/byrdcast_swap_v0.json`
  + `workflows/byrdcast_swap_v0.json` + `docs/BYRDCAST_SWAP_V0.md`, protected by
  CI contract checks and a zero-GPU dry-run acceptance test in
  `tests/integration_test.py`.
- Face lanes already live: ReActor direct/blend (private lane), Impact Pack
  AUTO route, CPU examiner (`byrdfacezone.py`), mesh-seed quality lane,
  DifferentialDiffusion and IP-Adapter avenues, `facelab.ps1` operator entry.
- LoRA lane already live: `collect-training-images.ps1`,
  `prepare-carey-lora-dataset.py`, `train-lora.ps1` /
  `train-carey-meina-lora.ps1` (kohya sd-scripts wrapper; versioned
  never-overwrite outputs; 7200 MB VRAM / 16-thread limits). Eight tracked
  training runs with honest reject verdicts in `docs/IMAGE_GENERATION_STATE.md`.
- MCP/agent layer exists: `scripts/byrd_belt_mcp.py` with a
  `BYRD_BELT_MCP_READONLY` permission flag (autonomy = permission change,
  never a separate build).

## 2. Differences from the handoff (live state wins)

| Handoff assumption | Live truth |
|---|---|
| `config\byrdhouse.config.json` + `services.local.json` | Config lives at repo root `byrdhouse.config.json` (template with CHANGE_ME placeholders; real values only on machines). No second registry created — one registry, the router reads it. |
| `workflows\production` + `candidates` + `experiments` tree | Flat `workflows/` with versioned API-format graphs and CI contract checks as production protection. Kept — the handoff itself says "do not force this tree". Candidate status = filename/version + STATE gate, not directory. |
| Dataset root `data\identities\carey_face` | Live conventions: `profiles/<id>/references/` (gitignored personal photos), `profiles/<id>/lora_dataset/`, and `Identities/<id>/approved/` for ByrdCast Swap references. No third convention introduced. |
| Branch `fable/byrdhouse-catchup-2026-07-15` | This session is bound to `claude/local-face-swap-lora-68v0sq` (PR #24). Same isolation intent — experiment branch, no merge to main without review. |
| `scripts\preflight\`, `scripts\benchmarks\`, `scripts\training\` subtrees | `scripts/` is flat by convention. Delivered as `scripts/byrdhouse-preflight.ps1` and `scripts/identity-benchmark.ps1`; training wrappers already exist flat. |
| Router/dashboard "historically port 8787" needs verification | Confirmed as the live config value; dashboard is served by the router on byrd-mini. |
| `train-carey-lora.ps1` to be created around duck3244/lora-sd-custom | `train-carey-meina-lora.ps1` already exists and is reliable on the machine (sd-scripts). duck3244 is a **candidate** to evaluate in an isolated env, not a replacement — the incumbent has eight benchmarked runs of history. |
| BYRD-MINI "8GB RAM reported" and the `15.2.2.5` endpoint conflict | Unresolved from the repo — the preflight script resolves both hostnames' IPv4 and records RAM; run it on both machines (§9 commands). |

## 3. What was changed (this delivery)

| File | Purpose |
|---|---|
| `docs/fable-implementation-report.md` | This report (handoff deliverable). |
| `docs/current-machine-inventory.md` | Inventory of CONFIRMED repo facts + VERIFY placeholders filled by preflight runs. |
| `docs/model-license-manifest.md` | Structured per-model manifest (license, commercial eligibility, location, rollback) per handoff §12.2. |
| `docs/agent-safety-policy.md` | Permission tiers 0–4, environment isolation, prohibited actions (handoff §9.2/§12). |
| `docs/identity-stack-review.md` | Research-registry dispositions (§10) reconciled to live licensing lanes. |
| `docs/identity-benchmark.md` | Five-target benchmark spec + empty scorecard, filled by real runs. |
| `scripts/byrdhouse-preflight.ps1` | Read-only machine/service preflight (§15), config-driven, timestamped JSON output. |
| `scripts/identity-benchmark.ps1` | Repeatable five-target benchmark runner over the available branches. |
| `docs/STATE.md`, `docs/DECISIONS.md` | Phase status + append-only decisions. |

## 4. What was deliberately NOT changed

- **No repository installs.** RMBG, facetools, Forbidden Vision, FaceShaper,
  Fayens, Wan 2.2, IndexTTS, OpenCode bridges — all are P1+ lab work on
  BYRD-GAMING, sequential, one at a time, per the handoff's own rule.
- **No `workflows/candidates/byrd_identity_swap_v1.json` and no matching
  recipe.** The handoff requires the candidate workflow "only after valid
  export" from a real ComfyUI with the nodes installed. Fabricating that JSON
  here would violate the gate; it ships when P1 produces a real export.
- **No restructure** of config/scripts/workflows/recipes trees (handoff:
  "map the current repository before restructuring").
- **No model downloads, no trainer swap, no production workflow edits.**
  Stable Swap V0 files untouched this delivery.
- **InfiniteYou, DeepFuze, InstaSwap, LM Studio unlocked backend,
  LmStudioToCursor, the leaked Claude Code mirror**: rejected/blocked per
  §10; the leaked mirror is a hard reject — never cloned, copied, or studied.

## 5. Tests

- `python tests/integration_test.py` — full belt suite (router + worker
  against mock ComfyUI/LM Studio + ByrdCast Swap V0 contract and dry-run
  checks) run after these changes; result recorded in the PR/CI.
- Both new `.ps1` files carry the UTF-8 BOM and parse clean (CI
  `powershell-parse` enforces both on every push).

## 6. Risks and licensing

- ReActor / inswapper / InsightFace / IP-Adapter FaceID: research,
  non-commercial — **private lane only**; monetized output goes through the
  identity-LoRA + license-clear generation route. Enforced as policy today;
  a programmatic route gate is a staged improvement (DECISIONS 2026-07-15).
- ParseNet anime fallback + Meina V5.1 provenance: private-local-evaluation
  only pending license review (tracked in `docs/IMAGE_GENERATION_STATE.md`
  and the new manifest).
- Every future lab install must land in `docs/model-license-manifest.md`
  with commit SHA, license, sizes, hashes, and rollback before first use.

## 7. Rollback

Everything in this delivery is additive docs + two read-only/benchmark
scripts: `git revert` of the delivery commit restores the prior state.
No machine state was modified.

## 8. Current phase → next action → checkpoint

- **Phase:** P0 (baseline) — repo side complete; machine side pending.
- **Next action:** run the preflight on both machines and paste results into
  `docs/current-machine-inventory.md` (commands below). Then P1: install
  ComfyUI-RMBG (light models only) in an isolated lab and run the five-target
  benchmark baseline with `scripts/identity-benchmark.ps1`.
- **Checkpoint (baseline reboot):** after a cold boot, one command reports
  roots, config, hosts, and all core services without hiding failures — the
  preflight script is that command.

## 9. Exact commands for the founder

Run on **each** machine (BYRD-GAMING, then BYRD-MINI), PowerShell:

```powershell
cd $env:BYRDHOUSE_ROOT
git pull origin claude/local-face-swap-lora-68v0sq
powershell -ExecutionPolicy Bypass -File scripts\byrdhouse-preflight.ps1
```

Read-only; writes `logs\preflight\<timestamp>\preflight.json` + a console
report. Then on BYRD-GAMING only, once five benchmark targets are in a folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\identity-benchmark.ps1 -TargetsDir "E:\ByrdHouse\inbox\benchmark_targets" -Identity Carey
```
