# Model & License Manifest

Structured manifest (handoff §12.2) of every model/checkpoint/adapter the kit
references, its license, and whether it may touch the **funded/public lane**
(monetized CareyRPG output) or is **private-lane only** (local experiments).
Narrative model guidance lives in `docs/MODELS.md`; the live image-lane record
is `docs/IMAGE_GENERATION_STATE.md`. **Rule: no new model is installed or used
until its row exists here** with license, size, destination, and rollback.

Legend — lane: `funded` (commercial-eligible) / `private` (research or
unverified license; local experiments only) / `blocked` (do not install/use).

## Windows RX 7900 XT local restoration — 2026-10-02

The founder authorized installing local image models on this PC and requires all
Carey examples to preserve his Black identity and resemble his original photos.
This is a separate single-PC lane; the historical 8 GB lane below remains history.
All current identity outputs remain private candidates awaiting likeness review.

| Component | Source / license | Installed size and destination | Rollback |
|---|---|---|---|
| GPEN-BFR-512 ONNX repair | [ReActor maintainer distribution](https://huggingface.co/datasets/Gourieff/ReActor/blob/main/models/facerestore_models/GPEN-BFR-512.onnx); license unverified, private local evaluation only | Verified 284,244,491 bytes; SHA256 `bf80acb8e91ba8852e3f012505be2c3b6cd6b3eed5ec605e3db87863c4e74d4e`. ONNX parser/checker passed. Installed in ComfyUI models/facerestore_models; truncated prior file retained under external/models/reactor. | Configure GFPGAN instead; preserve repair and prior file for audit. |
| AdvancedLivePortrait evaluation | [Upstream implementation and supplied workflows](https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait), based on LivePortrait; converted model distribution Kijai/LivePortrait_safetensors | Installed source commit `3bba732915e22f18af0d221b9c5c282990181f1b` via extension junction. Five model hashes matched Hub revision `59f30f36d7b791929c25437df7461d5b0e0010b1`; full hashes in models/liveportrait/provenance.json. Added missing timm/lmdb/tyro dependencies and upstream-required Bingsu/adetailer face_yolov8n.pt. AMD execution verified: 44-frame original Carey photo animation, 44.94 s. License review remains outstanding; private local evaluation only. | Keep separate from default still route; unlink extension if incompatible. |
| RealVisXL V5.0 Lightning FP16 | [Creator model card](https://huggingface.co/SG161222/RealVisXL_V5.0_Lightning), OpenRAIL++; FaceID/InsightFace combination remains private evaluation | 6,938,065,512 bytes, `D:\ByrdHouse\models\checkpoints\RealVisXL_V5.0_Lightning_fp16.safetensors`; revision `f4454158cedaab9f0688c199561d6c92525f3a85`; SHA256 `fabcadd9330dcc4f9702063428d40b9d4d07168d8acefc819b8d1d9db466b3ec` verified | Remove `fast_checkpoint` setting to restore base SDXL + Lightning LoRA fast mode; retain the downloaded file. |
| FLUX.2 Klein 4B distilled BF16 | [BFL model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B), Apache-2.0; Comfy-Org conversion | 7.22 GiB, `D:\ByrdHouse\models\diffusion_models\flux-2-klein-4b.safetensors` | Select SDXL; unlink this model only when ComfyUI is stopped. |
| Qwen3 4B text encoder | [Qwen model card](https://huggingface.co/Qwen/Qwen3-4B), Apache-2.0; Comfy-Org conversion | 7.49 GiB, `models\text_encoders\qwen_3_4b.safetensors` | Disable FLUX; retain source download. |
| FLUX2 VAE | Official [Comfy-Org distribution](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b); Klein 4B stack; redistribution review still required | 0.31 GiB, `models\vae\flux2-vae.safetensors` | Disable FLUX; retain source download. |
| IP-Adapter Plus Face SDXL ViT-H | [h94](https://huggingface.co/h94/IP-Adapter), Apache-2.0, CLIP-based | 847,517,512 bytes, `models\ipadapter` | Select FLUX; remove custom node after stopping ComfyUI. |
| CLIP ViT-H image encoder | h94 distribution, upstream OpenCLIP/LAION provenance; existing manifest allowance | 2,528,373,448 bytes, `models\clip_vision` | Disable SDXL reference route. |
| ComfyUI_IPAdapter_plus software | cubiq, GPL-3.0, pinned `a0f451a5113cf9becb0847b92884cb10cbdec0ef` | `ComfyUI\custom_nodes\ComfyUI_IPAdapter_plus` | Disable SDXL reference route; remove directory after stopping ComfyUI. |
| Carey v2 SDXL identity LoRA | Locally trained, SDXL base obligations; **private preview**, no likeness approval | 46.7 MB, `models\loras\carey_sdxl_v2_full.safetensors` | Choose FLUX. Never imply that the LoRA is approved. |
| BiRefNet background matting | [Comfy-Org/BiRefNet](https://huggingface.co/Comfy-Org/BiRefNet), MIT; pinned revision `35767b272f2846752a3aee1259abdd4586f735c8` | Verified 444,473,596 bytes; SHA256 `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154`; `D:\ByrdHouse\models\background_removal\birefnet.safetensors`. It will create an alpha edge matte for private source-preservation checks only; it does not establish Carey likeness. | Stop ComfyUI, remove the model file and the `background_removal` model-path mapping, then restart. |
| InstantID SDXL reference conditioning | [InstantX/InstantID](https://huggingface.co/InstantX/InstantID), Apache-2.0 checkpoint; [nosiu ComfyUI adapter](https://github.com/nosiu/comfyui-instantId-faceswap), Apache-2.0. Its required InsightFace/antelopev2 face models are research/non-commercial. | Existing local adapter `ComfyUI\models\ipadapter\ip-adapter.bin`, 1,691,134,141 bytes, SHA256 `02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1`; ControlNet 2,502,139,136 bytes, SHA256 `c8127be9f174101ebdafee9964d856b49b634435cf6daa396d3f593cf0bbbb05`; antelopev2 is present. **Private likeness benchmark only**, separate from source-preserved stills. | Do not expose or fund this lane. Disable the InstantID operation; uninstall only after ComfyUI is stopped and its model files are backed up. |
| PuLID v1.1 SDXL identity conditioning — qualification candidate | Official [PuLID code](https://github.com/ToTheBeginning/PuLID) and [v1.1 weights](https://huggingface.co/guozinan/PuLID) are Apache-2.0. The Comfy adapter candidate is [yashikawa3/ComfyUI-PuLID](https://github.com/yashikawa3/ComfyUI-PuLID) commit `c672e2a88580afe59773bde1576ce1838abd1a0f`; it contains no LICENSE file, so its provenance is recorded as unresolved and this remains a **private local qualification**. | Verified 984,405,232 bytes; SHA256 `4cb8ceec1078e0165399b88332ab3c5971619111b8e1730e6bae64144aabae41`; installed at `D:\ByrdHouse\models\pulid\pulid_v1.1.safetensors`. Required `antelopev2` models already exist. The candidate requires only `facexlib`, `filterpy`, `numba`, and `ftfy` beyond the active ROCm venv; dry-run resolved CPython 3.13 wheels. EVA-CLIP is pinned to D: by a documented one-line cache-path patch before first inference. | Keep staged code in `D:\ByrdHouse\external\ComfyUI-PuLID-v1_1-candidate`; remove the `pulid` model-path mapping, custom-node directory, and four added Python packages only while ComfyUI is stopped. |
| ControlNet Union SDXL 1.0 — pose/depth structure for the PuLID lab | [xinsir/controlnet-union-sdxl-1.0](https://huggingface.co/xinsir/controlnet-union-sdxl-1.0), Apache-2.0. Selected by the staged CivitAI SDXL IP-Adapter + Union workflow. | Verified 2,512,030,408 bytes; SHA256 `a9e13fd61f3193887791c8a0dd07a07202174dc47d5ddaea94ea1344f07c7467`; installed at `D:\ByrdHouse\models\controlnet\diffusion_pytorch_model.safetensors`. This single control model supports OpenPose and Depth; it controls structure, never Carey identity. | Stop ComfyUI, remove the model and `controlnet` mapping, then restart. |
| SDPose WholeBody FP16 — pose-map preprocessor for the PuLID lab | [Comfy-Org/SDPose](https://huggingface.co/Comfy-Org/SDPose), MIT; a repackaging of its cited original whole-body pose project. | Verified 1,916,645,792 bytes; SHA256 `63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721`; installed at `D:\ByrdHouse\models\checkpoints\sdpose_wholebody_fp16.safetensors`. It produces a pose map only and carries no Carey identity data. | Stop ComfyUI, remove this one checkpoint, then restart. |
| Animagine XL 4.0 Opt — ByrdHouse illustrated-keyframe candidate | [Cagliostro Labs model card](https://huggingface.co/cagliostrolab/animagine-xl-4.0), CreativeML Open RAIL++-M; SDXL 1.0 fine-tune. It is the selected checkpoint for the owner-approved Carey Anime Canon Anchor v1, not for photoreal likeness claims. | **Verified installed; first new-scene pose test rejected.** Official Hub revision `2b7c1b397761bf5bd3cc42e5b39ec99314a75a96`; 6,938,350,040 bytes; official and locally verified SHA256 `6327eca98bfb6538dd7a4edce22484a1bbc57a8cff6b11d075d40da1afb847ac`; destination `D:\ByrdHouse\models\checkpoints\animagine-xl-4.0-opt.safetensors`. Job `97b0b62f810d753cec3bf3c836329261` was visually rejected for Carey-canon drift; model remains a private local qualification tool until an approved anchor kit exists. | Remove only this checkpoint while ComfyUI is stopped; remove its Studio configuration entry; preserve the manifest and download log. |

FLUX component downloads pinned to Comfy-Org revision
`5f526678002e43af5551dadb73ce2e8c91b43afe`. `hf cache verify` passed for all
three downloaded model files (other repo files were intentionally not downloaded).
Installed filenames are hard links to these verified files on the same D: volume.
SHA-256: model `ec3d4e733a771f61c052fb4856c48b336c55eaf2c65487c2a1faeb9bbda7a343`;
encoder `6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a`;
VAE `868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3`.

## Historical checkpoints

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
| jonathandinu/face-parsing SegFormer | [Author model card](https://huggingface.co/jonathandinu/face-parsing) states non-commercial research and educational purposes (checked 2026-10-03) | private | Existing ComfyUI/models/face_parsing/model.safetensors, 338,580,732 bytes | CPU semantic masks for private source-preservation qualification. Registration is not coverage approval; inspect curls/face before editing. Disable the new source-mask route to roll back; preserve installed files. |
| inswapper_128.onnx (ReActor) | InsightFace research/non-commercial | private | `ComfyUI/models/insightface` | Direct-swap baseline for private experiments only. Rollback: delete + remove ReActor node pack. |
| buffalo_l (InsightFace detection) | research/non-commercial | private | auto-downloaded | Same restriction; ByrdCast Swap records it as detector when used. |
| GFPGANv1.4.pth | Apache-2.0 (Tencent ARC) | funded | `ComfyUI/models/facerestore_models` | Face restore after swap. |
| face_yolov8m.pt (Impact Subpack) | AGPL-3.0 (Ultralytics) | private† | `ComfyUI/models/ultralytics/bbox` | †Local detection tool; AGPL applies to redistribution/network service of the *software*, review before any hosted/public use. |
| control_v11p_sd15_canny | openrail | funded | `ComfyUI/models/controlnet` | ~700 MB; v3 guided cleanup. |
| ip-adapter-plus_sdxl_vit-h + CLIP-ViT-H (h94) | Apache-2.0 | funded | `ComfyUI/models/ipadapter` + `clip_vision` | game_ref reference engine. |
| ip-adapter-plus-face_sd15 (h94) | Apache-2.0 | funded | same | Avenue B real-photo identity anchor (CLIP-based, not InsightFace). |
| IP-Adapter **FaceID** variants | InsightFace dependency | blocked (funded) / private | — | Never in the funded lane (IMAGE_GENERATION_STATE rule). |
| mediapipe_face_fp32.safetensors (5,423,900 bytes, sha256 `a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a`) | Apache-2.0 ([Comfy-Org model card](https://huggingface.co/Comfy-Org/mediapipe), original Google MediaPipe) | funded geometry tool; alignment unqualified | Primary `D:\ByrdHouse\models\detection`; 5.42 MB runtime copy under current ComfyUI/models/detection | Restore from Comfy-Org/mediapipe revision `f787efc1ad99492ec7d5b6564c0dd6c48d84ee49`, file `detection/mediapipe_face_fp32.safetensors`. Existing CPU 478-point loader; no new Python package or CUDA node. Plan/verification in `external/workflows/carey-hairline-v2/face-mesh-download-plan.json`. Rollback: leave weights inert and disable candidate mesh use; do not remove established runtime or artwork. |
| parsing_parsenet.pth (85.3 MB, sha256 `3d558d8d…20de2`) | UNVERIFIED | private | face-zone lane | Anime parser fallback; replace or license-clear before any funded/public/redistributed use. Candidates (also UNVERIFIED until checked): jonathandinu/face-parsing, skytnt/anime-seg. |
| selfie_multiclass_256x256.tflite (16,371,837 bytes, sha256 `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`) | Apache-2.0, explicitly stated in [Google model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Multiclass%20Segmentation.pdf) | funded segmentation tool; local mask quality unqualified | Primary `D:\ByrdHouse\models\segmentation`; small runtime copy under configured ComfyUI/models/segmentation | Restore the existing face-zone helper's six-class CPU segmenter from official float32 version 1 (Google generation `1682480015568195`), using the already installed MediaPipe 1.0.1. No package/runtime reinstall. Not a pixel-perfect or identity model; anime fallback remains private. Rollback: leave weights inert and disable candidate preparation; preserve approved assets. |
| photomaker-v1.bin (890.8 MB, TencentARC) | Apache-2.0 | blocked on 8 GB | `ComfyUI/models/photomaker` | Needs ≥11 GB VRAM; retained as disabled future-hardware option. PhotoMaker V2 rejected (InsightFace + VRAM). |

## Identity LoRAs (local, never committed)

### Current Windows native Wan 2.2 qualification — 2026-10-04

The official [Comfy-Org Wan 2.2 repackaged model](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged)
is pinned at `ee6f4a40737a995bf5818954cfce6d59443b0f04`. Its model card
declares Apache-2.0. The existing ComfyUI core supplies inference; no CUDA
wheel, new custom node, training package, or FreeVideo installer is added.
These are native-model **local qualification** files, not the older proposed
14B Q4 dual-stage lane. Exact download records and hash verification are saved
in `D:\ByrdHouse\external\workflows\comfy-wan22-5b\sources.json`.

| File | Bytes | Expected SHA-256 | Destination / rollback |
|---|---:|---|---|
| `wan2.2_ti2v_5B_fp16.safetensors` | 9,999,658,848 | `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e` | `D:\ByrdHouse\models\diffusion_models`; inert unless the Wan scene-preview route is used. |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | 6,735,906,897 | `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68` | `D:\ByrdHouse\models\text_encoders`; storage FP8 is not a claim of native Radeon FP8 acceleration. |
| `wan2.2_vae.safetensors` | 1,409,400,960 | `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156` | `D:\ByrdHouse\models\vae`; decode uses the installed tiled VAE node. |

Deployment backup: `D:\ByrdHouse\backups\2026-10-04-wan22-studio`.
Restore the saved Studio files to disable the new route, preserving the queue,
approved artwork, and all model/output files. Real AMD result and limits belong
in the dated native-Wan review, not inferred from the model card.

All under `artifacts/lora/candidates/` on BYRD-GAMING — versioned filenames,
**never overwritten**, all currently *private preview / rejected* per the run
table in `docs/IMAGE_GENERATION_STATE.md`. No identity LoRA is approved for
any lane until visual + license gates pass. Rollback: files are inert unless
a recipe references them.

## Pending P1 lab installs (rows required BEFORE install)

### H3 / FreeVideo research candidate — 2026-10-04 follow-up

No H3 weight, node or installer is installed in this deployment. FreeVideo
code is Apache-2.0, but its H3 model/derivative license is separate. The
publisher's standard agreement at revision
`42ed227ee7df40d41602854ae760620d6eb651fe` expressly excludes the US, EU, UK
and Republic of Korea and describes separate licensing for those territories.
The inspected VDN derivative license is identical. No separate authorization
is recorded here. Do not treat a quantization repository's Apache declaration
as replacing the underlying model terms. Source/license hashes and different
AMD candidates are saved in
[the FreeVideo follow-up](reviews/2026-10-04-freevideo-follow-up.md).
This is an inert research entry, not approval or a download manifest.

ComfyUI-RMBG (light models only — INSPYRENET/BEN2 class, no SAM ViT-H),
comfyui_facetools, ComfyUI-Forbidden-Vision, ComfyUI_FaceShaper (benchmark
branch), Wan 2.2 Q4 dual-stage (P4 video lab). Each needs: repo URL + pinned
commit SHA, code license, model licenses + sizes + hashes, Python/Torch/CUDA
compatibility, conflicts, and uninstall steps recorded here first.
