# ByrdCoder Local V0 — the local coding agent

A permanent local coding agent that keeps working when Codex or cloud-model
usage is exhausted. It is **OpenCode** (open-source coding TUI/CLI) talking to
**LM Studio** on BYRD-GAMING through the pinned **opencode-lmstudio** bridge
plugin — no cloud provider is configured, no paid model is required, and it
obeys the ByrdHouse agent safety policy (docs/agent-safety-policy.md).

Nothing here replaces LM Studio, the router, or the memory system. ByrdCoder
is a client of LM Studio the same way Cherry Studio is; the belt is untouched.

## The pieces

| Piece | What it is |
|---|---|
| `configs/byrdcoder/opencode.example.json` | The isolated OpenCode config (template). LM Studio URL is a `{{LMSTUDIO_URL}}` placeholder — zero hardcoded hosts in git. |
| `configs/byrdcoder/prompts/*.md` | System prompts for the seven byrd-* profiles. |
| `configs/byrdcoder/allowlist.json` | Single source of truth: allowed/denied commands, allowed/forbidden directories, protected branches. |
| `scripts/start-byrdcoder.ps1` | The one launch command. Generates the machine config into `LLM\byrdcoder\` (gitignored), enforces the byrd-build branch guard, launches OpenCode with `OPENCODE_CONFIG` pointing at the isolated file — your global OpenCode config is never touched. |
| `scripts/byrdcoder-preflight.ps1` | Phase 1 verification: LM Studio reachable, models discovered, embeddings excluded, context/capabilities reported, coder models present. |
| `scripts/byrdcoder_models.py` | Stdlib discovery helper (same endpoints the plugin uses). |
| `scripts/test-byrdcoder.ps1` | Config / permission / allowlist behavior tests (live parts skip when services are down). |
| `scripts/byrdcoder-benchmark.ps1` | Phase 5: the 7-task protocol per model in a disposable clone. |
| `scripts/byrdcoder_review.py` | Phase 6: two-agent loop reviewer (approve / request_changes / block, fail-closed). |

**Pinned bridge:** `opencode-lmstudio@0.3.1` (MIT, stable 2026-06-21 — pinned
over the 1.0.0-rc prerelease deliberately). It discovers models from LM
Studio's native API at OpenCode start, adds only `llm` records (embedding
models excluded), reports loaded/max context, and maps tool/vision capability
flags. Upgrades are a founder decision recorded in DECISIONS.md.

## Install (BYRD-GAMING, once)

```powershell
cd $env:BYRDHOUSE_ROOT
git pull origin main
# OpenCode CLI (record the installed version in this doc after install):
npm install -g opencode-ai
# verify Phase 1:
powershell -ExecutionPolicy Bypass -File scripts\byrdcoder-preflight.ps1
powershell -ExecutionPolicy Bypass -File scripts\test-byrdcoder.ps1
```

The plugin itself installs automatically from the `plugin` pin in the config
on first OpenCode start. **Installed OpenCode version:** *(fill after
install)*. Do not download new LM Studio models until the currently installed
ones are benchmarked (Phase 5).

## Daily use

```powershell
start-byrdcoder.ps1                    # byrd-ask: read-only Q&A (the default)
start-byrdcoder.ps1 byrd-patch         # patch previews, never applied
start-byrdcoder.ps1 byrd-build        # writes — refuses to start on main
start-byrdcoder.ps1 byrd-test          # allowlisted test execution only
start-byrdcoder.ps1 byrd-offline       # no remote providers, no web
start-byrdcoder.ps1 byrd-private       # local-only, no external transmission
```

**Every new session defaults to read-only**: the launcher defaults to
byrd-ask AND the config's global permissions are deny-by-default, so even the
built-in OpenCode agents are inert under this config.

## Profiles ↔ permission tiers

| Profile | Tier | Can do |
|---|---|---|
| byrd-ask | 0 observe | Read + explain. Nothing else. |
| byrd-patch | 1 propose | Unified-diff previews; read-only git inspection. |
| byrd-build | 2 safe write | Edit + commit on an approved feature branch (`byrdcoder/`, `feature/`, `agent/`, `claude/`). Launcher + config both refuse main. No push, no merge — ever. |
| byrd-test | 3 execute | Only the allowlisted test commands. |
| byrd-review | 0/1 | Judges another model's patch; read-only. |
| byrd-offline / byrd-private | 0 | byrd-ask hardened for offline / private material. |
| — | 4 promote | **Founder only.** Push, PR, merge. Never automated. |

## Two-agent coding loop (Phase 6)

Model A codes (byrd-patch/byrd-build), Model B reviews:

```powershell
python scripts\byrdcoder_review.py --task task.md --diff my.patch --tests test_output.txt --context scripts\byrdcast_swap.py --model <reviewer-model-id>
```

The reviewer receives the original task, the diff, test output, and file
context, and must return `approve` / `request_changes` / `block` (exit
0/1/2), with a review card written to `logs\byrdcoder\reviews\`. Unparseable
or unreachable reviewer = **block** (fail closed). A blocked patch is never
promoted automatically; promotion is always the founder's Tier 4 action. The
benchmark runner wires this automatically via `-Reviewer <model>`.

## Acceptance checkpoint (run on BYRD-GAMING)

V0 passes only when all ten hold — record results + log paths here:

1. LM Studio starts and exposes the expected local models — `byrdcoder-preflight.ps1` green.
2. OpenCode discovers those models (bridge plugin loads, embeddings excluded).
3. A local model reads the repo — `start-byrdcoder.ps1` (byrd-ask), ask it to explain `scripts/worker.py`.
4. It creates a valid feature branch — founder runs `git checkout -b byrdcoder/first-change`, then `start-byrdcoder.ps1 byrd-build`.
5. It proposes and applies one harmless change (e.g. a typo fix in a doc) and commits.
6. `start-byrdcoder.ps1 byrd-test` → `python tests/integration_test.py` passes.
7. A second local model reviews the patch via `byrdcoder_review.py` → approve.
8. Nothing touched `main`, secrets, or production ComfyUI — `git log main` unchanged, `test-byrdcoder.ps1` green.
9. The whole flow ran without Codex/Claude/any paid model (LM Studio only — check `logs\byrdcoder\sessions.log`).
10. Rollback recorded: `git branch -D byrdcoder/first-change` (and `git revert <hash>` for anything merged later).

**Checkpoint status:** *(pending — not yet run on hardware)*

## Rollback (whole feature)

Everything is additive: revert the ByrdCoder commit(s), delete
`LLM\byrdcoder\` on the machine, `npm uninstall -g opencode-ai`. No belt,
router, memory, or ComfyUI state is involved.

## Later (explicitly out of V0)

The Codex proxy is NOT installed in V0. It may be evaluated later as an
optional compatibility adapter, in an isolated lab, only after this
independent OpenCode lane passes its checkpoint (DECISIONS 2026-07-16).
