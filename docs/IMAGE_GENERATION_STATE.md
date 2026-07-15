# Image Generation State — read before changing the GAMING image lane

**Last updated:** 2026-07-15 (EDT, CPU crop reroute + adapter crop-preflight gate verified on the hard Vegeta target; integration suite green)  
**Owner:** BYRD-GAMING (`E:\ByrdHouse`)  
**Rule:** Read this file before changing an image model, graph, training set, or route. Update it after every real local test.

## Current verdict

The compact local target-edit belt now performs semantic masking and CPU identity mesh seeding, but **no Carey LoRA candidate or finished face-edit lane is approved**. LoRA-only semantic edits still produce a generic light/tan face or text-like facial artifacts. Warping a reviewed Carey anime reference into the target's 478-point mesh is a real improvement: the Naruto-seeded Gojo run transfers Carey identity/color before GPU cleanup. It nevertheless fails the visual gate because of a distorted visible eye, piercing-like facial artifacts, a pale retained target ear, and a hard jaw/ear skin seam.

Do not promote or configure any candidate as the recipe's deployed identity LoRA.

## Staged 2026-07-15: guided cleanup v3 (UNTESTED on hardware — test before trusting)

Note: the two-pass v2 recipe the integration suite locks (`recipes/anime_face_zone_edit.v2.json`) was missing from the rescued branch and has been reconstructed exactly to the suite's spec (identity_fill 16/0.38 + line_harmonize 8/0.12, `skip_gpu_cleanup: true`, accessory truth per preset).

Diagnosis of "CPU beat GPU": the v1 cleanup pass was **unguided** img2img — at
denoise 0.38 it could not redraw seams/lighting (kept them), at ~0.9 it destroyed
the warped identity, and the whole-crop VAE round trip washed color either way.
The 3070 was never the limit; the pass had nothing to push against.

Staged fix (recipe `anime_face_zone_edit@3`, graph
`workflows/sd15_face_zone_controlnet_api.json`):

- **ControlNet CANNY guidance extracted from the identity mesh seed itself**
  (core ComfyUI nodes; model `control_v11p_sd15_canny.safetensors`, openrail,
  ~700MB → `models/controlnet`; Meina 2.13GB + LoRA + ControlNet ≈ well inside
  the 7200MB budget at 512px).
- Denoise raised to **0.55** with canny strength 0.55 / end 0.75: the sampler
  now redraws the WHOLE zone's linework (full face, forehead included — the
  jaw-to-jaw limitation goes away because the redraw covers the entire semantic
  mask) in the target's material while the seed's edges hold Carey's geometry.
- **Hair-over-likeness composite rule** (byrdfacezone `composite_generated`):
  after the paste, the target's hair/headwear pixels are re-asserted ON TOP of
  the likeness through a feathered `hair_headwear_exclusion` mask, so the zone
  boundary can never eat the hairline and overlapping strands win.
- v1 stays as rollback; `skip_gpu_cleanup` still selects the CPU-only finish.
- First hardware test: rerun the Gojo (Naruto-seed) and hard-Vegeta targets on
  `anime_face_zone_edit@3`; sweep denoise 0.45–0.6 × canny strength 0.45–0.65;
  record VRAM + verdicts here per the rule above.

## Staged 2026-07-15 (later): the examiner — understand before touching (UNTESTED on hardware)

Founder contract: for ANY uploaded image the system must FIRST fully understand
where it can and can't operate, then plan which features get the founder's
likeness while keeping the target's logic/shape/theme. Start small: geometry
v1, semantic enrichment next.

