# Agent Safety Policy

Governs every coding agent, MCP client, and automation that touches ByrdHouse
(handoff §9/§12). The belt principle stands: **bot autonomy is a permissions
change on audited endpoints, never a separate build.**

## Permission tiers

| Tier | Name | Allowed behavior | ByrdHouse mechanism |
|---|---|---|---|
| 0 | Observe | Read files, status, logs, repo history. | `BYRD_BELT_MCP_READONLY=1` on `byrd_belt_mcp.py`; `byrd-status.ps1`; `byrdhouse-preflight.ps1` (read-only by design). |
| 1 | Propose | Plans, commands, patch previews — no writes. | Agent output reviewed by founder; nothing applied automatically. |
| 2 | Safe write | Writes only inside an experiment branch or disposable workspace. | Git feature branches (e.g. PR #24); lab dirs; never `main`, never production workflows. |
| 3 | Execute | Allowlisted tests/commands in approved directories. | `python tests/integration_test.py`; belt job submission through audited router endpoints. |
| 4 | Promote / deploy | Requires explicit founder approval + passing checkpoint. | STATE.md gate + DECISIONS.md entry; merge to `main` only after review. |

Default for any new agent is **Tier 0**. Escalation is a founder decision
recorded in `docs/DECISIONS.md`.

## Environment isolation (before any risky install)

| Environment | Purpose |
|---|---|
| Production ComfyUI (`Generators/ComfyUI`) | Stable image/swap workflows only. Protected — no experimental custom nodes. |
| Identity Lab ComfyUI | New face/identity custom nodes and candidate workflows (P1). |
| Video Lab ComfyUI | Wan/FLOAT/reactive nodes and large video deps (P4). |
| Training Lab | Dedicated Python env for image LoRA (sd-scripts today; candidates isolated). |
| Agent Lab | Disposable repo + restricted tools for OpenCode/Codex-style tests (P3). |
| Voice Lab | Dedicated env + consent-controlled reference data (P5). |

Each lab must be disable-able/removable without breaking production
(rollback checkpoint).

## Prohibited actions (hard rules)

- No use, cloning, copying, or studying of the leaked proprietary Claude Code
  mirror.
- No committing credentials, dashboard/admin tokens, API keys, consent
  records, or private reference images (`.env` and `profiles/*/references/`
  are gitignored; `admin_token` stays `CHANGE_ME` in git).
- No bulk-installing researched repositories; one capability at a time,
  manifest row first (`docs/model-license-manifest.md`).
- No patching the production Python/Torch environment for an experiment.
- No large model downloads without a proposed manifest (size, destination,
  license, purpose) approved first — the 2026-07-08 download freeze stands.
- No rewriting stable scripts without compatibility wrappers and rollback.
- No public exposure of LM Studio, ComfyUI, browser debugging, or agent
  endpoints — tailnet only, authenticated.
- No full-auto/YOLO agent mode against `E:\ByrdHouse` or `D:\ByrdHouse`.
- No LM Studio GPU model concurrent with heavy ComfyUI diffusion/video; no
  LoRA training concurrent with production ComfyUI jobs; no two video jobs
  (GPU modes are exclusive on the 8 GB 3070 — `use-image-mode.ps1` ritual).

## Consent and identity data

- Identity profiles are per-person and never merged (friends'/girlfriend's
  data never mixes into Carey's package).
- Real photos anchor facial geometry; generated sets are support material and
  never auto-approve a LoRA.
- Never train on evaluation targets (Gojo/Vegeta/Luffy/Link images).
- Speaker/voice work (P5) requires stored consent, allowed uses, reference
  hashes, and engine/model version history before first generation.
