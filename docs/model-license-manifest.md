# Model & License Manifest

Structured manifest (handoff §12.2) of every model/checkpoint/adapter the kit
references, its license, and whether it may touch the **funded/public lane**
(monetized CareyRPG output) or is **private-lane only** (local experiments).
Narrative model guidance lives in `docs/MODELS.md`; the live image-lane record
is `docs/IMAGE_GENERATION_STATE.md`. **Rule: no new model is installed or used
until its row exists here** with license, size, destination, and rollback.

Legend — lane: `funded` (commercial-eligible) / `private` (research or
unverified license; local experiments only) / `blocked` (do not install/use).

## Checkpoints

| Model | License | Lane | Location | Notes / rollback |
|---|---|---|---|---|
| Juggernaut-XL v9 | openrail++ | funded | `ComfyUI/models/checkpoints` | Recipe default photoreal. Rollback: delete file. |
| animagine-xl-4.0 | openrail++ | funded | same | Anime/stylized family. |
| RealVisXL V5.0 | openrail++ | funded | same | Photoreal family. |
| dreamshaper-xl (+ lightning) | openrail++ | funded | same | Versatile / 4-step drafts. |
| Meina V5.1 Baked VAE (SD1.5, 2.13 GB, sha256 `b4cca998…92ba`) | UNVERIFIED provenance | private | same | Quality-lane base. Independent provenance/license check required before any funded use (IMAGE_GENERATION_STATE follow-up #5). |
| Juggernaut XI | cc-by-nc-nd | blocked | — | Non-commercial; never ship with it. |

## Face / identity components

| Model | License | Lane | Location | Notes / rollback |
|---|---|---|---|---|
| inswapper_128.onnx (ReActor) | InsightFace research/non-commercial | private | `ComfyUI/models/insightface` | Direct-swap baseline for private experiments only. Rollback: delete + remove ReActor node pack. |
| buffalo_l (InsightFace detection) | research/non-commercial | private | auto-downloaded | Same restriction; ByrdCast Swap records it as detector when used. |
| GFPGANv1.4.pth | Apache-2.0 (Tencent ARC) | funded | `ComfyUI/models/facerestore_models` | Face restore after swap. |
| face_yolov8m.pt (Impact Subpack) | AGPL-3.0 (Ultralytics) | private† | `ComfyUI/models/ultralytics/bbox` | †Local detection tool; AGPL applies to redistribution/network service of the *software*, review before any hosted/public use. |
| control_v11p_sd15_canny fp16 (722,601,100 bytes, sha256 `8932b66e...7c9f10`) | OpenRAIL | funded | `ComfyUI/models/controlnet/control_v11p_sd15_canny.safetensors` | v3 guided cleanup; source `comfyanonymous/ControlNet-v1-1_fp16_safetensors`. Rollback: delete this file. |
| ip-adapter-plus_sdxl_vit-h + CLIP-ViT-H (h94) | Apache-2.0 | funded | `ComfyUI/models/ipadapter` + `clip_vision` | game_ref reference engine. |
| ip-adapter-plus-face_sd15 (98,183,288 bytes, sha256 `1c9edc21...f7569b`) | Apache-2.0 | funded | `ComfyUI/models/ipadapter/ip-adapter-plus-face_sd15.safetensors` | Avenue B real-photo identity anchor (CLIP-based, not InsightFace). Rollback: delete this file. |
| CLIP-ViT-H-14-laion2B-s32B-b79K (2,528,373,448 bytes, sha256 `6ca9667d...07b030`) | Apache-2.0 | funded | `ComfyUI/models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | Image encoder for the SD1.5 Plus Face adapter. Rollback: delete this file. |
| ComfyUI_IPAdapter_plus node pack (commit `a0f451a5113cf9becb0847b92884cb10cbdec0ef`) | GPL-3.0 | funded/local | `ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus` | Workflow implementation only; model licenses remain separate. Rollback: remove the node-pack directory and restart ComfyUI. |
| IP-Adapter **FaceID** variants | InsightFace dependency | blocked (funded) / private | — | Never in the funded lane (IMAGE_GENERATION_STATE rule). |
| mediapipe_face_fp32.safetensors (5.42 MB, sha256 `a98c4806…888a`) | Apache-2.0 (MediaPipe) | funded | `ComfyUI/models/detection` | 478-point mesh for the CPU examiner/seed lane. |
| SAM 2.1 Hiera Tiny checkpoint (156,008,466 bytes; sha256 `7402e0d8…be69`) | Apache-2.0 (Meta) | funded | `ComfyUI/models/sams/sam2.1_hiera_tiny.pt` | Prompted outer-head/ear/neck mold authority; official Meta URL only. Runtime code pinned to `facebookresearch/sam2@2b90b9f5ceec907a1c18123530e92e794ad901a4`. Rollback: delete checkpoint and `Generators/sam2`; the belt must then stop for reviewed masks, not fall back to ParseNet. |
| parsing_parsenet.pth (85.3 MB, sha256 `3d558d8d…20de2`) | UNVERIFIED | private | face-zone lane | Anime parser fallback; replace or license-clear before any funded/public/redistributed use. Candidates (also UNVERIFIED until checked): jonathandinu/face-parsing, skytnt/anime-seg. |
| photomaker-v1.bin (890.8 MB, TencentARC) | Apache-2.0 | blocked on 8 GB | `ComfyUI/models/photomaker` | Needs ≥11 GB VRAM; retained as disabled future-hardware option. PhotoMaker V2 rejected (InsightFace + VRAM). |

## Identity LoRAs (local, never committed)

All under `artifacts/lora/candidates/` on BYRD-GAMING — versioned filenames,
**never overwritten**, all currently *private preview / rejected* per the run
table in `docs/IMAGE_GENERATION_STATE.md`. No identity LoRA is approved for
any lane until visual + license gates pass. Rollback: files are inert unless
a recipe references them.

## Pending P1 lab installs (rows required BEFORE install)

ComfyUI-RMBG (light models only — INSPYRENET/BEN2 class, no SAM ViT-H),
comfyui_facetools, ComfyUI-Forbidden-Vision, ComfyUI_FaceShaper (benchmark
branch), Wan 2.2 Q4 dual-stage (P4 video lab). Each needs: repo URL + pinned
commit SHA, code license, model licenses + sizes + hashes, Python/Torch/CUDA
compatibility, conflicts, and uninstall steps recorded here first.
| Google Cartoon Set (optional geometry/attribute source; not installed) | CC BY 4.0 | funded with attribution | download only if needed, `training/datasets/google-cartoon-set` | Synthetic cartoon faces with published attributes; use for generic face/hair/eye geometry augmentation, not as a substitute for target-derived masks. Source: https://google.github.io/cartoonset/download.html. Rollback: delete dataset and attribution entry. |
