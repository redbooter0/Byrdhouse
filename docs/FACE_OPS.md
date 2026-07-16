# FACE OPS — how the founder (or Codex) operates the Face Lab by hand

*The goal (founder, 2026-07-15): professional-grade face swaps like the viral
multi-person IG posts — identity carried perfectly while the target image's
entire look and feel (lighting, grain, linework, pose, clothes, vibe) stays
untouched. 100% local on BYRD-GAMING, our own likeness and references only —
evaluation targets are never trained on. The examiner spends REAL effort
understanding every image before any edit.*

One entry point for everything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 help
```

## 0. One-time installs (models to drop in manually)

Run `facelab.ps1 preflight` first — it tells you exactly what's missing. The
full list, with where each file goes (all under `E:\ByrdHouse\Generators\ComfyUI\`):

| What | Where | Get it | License |
|---|---|---|---|
| `control_v11p_sd15_canny.safetensors` (~700MB) | `models\controlnet\` | `huggingface.co/lllyasviel/ControlNet-v1-1` → Files | openrail ✅ |
| `mediapipe_face_fp32.safetensors` (5.42MB) | `models\detection\` | Comfy-Org (hash pinned in IMAGE_GENERATION_STATE.md) | Apache ✅ |
| `selfie_multiclass_256x256.tflite` (16MB) | per byrdfacezone `_selfie_segmenter_path` | Google MediaPipe releases | Apache ✅ |
| `Meina V5.1 - Baked VAE.safetensors` (2.13GB) | `models\checkpoints\` | already installed (hash pinned) | — |
| Impact Pack + Subpack (auto route) | ComfyUI Manager → Install both → restart | Manager | GPL-3 pack ✅ |
| `face_yolov8m.pt` | `models\ultralytics\bbox\` (installs with Subpack) | Manager Model Manager | AGPL — detection only |
| ReActor pack + `inswapper_128.onnx` + `GFPGANv1.4.pth` | Manager / `models\insightface`, `models\facerestore_models` | see MODELS.md | **research-only — private lane** |

PowerShell download example (any HF file, no CLI needed):

```powershell
Invoke-WebRequest -Uri "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_canny.safetensors" -OutFile "E:\ByrdHouse\Generators\ComfyUI\models\controlnet\control_v11p_sd15_canny.safetensors"
```

## 1. Examine — ALWAYS the first command on a new image

```powershell
powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 examine -Image E:\targets\gojo.png
```

Thorough scrutiny is the default (the founder rule — real effort before any
edit): every face gets a verdict (operable / with-care / refuse + why), risk
flags (`extreme_expression` = the Luffy-grin melt; `strong_profile`;
`too_small`), a **scale-stability cross-check** (the geometry is re-detected at
2x and compared — drifting landmarks mean the detector is guessing), occlusion
truth over the eye line, the per-feature likeness plan, a **recommended lane**,
and the elapsed analysis time on the report. `-Quick` skips the deep pass.

The same examiner runs automatically as the gate inside the quality lane — an
un-operable image refuses before a single GPU step, and the report rides the
artifact card.

## 2. The lane ladder — main plan + backups (founder rule: 3–5 ways, always keep what works)

| # | Lane | Command | When |
|---|---|---|---|
| **MAIN** | Quality mesh-seed (v2 two-pass, CPU-seed finish default — PROVEN on Gojo/Vegeta) | `facelab.ps1 quality -Image X -Preset gojo` | anime/stylized targets; the calibrated presets |
| B1 | Guided cleanup v3 (ControlNet canny holds geometry at denoise 0.55) | `facelab.ps1 quality -Image X -Preset vegeta` after setting the recipe to `anime_face_zone_edit@3`, or per-job `engine.gpu_passes` | when v2's seams need real GPU redraw — test-gated, needs the canny model |
| B2 | Zone route (your mask, GPU edits ONLY inside) | `facelab.ps1 zone -Image X -Mask M -Lora carey_face -Prompt "..."` | examiner refused / weird face the detector can't hold; masks from a zone preview or hand-drawn |
| B3 | Auto route (detector → mask → redraw as you) | `facelab.ps1 auto -Image X -Lora carey_face` | quick drafts, photoreal targets, batch runs |
| B4 | ReActor + blend (**private experiments only** — license) | `facelab.ps1 swap -Image X -Blend 0.35` | comparisons; never monetized output |
| B5 | Generate-as-character (`me_as_character` recipe, FaceID + LoRA) | dashboard Create tab | when swapping fights the art — draw you IN the style from scratch |

Group photos (the goal image): `examine` first — it reports every face with an
index — then run the chosen lane per face: `facelab.ps1 quality -Image X -FaceIndex 1`.

## 2b. Flow knobs (quality lane)

- **Canvas follows the face automatically** (512/640/768 from the examiner's
  measurement — large faces keep native detail). Force one: `engine.crop_size`.
- **Candidates per submit** (v3 guided lane): `engine.batch` 1–4 — encode once,
  sample N, every candidate composited + carded (`candidate x/N`); pick the
  keeper in the gallery. VRAM-clamped for the 3070.

## 2c. Extra avenues on the quality lane (reverse-engineered from proven 8GB setups)

The lane's default never changes — avenues ride as PARAMETERS
(`-Workflow` on facelab.ps1, `engine.workflow` on a job), so we test new ways
while the proven way keeps working:

| Avenue | Command | What it replicates | Needs |
|---|---|---|---|
| A — Seam killer | `facelab.ps1 quality -Image X -Workflow diffdiff` | the community's standard inpaint stack: DifferentialDiffusion turns our graded mask into a strength MAP (full rebuild at the core, feather at the ring) — aimed at the exact jaw/ear seam failure | core ComfyUI only |
| B — Photo anchor | `facelab.ps1 quality -Image X -Workflow ipadapter` | the most-replicated consistent-face stack: IP-Adapter PLUS FACE conditions on a REAL photo embedding (CLIP-based, Apache-2.0, NOT insightface) — identity no longer rides the unapproved LoRA alone | IPAdapter_plus pack + 2 models (§0) |
| C — Guided | `facelab.ps1 quality -Image X -Workflow controlnet` | ControlNet-canny geometry hold at 0.55 denoise (the v3 lane as a parameter) | canny model (§0) |
| D — PhotoMaker (SDXL) | Codex's smoke assets: `run-private-photomaker-smoke.py` + `sdxl_photomaker_v1_target_smoke_api.json` | TencentARC PhotoMaker stacked-ID embeddings | SDXL VRAM headroom; license verify before funded use |

Avenue-B model downloads:

```powershell
Invoke-WebRequest -Uri "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors" -OutFile "E:\ByrdHouse\Generators\ComfyUI\models\ipadapter\ip-adapter-plus-face_sd15.safetensors"
Invoke-WebRequest -Uri "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors" -OutFile "E:\ByrdHouse\Generators\ComfyUI\models\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
```

## 3. Identity (the LoRA that makes it YOU)

```powershell
# move the newest generated identity photos into the dataset (auto-searches
# profiles\me\references\generated_*)
powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 collect

