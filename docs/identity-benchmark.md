# Identity Benchmark — five-target scorecard

Repeatable benchmark for the identity swap lanes (handoff §6.3–6.5). Run it
with `scripts/identity-benchmark.ps1` on BYRD-GAMING; it fills a results
folder under `logs\benchmarks\` with per-run sidecars and a scorecard table
to paste back here. **Do not declare a winner from a single run** — repeat
runs (including cold starts) before promotion.

## The five targets

Put five images in one folder (e.g. `E:\ByrdHouse\inbox\benchmark_targets`),
named so the case is obvious:

| Case | Target | What it tests |
|---|---|---|
| 1 | `01_front*.png` — front-facing portrait | Baseline identity fidelity. |
| 2 | `02_angle45*.png` — 45° face angle | Alignment and geometry. |
| 3 | `03_profile*.png` — near profile | Hard-angle reconstruction. |
| 4 | `04_occlusion*.png` — glasses / partial occlusion | Occlusion-aware masking. |
| 5 | `05_smallface*.png` — small face in full-body shot | Detection, crop resolution, paste-back. |

Never use LoRA evaluation targets (Gojo/Vegeta/Luffy/Link) as training data;
using them as swap *targets* here is fine and expected.

## Branches

| Branch | Pipeline | Status |
|---|---|---|
| A | ReActor only (belt `image.faceswap` direct route) | Available (private lane) |
| S | ByrdCast Swap V0 (`scripts/byrdcast_swap.py`) | Available — what the runner drives today |
| B | facetools → ReActor → warp-back | Gated: install comfyui_facetools in the Identity Lab first |
| C | facetools → FaceShaper → ReActor → warp-back | Gated: FaceShaper after baseline works |
| D | facetools → ReActor → Forbidden Vision → warp-back | Gated: expected practical winner — benchmark decides |

## Scorecard fields (per case × branch)

Identity similarity · jaw/face-shape fidelity · eye integrity · mouth/teeth
integrity · skin detail · lighting/color match · seam visibility · background
preservation · runtime (s) · peak dedicated VRAM + shared memory · system RAM ·
license lane (funded/private). Automated fields come from the run sidecars
(score.json); visual fields are founder-scored 0–5 from the outputs.

## Results

*(no runs recorded yet — paste each benchmark's summary table below, newest
first, with date, branch, quality mode, and the runner's output folder path)*