- `byrdfacezone.py analyze` (new subcommand, edits nothing, landmarker-only,
  runs in any GPU mode): every face → box, size, yaw proxy, mouth-open ratio,
  verdict (`operable` / `operable_with_care` / `refuse` with reasons), risk
  flags — `extreme_expression` is the Luffy-grin case that melted the
  d36/m60 run; `strong_profile`; `too_small` — and the per-feature plan
  (skin/brow/nose/mouth/jaw = generate-likeness-in-target-form; eyes =
  keep-target; forehead = likeness-if-exposed; hair/headwear = keep-target
  composited OVER the likeness; expression/pose/theme = keep-target).
  Writes `face_report.json` + ONE clean overview PNG (numbered green/yellow/red
  boxes — replaces mesh/parse spaghetti as the founder-facing diagnostic).
- **Gate wired into the quality lane**: `edit_face_zone` now runs the examiner
  first and refuses with the examiner's own reasons before any zone/GPU work;
  the report rides every card (`face_report`).
- **Examine route** on `image.faceswap` (`route:"examine"`, dashboard "Examine
  first", required_mode ANY): archives the overview + verdict as an artifact so
  the founder sees operability before spending anything.
- Next rungs (in order, small steps): semantic enrichment of the report
  (headwear/eye occlusion truth from the parser — Gojo blindfold), per-face
  preset auto-suggestion from flags, multi-face batch operation.
- Thorough scrutiny (founder rule, 2026-07-15 later): `analyze --thorough` is
  the DEFAULT for the quality-lane gate and the examine route (`engine.quick_report`
  / `-Quick` opt out). Adds per-face scale-stability cross-check (re-detect at 2x,
  landmark drift → `geometry_stability` 0–1), parser occlusion truth over the eye
  line, a `recommended_lane` mapped to the FACE_OPS ladder, and `analysis_seconds`
  on the report — provable effort before any edit. Operator entry point:
  `scripts/facelab.ps1` (preflight/examine/quality/zone/auto/swap/collect/train);
  full manual in `docs/FACE_OPS.md`.
- First hardware test: `python scripts\byrdfacezone.py analyze --input <image>`
  on the five calibrated targets + one group shot + one no-face image; verify
  verdicts/flags match reality (Luffy close must flag extreme_expression);
  then one `route:"examine"` job through the belt.

Parser replacement candidates for the ParseNet license gap (both LICENSE-UNVERIFIED
— treat exactly like ParseNet, private local evaluation only, until the license is
confirmed): `jonathandinu/face-parsing` (SegFormer/CelebAMask-HQ via HF
transformers, strong on real photos) and `skytnt/anime-seg` (anime character
matting — a hair/character matte source for anime targets).

## Current CPU face-zone state

The permanent target-edit architecture is **upload -> CPU 478-point mesh + semantic parser -> neck-connected face/head/ears above the neck minus hair/headwear/accessories/clothing -> CPU Carey-reference triangle warp -> CPU-only seed/composite when that looks better than GPU cleanup -> CPU soft composite -> card/review**. Its detailed handoff is [`FACE_ZONE_EDIT_WORKFLOW.md`](FACE_ZONE_EDIT_WORKFLOW.md). The belt works end to end, and the CPU crop preflight now expands and re-audits clipped head/neck envelopes before any GPU work. For the current v2 lane, CPU-only seed finishing is the preferred default because the GPU cleanup degraded the hard target. This is still not a quality or deployment approval.

- The CPU tool is `scripts/byrdfacezone.py`; the belt adapter is `scripts/byrdimage.py` (`edit_face_zone`); the worker route is `scripts/worker.py` (`face_zone_identity_edit`).
- Recipe: `recipes/anime_face_zone_edit.v1.json`. Current GPU workflow: `workflows/sd15_face_mesh_seed_refine_api.json` (`VAEEncode` + `SetLatentNoiseMask`). The older `workflows/sd15_face_zone_inpaint_api.json` is only the no-reference fallback.
- The mesh model is `Generators/ComfyUI/models/detection/mediapipe_face_fp32.safetensors`, 5,423,900 bytes (5.42 MB), SHA-256 `a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a`.
- The preferred semantic model is Google's `selfie_multiclass_256x256.tflite`, 16,371,837 bytes, SHA-256 `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`, Apache-2.0. It works on real photos but does not reliably recognize anime.
- The current anime fallback is `parsing_parsenet.pth`, 85,331,193 bytes, SHA-256 `3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2`. It is **private-local-evaluation-only** and requires a deployment license review/replacement before any funded, commercial, public, or redistributed lane.
- Do not replace the semantic route with a rectangle editor. The CLI `--manual-box` is a reviewed recovery fallback that records `manual_zone: true`; it is not a normal UI edit mode. Stop rather than silently guessing when semantic confidence fails.
- Reviewed preset references: Gojo -> `002_naruto.png`; Vegeta -> `013_yu-yu-hakusho.png`; Luffy close/full -> `003_one-piece.png`, all under `profiles/me/references/generated_anime_cartoon/`.
- The Naruto-seeded Gojo job `face_mesh_gojo_naruto_d38_m60` completed with 854 triangles and 88.008% edit-zone coverage. Output: `artifacts/image_lab/2026-07/20260714_anime_face_zone_edit_face_mesh_gojo_naruto_d38_m60_00001_.png`. It proves the architecture and identity/color transfer, but **fails** visual quality for the eye/artifact/ear/seam defects above.\n- The hard Vegeta CPU reroute `vegeta_crop_reroute_jaw_fit_foundation_06` successfully expanded the crop from `x=212,y=42,w=288,h=288` after one reroute (`crop_preflight.reroutes = 1`) and passed the full neck-to-head analysis before GPU work.\n- The local CPU-only rerun `job_19f644b00fbkrcxdf` completed with `skip_gpu_cleanup = true` and archived the better-looking seed/composite path for the hard Vegeta target.
- Current preview candidate: `artifacts/lora/candidates/carey_meina_sd15_expanded_hybrid_r32_20260714_125628-step00001200.safetensors`, rank 32 / step 1,200, SHA-256 `ad5d34e32d32099a6f0f813064dc62fdccd0b429b89ff415b0ba17e83e78fc13`. Preview only; never deployed.
- All support references are audited: generated animation/cartoon IDs `001-100` and synthetic-photoreal IDs `101-200`. They remain support material, not automatic approval of any LoRA.

## What is working locally

- GAMING hardware: RTX 3070 8 GB, 32 GB RAM.
- Base: `Meina V5.1 - Baked VAE.safetensors` (SD 1.5, 2.13 GB), SHA-256 `b4cca998e3be0c9c757527d77691d335cd194998aa845a798a68923f9a2d92ba`.
- ComfyUI runs locally at `http://127.0.0.1:8188` with dynamic VRAM. It is currently open in a visible PowerShell window.
- Local dashboard/router is open at `http://127.0.0.1:8787` for visual workflow review. It is a GAMING-local display instance; `byrd-mini` is still not resolvable, so the actual two-PC handoff is not yet live.
- Target route: `Dashboard upload → router artifact → GAMING worker → target_identity_edit → local ComfyUI → card/artifact → review`.
- Target graph: `workflows/sd15_anime_target_identity_api.json`.
- Recipe: `recipes/anime_face_edit.v1.json`; calibrated targets are Gojo, Vegeta, Luffy close, and Luffy full.
- Permanent face-zone graph: `workflows/sd15_face_mesh_seed_refine_api.json`; recipe: `recipes/anime_face_zone_edit.v1.json`; see `docs/FACE_ZONE_EDIT_WORKFLOW.md`.
- Isolated trainer: `Generators/sd-scripts/` v0.11.1 in its own venv; it passed local CUDA training without changing ComfyUI.
- `python tests/integration_test.py` passed locally after the image-lane changes and again after the hybrid/studio/PhotoMaker experiments on 2026-07-14.

## Policy and architecture

- Keep production jobs on the audited `image.generate` belt. Do not create a direct-Comfy production bypass.
- Do not use ReActor, ReSwapper, or IP-Adapter FaceID in the funded/public lane: they rely on InsightFace research/non-commercial face-recognition dependencies.
- The intended compliant lane is an owner-authorized SD1.5 identity LoRA with trigger `careybh person`.
- The supplied Gojo/Vegeta/Luffy images are **evaluation targets only**; never train an identity model on them.
- Generated anime/cartoon references never replace real-photo facial geometry. They may only be used as a separately weighted, user-approved style-support bucket after visual review.

## Reference set and staging rules

The private Carey-only source folders are:

- `profiles/me/references`
- `profiles/me/references/generated_anime_cartoon`
- `profiles/me/references/generated_real_photos`

Current strong real-photo set selected by `scripts/prepare-carey-lora-dataset.py`:

`me_photo_01`, `02`, `03`, `04`, `05`, `07`, `09`, `11`, `12`, `13`, `14`, `15`, `19`

- `06`, `08`, and `17` are optional only: cap/hard shadow, washed/redundant, or reflective glasses.
- `10`, `16`, `18`, and `20` are excluded: tiny face, motion softness, blur/hand distraction, or soft cluttered framing.
- `me_photo_21` and `22` are clean synthetic studio anchors used by the current photoreal generation stream; do not label them as camera ground truth.
- The six `ai_identity_*.png` studio portraits are synthetic, not real-photo anchors. They are useful as carefully weighted angle-support material.
- The animation library IDs `001-100` and synthetic-photoreal IDs `101-200` are complete and audited. They remain separately labeled support material; generated images never become camera-photo ground truth.

Current staged real-only dataset:

- `profiles/me/lora_dataset/identity/10_careybh`
- 13 camera originals + 26 visually verified tight/medium face crops = **39 training images**, repeat 10.
- Face crops are created by `scripts/build-carey-face-crops.py` using local OpenCV. All 26 current crops were visually checked on `artifacts/image_lab/2026-07/carey_identity_real_crops_20260714.png`; the fallback crop for braided photo 03 is also correct.

Current staged hybrid diagnostic dataset:

- `profiles/me/lora_dataset/anime-mix/5_careybh_real`: 8 real originals + 16 face crops, repeat 5.
- `profiles/me/lora_dataset/anime-mix/3_careybh_studio`: 6 generated studio-angle portraits, repeat 3.
- `profiles/me/lora_dataset/anime-mix/2_careybh_anime`: 18 visually reviewed, user-owned anime portraits, repeat 2.
- The weighted loader reports 174 effective samples. Real material remains 69% of each epoch; studio and anime assets are supporting signals only.

Current staged studio-core diagnostic dataset:

- `profiles/me/lora_dataset/studio-core/5_careybh_real`: 8 real originals + 16 verified face crops, repeat 5.
- `profiles/me/lora_dataset/studio-core/6_careybh_studio`: 6 clean studio identity views + 12 verified face crops, repeat 6.
- The weighted loader will report 228 effective samples. This deliberately removes anime scenes and gives facial geometry from clean studio views near-equal exposure to the real-photo bucket.
- A local 20-step U-Net + text-encoder smoke test completed at 2026-07-14 01:59 EDT without memory or loader errors. Its 18.11 MB file is a smoke artifact only, not a quality candidate.

## Training launcher status

`scripts/train-carey-meina-lora.ps1` is now reliable on this machine:

- `-FaceCrops` stages face-focused 512 px training images.
- `-TrainTextEncoder` removes `--network_train_unet_only` and adds `--text_encoder_lr 5e-5`.
- Comfy stop confirmation no longer treats an expected offline connection as fatal.
- LM Studio's harmless “no models to unload” stderr no longer aborts training.
- Accelerate's harmless defaults notice no longer aborts training; native exit code is checked explicitly.

Use a 10-step text-encoder smoke test before changing base model/rank/hardware. It passed on the RTX 3070. The new weighted hybrid data path also completed a 20-step GPU smoke test at 2026-07-13 23:42 EDT: 174 effective samples, 72 text-encoder modules, 192 U-Net modules, 18.11 MB candidate. It is a parser/VRAM proof only, never a quality candidate.

## Candidate test record — rejected and pending

| Candidate | Dataset / training | Result |
|---|---|---|
| `carey_meina_sd15_anime_mix_20260713_204036.safetensors` | 6 real + 9 anime, U-Net only, 300 steps | Generic Gojo; reject. |
| `carey_meina_sd15_identity_20260713_210157.safetensors` | 8 earlier real selection, U-Net only, 650 steps | Generic face at normal strength; distorted generic face at high strength; reject. |
| `carey_meina_sd15_identity_20260713_213808.safetensors` | 6 strong real + 12 crops, U-Net only, 700 steps | Generic targets; reject. |
| `carey_meina_sd15_identity_20260713_215809.safetensors` | 6 strong real + 12 crops, U-Net + text encoder, 700 steps | Correct text encoder tensors, but still generic targets; reject. |
| `carey_meina_sd15_identity_20260713_221853.safetensors` | 8 strong real + 16 crops, U-Net + text encoder, 900 steps | 792 tensors / 216 text-encoder tensors / 24 images; Gojo, Vegeta, both Luffys, and high-influence Gojo all remain generic; reject. |
| `carey_meina_sd15_anime_mix_20260714_000944.safetensors` | 8 real + 16 real crops (repeat 5), 6 studio views (repeat 3), 18 reviewed anime portraits (repeat 2), U-Net + text encoder, 1,200 steps | All four normal targets remain target-like/generic. High-influence Gojo shifts toward broad Black-male facial features, but not recognizably Carey; reject. |
| `carey_meina_sd15_studio_core_20260714_020203.safetensors` | 8 real + 16 real crops (repeat 5), 6 clean studio views + 12 studio crops (repeat 6), U-Net + text encoder, 1,200 steps | Gojo at 600, 800, 1,000, and 1,200 steps produces nearly the same generic altered face; reject before wasting the remaining three target runs. |
| `carey_meina_sd15_identity_20260714_044058.safetensors` | 13 camera originals + 26 verified face crops, per-photo variable captions, U-Net + text encoder, rank/alpha 16, 1,600 steps / 5 epochs | Target-free 1,200-1,600 gates learn a consistent Carey-like photoreal face. Normal masked anime edits remain generic; high-denoise edits paste photo appearance/backgrounds. Split model/CLIP strengths restore anime style but lose too much identity. Retain as private teacher/evaluation candidate; do not deploy. |
| `carey_meina_sd15_expanded_hybrid_r32_20260714_125628-step00001200.safetensors` | Expanded hybrid support set, U-Net + text encoder, rank/alpha 32, step 1,200 | Private preview only. LoRA-only semantic edits remain generic/light or add face text. Naruto mesh seeding transfers identity/color, but the d0.38 Gojo output fails on eye distortion, piercing-like artifacts, pale ear, and jaw/ear seam. Never deploy or promote from this result. |

Latest rejected candidate metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_identity_20260713_221853.safetensors`
- SHA-256: `88C6612386D89E716E7F0E920E7A469A8D2644FAF4B5CD02578B41D3D0C71007`
- 900 steps, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder).
- Temporary Comfy preview: `carey_meina_sd15_identity_te_8real_preview.safetensors`; preview only, never deploy.

Important discovery: earlier U-Net-only candidates had exactly zero `lora_te*` tensors. The text-encoder change fixed that technical defect, but did not make the limited source set sufficiently recognizable.

The direct text-to-image portrait diagnostic also produced only a plausible generic person with broad traits, confirming that this is not solely a target-mask issue.

PhotoMaker V2 was assessed and rejected before installation: the built-in Comfy nodes are V1-only, the V2 route requires InsightFace licensing, and official guidance calls for at least 11 GB VRAM. A partial 1.8 GB adapter download was stopped and removed completely; it is not in the project model path.

Latest rejected hybrid metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_anime_mix_20260714_000944.safetensors`
- SHA-256: `3E22C6924A9C923079514A07EB11C73132B5ED73959DBCBE88FAF4E6B3BD02A1`
- 1,200 steps, seven epochs, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder).
- Fixed-seed normal validation report: `artifacts/image_lab/2026-07/validation_hybrid_1200_20260714_011444.json`; high-influence report: `validation_hybrid_1200_boundary_20260714_014740.json`.

