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
| control_v11p_sd15_canny | openrail | funded | `ComfyUI/models/controlnet` | ~700 MB; v3 guided cleanup. |
| ip-adapter-plus_sdxl_vit-h + CLIP-ViT-H (h94) | Apache-2.0 | funded | `ComfyUI/models/ipadapter` + `clip_vision` | game_ref reference engine. |
| ip-adapter-plus-face_sd15 (h94) | Apache-2.0 | funded | same | Avenue B real-photo identity anchor (CLIP-based, not InsightFace). |
| IP-Adapter **FaceID** variants | InsightFace dependency | blocked (funded) / private | — | Never in the funded lane (IMAGE_GENERATION_STATE rule). |
| mediapipe_face_fp32.safetensors (5.42 MB, sha256 `a98c4806…888a`) | Apache-2.0 (MediaPipe) | funded | `ComfyUI/models/detection` | 478-point mesh for the CPU examiner/seed lane. |
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
