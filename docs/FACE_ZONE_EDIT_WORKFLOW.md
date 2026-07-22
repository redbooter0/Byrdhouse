# Semantic Face-Zone + Mesh-Seed Workflow

**Status:** implemented and exercised locally on BYRD-GAMING. The architecture transfers Carey identity/color into the Gojo target, but the current Naruto-seeded Gojo render fails the visual gate. This is a private calibration lane, not a production approval.

## Required behavior

For an owner-authorized face edit, ByrdHouse follows this exact belt:

```text
upload
  -> CPU 478-point face mesh + semantic parsing
  -> neck-connected face/head/ears above the neck, minus hair/headwear/accessories/clothing
  -> CPU Carey-reference triangle warp (identity mesh seed)
  -> low-denoise GPU cleanup inside the semantic mask
  -> CPU soft composite into the untouched upload
  -> artifact card + human review
```

The editable region is not a face rectangle and is not merely the inner landmark oval. It starts at the detected neck anchor, keeps the connected visible face/head/ears above it, fills facial-feature/ink holes, and removes hair, hats, jewelry, and clothing. Hair remains the target's hair. When a collar hides the neck, the record must say `neck_visible: false`; it must not claim a neck edit that was not visible.

If semantic confidence fails, stop for review. `--manual-box` remains a recorded elliptical recovery tool, not a normal dashboard editor and not permission to silently guess the face.

## Permanent implementation paths

| Component | Path | Responsibility |
| --- | --- | --- |
| Recipe | `recipes/anime_face_zone_edit.v1.json` | Pins the runner, cleanup graph, target prompts, LoRA defaults, and reviewed Carey identity references. |
| GPU graph | `workflows/sd15_face_mesh_seed_refine_api.json` | Encodes the retained mesh seed with `VAEEncode`, limits noise with `SetLatentNoiseMask`, and performs low-denoise cleanup. |
| Legacy fallback graph | `workflows/sd15_face_zone_inpaint_api.json` | Used only when no identity reference/mesh seed is available; it is not the current preset route. |
| CPU geometry/parser/composite | `scripts/byrdfacezone.py` | Detects the face, builds the semantic zone, warps the reference through 478 landmarks, writes audit artifacts, and performs the exact soft composite. |
| Belt adapter | `scripts/byrdimage.py` (`edit_face_zone`) | Resolves the preset reference, invokes CPU preparation, patches/runs ComfyUI, downloads the cleaned crop, and writes the card. |
| Worker handoff | `scripts/worker.py` (`face_zone_identity_edit`) | Fetches the router upload and dispatches the audited job. |
| State handoff | `docs/IMAGE_GENERATION_STATE.md` | Records the latest tested candidate, artifacts, failures, and deployment gates. |

## Runtime sequence

1. The dashboard uploads a target through the router and queues `anime_face_zone_edit@1`. GAMING pulls the job; production use must not bypass the belt for direct ComfyUI calls.
2. `byrdfacezone.py prepare` runs the CPU MediaPipe landmarker and semantic parser, selects the requested face, and creates a 512 px working crop.
3. The semantic rule writes `semantic_labels.png`, `hair_headwear_exclusion.png`, `neck_anchor_mask.png`, hard/graded/soft edit masks, skin-match ring, outline previews, and `face_zone.json`.
4. The recipe resolves the reviewed Carey anime reference for the target preset. CPU MediaPipe triangulation warps that reference into the target pose using 854 triangles and saves `identity_mesh_seed.png`, `identity_mesh_warp.png`, and `identity_mesh_warp_mask.png`.
5. ComfyUI loads the identity mesh seed and semantic edit mask. `VAEEncode` retains the seed latent; `SetLatentNoiseMask` restricts low-denoise cleanup to the face zone. The LoRA supports cleanup/identity but does not have to invent the face from noise.
6. The generated crop is soft-composited into the original. Pixels outside the saved soft mask remain the uploaded target's pixels. The final image, zone record, source/reference hashes, prompt/settings, and lineage are written to the artifact card for review.

