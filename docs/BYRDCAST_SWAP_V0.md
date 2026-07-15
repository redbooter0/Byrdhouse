# ByrdCast Swap V0 — target-image-first local face swap

*Give ByrdCast any target image; it replaces the MAIN face with an identity from
a local approved-reference folder while preserving the target's pose, lighting,
style, scene, clothing and composition. 100% local on the RTX 3070 8GB /
i9-10850K / 32GB box. Image only — no video, no multi-person, no prompt
generation in V0.*

This is a **self-contained tool** (`scripts/byrdcast_swap.py`), separate from the
belt's face-zone lanes: single command in, one debug-rich job folder out. It
shows its work — what it detected, which reference it chose and why, which route
it used, and why the result passed or failed — and it **fails closed** (a weak
result is saved and marked `accepted=false`, never silently shipped).

## Command

```powershell
python scripts\byrdcast_swap.py --identity Carey `
  --target "E:\ByrdHouse\Inputs\target.png" `
  --refs "E:\ByrdHouse\Identities\Carey\approved" `
  --out "E:\ByrdHouse\Outputs\ByrdCastSwap" --quality best
```

- `--identity`  identity name (also the `Identities\<name>` folder).
- `--target`    the picture to swap onto.
- `--refs`      approved reference folder (defaults to
  `<identities_root>\<identity>\approved` from the config).
- `--out`       outputs root (defaults from config).
- `--quality`   `fast` | `balanced` | `best`.
- `--dry-run`   run the CPU stages + write the full folder WITHOUT a GPU/ONNX
  swap (structure proof; always `accepted=false`). Use it to verify the plumbing
  and see the detection/masks before spending the GPU.

## The 14 stages

1. Validate the target image exists.
2. Validate the identity reference folder exists.
3. Load all approved references from `E:\ByrdHouse\Identities\<identity>\approved\`.
4. Detect the face in the target (best available detector — see below).
5. Detect faces in every reference.
6. **Choose the best reference** on face angle, expression, lighting similarity
   and image quality. Weights are in the config; a factor that can't be measured
   (e.g. angle without landmarks) is recorded and the weights **renormalize over
   what was measured** — never a silent guess.
7. Write the target face-detection debug overlay.
8. Build masks: **face, jaw, hairline, ears, neck, skin** (geometric off the
   detected box, feathered) + a colored `mask_overlay.png` and per-zone PNGs.
9. Run the swap route: **ReActor** (ComfyUI) → **InsightFace** (in-process) →
   fail closed if neither is available.
10. Masked restore/refinement: **FaceDetailer** (Impact Pack) if present —
    face-only, never touches hair/clothes/background — else skipped.
11. Optional low-denoise inpaint blend around the face/hair/neck seam
    (`quality=best`).
12. Score the candidate: **identity similarity** (face-embedding cosine when
    both sides were embedded), **mask fit**, **landmark alignment**, **blend
    quality**, **artifact risk**.
13. Save: `target.png`, `selected_reference.png`, `face_detect_overlay.png`,
    `mask_overlay.png`, `candidate_reactor.png`, `candidate_refined.png`,
    `final.png`, `score.json`, `sidecar.json` (+ a `masks/` folder).
14. **Fail closed**: below threshold → the output is still saved, `accepted=false`,
    and the reason (weakest factors) is written to the sidecar.

## Detector chain (honest degradation, always recorded)

| Priority | Detector | Gives | When |
|---|---|---|---|
| 1 | **insightface** `buffalo_l` | box + 5 landmarks + pose + 512-d embedding | installed (comes with ReActor) — enables real identity scoring |
| 2 | **OpenCV Haar** | box only | cv2 present, insightface not |
| 3 | **PIL placeholder** | center box, flagged | nothing else — **forces `accepted=false`** |

The method used rides on `sidecar.json.target_face.method`, so you always know
whether the geometry was measured or guessed.

## Hardware rules (enforced / recorded)

- batch size 1; no video; modest resolution first (768 preview / 896 refine).
- Unload LM Studio before the heavy ComfyUI pass (config
  `hardware.unload_lmstudio_before_swap`; the run prints the reminder).
- Never assume more than 8GB VRAM (`vram_budget_mb: 7200`).
- Every debug file is preserved for every run (`keep_debug_files`).

## One-time installs

Run `facelab.ps1 preflight` (it checks ReActor, inswapper, GFPGAN, Impact Pack,
the detector) — see `docs/MODELS.md` / `docs/FACE_OPS.md §0`. The swap route needs
**ComfyUI-ReActor + `inswapper_128.onnx`** (or the `insightface` package for the
in-process route); the refine needs **Impact Pack + a photoreal checkpoint**.

## License note (important)

ReActor / inswapper / insightface are **research / non-commercial**. ByrdCast V0
is the personal-experiment lane. For monetized output, the funded lane stays the
identity-LoRA + IP-Adapter FaceID route (`docs/FACE_LAB.md`) — same rule as the
rest of the Face Lab.

## Acceptance test

```
python scripts\byrdcast_swap.py --identity Carey --target <img> --refs <folder> --out <dir> --quality best
```

must produce one job folder containing `final.png`, `face_detect_overlay.png`,
`mask_overlay.png`, `selected_reference.png`, `score.json` and `sidecar.json`.
The result need not be perfect yet — but the folder must show what was detected,
which reference was chosen, which route ran, and why it passed or failed.
(`--dry-run` produces exactly this folder with `accepted=false` and is verified
in the belt integration suite.)

## Config

`configs/byrdcast_swap_v0.json` — reference-selection weights, mask geometry,
route order, scoring weights + `accept_threshold`, quality-mode presets, and the
8GB hardware budget. Hosts are never hardcoded: the ComfyUI URL is read from
`byrdhouse.config.json services.comfyui`.

## Roadmap (explicitly NOT in V0)

Video is next after this (frame loop + temporal consistency reusing this
per-frame swap). Then multi-person (per-face fan-out) and prompt generation.
V0 is target-image replacement only — proven first, expanded second.