Latest rejected studio-core metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_studio_core_20260714_020203.safetensors`
- SHA-256: `5588BEBAD2BCEBB3B6050D124EF0432AB85E5B480ACE8DC32C31956763224062`
- 1,200 steps, six epochs, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder); data buckets: 24 real/crop images ×5 and 18 studio/studio-crop images ×6.
- Gojo checkpoint-selection reports: `validation_studio_600_20260714_022156.json`, `validation_studio_800_20260714_022159.json`, `validation_studio_1000_20260714_022202.json`, and `validation_studio_1200_20260714_022206.json`.

PhotoMaker V1 private test:

- Official `TencentARC/PhotoMaker` V1 is Apache-2.0, direct-reference, and its 890.8 MB `photomaker-v1.bin` is present under `Generators/ComfyUI/models/photomaker/`.
- The built-in Comfy V1 nodes load without InsightFace. A private, non-app 512 px masked Gojo smoke ran at roughly 7.0 GB GPU memory, but the face output was corrupted/unusable (`artifacts/image_lab/2026-07/private_gojo_smoke_00001_.png`).
- Official PhotoMaker guidance lists 11 GB minimum; do not route V1 to the 8 GB worker. Retain the adapter only as an explicitly disabled future-hardware option.
- All temporary Carey preview copies were removed from `Generators/ComfyUI/models/loras`; the application has no active Carey identity candidate.

## Next gate — do not skip

1. Fix the Naruto-seeded Gojo cleanup defects: distorted eye, piercing-like artifacts, pale target ear, and hard jaw/ear skin seam. Re-run with the same saved semantic/mesh evidence so changes are attributable.
2. Only after Gojo passes identity, integration, and preservation, run Vegeta (`013_yu-yu-hakusho.png`) and both Luffys (`003_one-piece.png`). A single attractive crop is not enough.
3. Keep the audited IDs `001-100` and `101-200` in separate buckets. Camera photos remain ground truth; synthetic-real and animation images are support material only.
4. Do not deploy the rank-16 teacher, the rank-32 preview, or any generated-real-only derivative. A pass requires recognizable Carey identity, native anime integration, and preservation outside the saved soft zone.
5. Before any public/funded deployment, independently verify the provenance and license of `Meina V5.1 - Baked VAE.safetensors`; it is currently a private test checkpoint, not an approved public checkpoint.
6. Replace or explicitly clear the ParseNet anime fallback before funded/public deployment. If further conditioning is needed, evaluate another **license-compatible** reference-conditioning model or higher-VRAM worker before downloading/installing it; do not silently introduce InsightFace FaceID components into the funded lane.

## Exact validation settings

- Current mesh-seed baseline: 22 steps, CFG 5.0, denoise 0.38, LoRA model strength 0.60 / CLIP strength 0.75.
- Naruto-seeded Gojo baseline: seed `7124`, 854 triangles, 88.008% edit-zone coverage. It is a failed calibration baseline, not approval evidence.
- Earlier LoRA-only target diagnostics used identity strength `0.90`, 18 steps, CFG 6.0, denoise 0.48; the Gojo boundary test used identity strength `1.25`, 22 steps, CFG 6.0, denoise 0.60.
- Fixed seeds: Gojo `7124`, Vegeta `7125`, Luffy close `7126`, Luffy full `7127`, high-influence Gojo `7133`.
- A candidate must visibly read as Carey in normal target renders; a high-influence artifact is diagnostic evidence only, never a pass.
- Rank-16 split-strength diagnostics added separate `strength_model` / `strength_clip` support to `scripts/byrdimage.py`; this is an experimental calibration control, not evidence of approval.