## Reviewed reference map

| Target preset | Carey identity reference |
| --- | --- |
| `gojo` | `profiles/me/references/generated_anime_cartoon/002_naruto.png` |
| `vegeta` | `profiles/me/references/generated_anime_cartoon/013_yu-yu-hakusho.png` |
| `luffy_close` | `profiles/me/references/generated_anime_cartoon/003_one-piece.png` |
| `luffy_full` | `profiles/me/references/generated_anime_cartoon/003_one-piece.png` |

These are owner-authorized identity/style support images. The Gojo, Vegeta, and Luffy targets are evaluation images only and must never enter identity training.

## CPU model locks and license boundary

| Role | Local model | Size | SHA-256 | Deployment status |
| --- | --- | ---: | --- | --- |
| 478-point face geometry | `Generators/ComfyUI/models/detection/mediapipe_face_fp32.safetensors` | 5,423,900 B | `a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a` | Hash-locked local geometry model. |
| Six-class real-person segmentation | `Generators/ComfyUI/models/segmentation/selfie_multiclass_256x256.tflite` | 16,371,837 B | `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0` | Google MediaPipe Selfie Multiclass, Apache-2.0. Preferred path when it recognizes the image. |
| 19-class anime fallback | `Generators/ComfyUI/models/facedetection/parsing_parsenet.pth` | 85,331,193 B | `3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2` | **Private local evaluation only. Deployment license review required.** |

The Google model separates background, hair, body skin, face skin, clothes, and other. Anime images are often not recognized reliably, so the current local fallback is CodeFormer ParseNet. That fallback is useful for calibration, but its presence does not clear public, funded, commercial, or redistributed use. Replace it with a commercially cleared anime parser or obtain explicit permission before deployment.

The face geometry model source is `https://huggingface.co/Comfy-Org/mediapipe/resolve/main/detection/mediapipe_face_fp32.safetensors`; the Google segmenter source is `https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite`; the ParseNet weight source is the CodeFormer v0.1.0 release. Hash mismatch is a hard failure, never a silent substitution.

## Current Gojo evidence

The LoRA-only semantic tests proved that the larger neck-up-minus-hair mask works, but the model still produced a generic light/tan face and facial text artifacts. That established conditioning—not mask geometry—as the bottleneck.

The mesh-seed route then completed the local Naruto-pose test:

- Job: `face_mesh_gojo_naruto_d38_m60`
- Target: `Images/Targets/anime_games/anime_game_3.jpg`
- Reference: `profiles/me/references/generated_anime_cartoon/002_naruto.png`
- Output: `artifacts/image_lab/2026-07/20260714_anime_face_zone_edit_face_mesh_gojo_naruto_d38_m60_00001_.png`
- Zone record: `artifacts/face_zones/2026-07/face_mesh_gojo_naruto_d38_m60/face_zone.json`
- Mesh: 854 triangles, 88.008% edit-zone coverage; source detection score `0.949353`; target score `0.726651`
- Cleanup: 22 steps, CFG 5.0, denoise 0.38, seed 7124, LoRA model 0.60 / CLIP 0.75

**Verdict: visual gate failed.** It is valid architecture and identity/color-transfer proof, but the visible eye is distorted, the face has piercing-like artifacts, the retained target ear is pale, and the jaw/ear skin transition has a hard seam. Do not promote the LoRA or call the lane production-ready from this output.

## Approval gate

Gojo, Vegeta, Luffy close, and Luffy full must each pass:

1. **Identity:** the edited face clearly reads as Carey.
2. **Integration:** eye/ear/mouth geometry is clean; skin, linework, palette, and cel shading match; no text, piercing artifacts, or hard seam.
3. **Preservation:** target hair/headwear/clothes/background and every pixel outside the saved soft zone remain unchanged.

The current rank-32 step-1,200 LoRA and Meina V5.1 checkpoint remain private previews. Separately verify checkpoint provenance/license before any public or funded lane. Do not introduce InsightFace/FaceID-derived dependencies into that lane.
