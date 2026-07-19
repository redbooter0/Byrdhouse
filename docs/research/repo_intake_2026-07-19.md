# Repository Intake — 2026-07-19

*Source: `ByrdHouse_Fable_Handoff_Image_Lane_Repo_Intake_20260719.docx`*

This note captures the nine-repository intake handoff so its decisions are
durable in the repo. **It is not a work order for this session.** All
implementation is queued behind the U1 IMAGE LAB hardware-validation gate
tracked on PR #25.

Two things constrain what any future session may do from this note:

1. The Image Lane Master Brief (also 2026-07-19) requires BYRD-GAMING
   hardware evidence (easy → Gojo → Vegeta on the merged
   `claude/local-face-swap-lora-68v0sq`) before *any* new integration
   work lands. This handoff's §11 execution directive says the same
   thing in its step 1: "Establish and archive the current baseline on
   locked Luffy, Vegeta, Gojo, realistic, and gaming targets."
2. §1.2 hard-forbids "another document-only plan" — this note exists
   only so the intake matrix and per-repo instructions survive in the
   repo, not so a future session can defer WO-0 by re-reading it.

## Repository intake decision matrix

| Repo | Role | Current action | Priority |
|---|---|---|---|
| comfyUI-Realtime-Lora | LoRA train/analyze/select blocks/schedule | **INTEGRATE FIRST — analysis-first only** | P0 |
| Mask2Former | Universal segmentation reference | Adapter reference / sandbox (archived Jan 2025) | P2 |
| Presidio | PII detection, image redaction | Later privacy/export gate (NOT a face-mask engine) | P3 |
| Barbershop | GAN hair compositing research | Reference only, extract concepts not deps | P4 |
| FireRed Image Edit Fast | High-fidelity multi-reference edit | Future high-VRAM lane (~30 GB, NOT the 3070) | P4 now / P1 future |
| mcp-image | MCP prompt optimization + image actions | Copy architecture, replace cloud provider | P1 study |
| LocalAI | Unified OpenAI-compatible engine | Do NOT replace LM Studio / ComfyUI | P3 |
| LocalAGI | Local agent teams + MCP | Sidecar study, not a belt replacement | P2 |
| Locally Uncensored | Offline desktop AI studio (AGPL) | Product-shell study only, license decision required before code reuse | P2 |

Sources: repo-intake handoff §3 and §4. Confirm each upstream README before
install — repositories change.

## Hard prohibitions (§1.2, restated)

- No LM Studio, router, worker, Qdrant, SQLite, or dashboard replacement.
- No FireRed install on the RTX 3070 production lane.
- No Mask2Former direct dependency (adapter interface only; upstream is archived).
- No auto-training on rejected / unscored / weak outputs.
- No document-only reply — inspect, implement, test, record, commit.
- No endless command loop — after two materially identical failures, stop and diagnose.

## Work orders — locations in this repo

Path mapping so a future BYRD-GAMING session can execute without re-deriving
the layout. Names follow the intake §8 recommendation; final names should
adapt to existing conventions after inspection, per §8 note.

| WO | Purpose | Target path(s) |
|---|---|---|
| WO-0 | Baseline archive + branch + evidence lock | `docs/IMAGE_GENERATION_STATE.md` (append run block), locked baseline artifacts under existing artifact belt |
| WO-1 | Install `comfyUI-Realtime-Lora` analyzer/selective-loader nodes (no training backend) | `configs/image/realtime_lora.json`, `scripts/realtime_lora_preflight.py`, `docs/research/realtime_lora_intake.md` |
| WO-2 | Identity LoRA block-analysis harness | `scripts/analyze_identity_lora.py` + JSON/MD reports under `Images/Reports/lora_analysis/` (or repo-idiomatic `artifacts/` subtree) |
| WO-3 | Locked acceptance benchmark | `configs/image/benchmark_locked.json`, `Images/Benchmarks/identity_locked/`, wire through `scripts/identity-benchmark.ps1` (already present) |
| WO-4 | Selective LoRA evaluation → promote one preset as `identity_selective_sdxl@1` | `recipes/identity_selective_sdxl@1.json`, `scripts/benchmark_selective_lora.py`; **prior recipe stays selectable for rollback** |
| WO-5 | Approved-output dataset curator + one conservative micro-LoRA trial | `scripts/curate_identity_dataset.py`, `scripts/train_identity_candidate.ps1`; approval reasons wired into dashboard/API |
| WO-6 | Provider-neutral `segment_image` router + face-zone mask package | `scripts/segment_image.py`, `scripts/compose_face_zone_mask.py`, `workflows/segmentation/face_zone_diagnostics.json` — wraps the working backend first |
| WO-7 | Local ByrdImage MCP (read-only actions first) | routes to existing `router/router.py`, does NOT call ComfyUI directly |
| WO-8 | App-shell + agent-room study — research note only | `docs/research/agent_shell_review.md` |

## The `segment_image` contract (§4.2)

Provider-neutral, backend-swappable interface. Wrap the currently working
face detector as backend 1; add hair/skin/body/background backends only
after each has its own preflight.

```python
segment_image(
    image_path,
    requested_regions=["face", "hair", "skin", "clothing"],
    backend="auto",
    output_dir=...,
) -> {
    "masks": {...},
    "boxes": {...},
    "confidence": {...},
    "coverage": {...},
    "backend": "...",
    "model_version": "...",
    "runtime_ms": 0,
}
```

Isolation rule: an experimental segmenter must not be able to break ComfyUI.

## Acceptance rubric — dimensions and promotion gates (§7)

Six dimensions, each scored 0 / 3 / 5: identity likeness, face
completeness, theme preservation, structure preservation, seam quality,
anatomy/artifacts.

Promotion rules:

- No critical target may score below 3 on identity, completeness, or theme.
- Aggregate must beat production baseline by a documented margin.
- Runtime + VRAM must stay in the 3070 envelope without repeated OOM recovery.
- Human review must approve representative outputs — not just the top score.
- Previous recipe/model stays selectable for rollback.

## Status-report format for every WO (§9.1)

```
CURRENT PHASE:
WORK COMPLETED:
FILES CHANGED:
TESTS RUN:
EVIDENCE / ARTIFACTS:
REGRESSIONS CHECKED:
KNOWN LIMITS:
ROLLBACK:
NEXT SINGLE ACTION:
```

## What this note explicitly does NOT do

- Does not clone any of the nine repositories.
- Does not add any dependency, custom node, or script.
- Does not modify `PR #25` (the U1 image-lane merge-candidate).
- Does not change any recipe, workflow, config, or belt behavior.
- Does not authorize starting WO-0 in this cloud session — WO-0 needs BYRD-GAMING.

## Order of operations across the two 2026-07-19 handoffs

The Image Lane Master Brief and this Repository Intake Handoff must be
executed in one sequence, not in parallel:

1. **Master Brief Phases 3–9 (hardware ladder) on BYRD-GAMING against
   `claude/local-face-swap-lora-68v0sq`.** Records results in
   `docs/IMAGE_GENERATION_STATE.md`. This IS the intake handoff's WO-0.
2. Only after (1) closes U1 or explicitly bounds it, this intake's WO-1
   begins (comfyUI-Realtime-Lora analyzer install, still analysis-only,
   no training backend).
3. WO-2 through WO-8 follow the intake handoff's §6 sequence, each with
   the §9.1 status report and §7 promotion gates.