# train a NEW versioned LoRA — never overwrites; auto-sizes to ~2,500 steps
powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 train
```

Codex's existing LoRA (37.9MB, step-400 checkpoint gated best, trigger
`careybh person`) stays untouched; the quality-lane recipes pin their own
identity block. Rules that never bend: real photos anchor geometry; generated
sets are support material; never train on Gojo/Vegeta/Luffy/Link images.

## 4. When something fails

- **Examiner refuses** → it says exactly why (too small → upscale the target
  first via dashboard refine; no face → wrong image). Never bypass with a
  rectangle; `--manual-box` in byrdfacezone is a recorded recovery tool.
- **Seams / lighting kept** → the cleanup was too weak: move up the ladder to
  v3 guided, or raise the pass denoise via `engine.gpu_passes`.
- **Identity washed out** → denoise too high without guidance: drop back to
  v2's CPU-seed finish (proven), or attach the LoRA + trigger word.
- **Luffy-grin melts** → the examiner flags `extreme_expression`; use v2
  multipass with lower `mesh_identity_strength` (the preset does this) and
  expect to pick from a batch.
- Every artifact card carries `face_report`, `upload_analysis`,
  `crop_preflight`, seeds and hashes — the full why of every result.

## 5. The rules the system enforces for you

- Examiner gate before any quality-lane GPU work (thorough by default).
- GPU never decides the mask; hair/headwear composited OVER the likeness.
- ≤7200MB VRAM verified before training; 16–18 CPU threads max.
- LoRA outputs versioned — nothing is ever overwritten.
- ReActor/FaceID = private lane only (research licenses); the funded lane is
  the mesh-seed + owner-LoRA architecture.
- Every artifact has a sidecar card; every change is reproducible.
