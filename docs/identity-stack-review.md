# Identity Stack Review — research registry dispositions

Decision record for the repositories researched in the 2026-07-15 handoff
(§10), reconciled against live ByrdHouse lanes and licensing rules. These are
**implementation guidance, not proof a repo works on the live machine** — every
Adopt/Test requires a pinned commit, a manifest row
(`docs/model-license-manifest.md`), an isolated lab, and a benchmark before
promotion. Nothing here is installed yet unless the live docs say so.

## Identity Stack V1 (P1) — install sequentially, benchmark decides

| Order | Component | Disposition | Notes |
|---|---|---|---|
| 1 | ComfyUI-RMBG (1038lab) | Adopt selectively | Segmentation/mask engine: person/face/hair/clothes. Start with light models (INSPYRENET/BEN2 class); **no SAM ViT-H / SAM2 Large** on the 8 GB card. |
| 2 | comfyui_facetools (dchatel) | Adopt/test | Prove detect → align → crop → **unchanged warp-back** with zero drift before any swap sits on it. |
| 3 | ComfyUI-ReActor (Gourieff) | Already live | Direct-swap baseline (branch A). Private lane only — InsightFace non-commercial. |
| 4 | ComfyUI-Forbidden-Vision | Adopt/test | Post-swap crop-based fixer: 512/768 crops, batch 1, 8–12 steps, denoise ~0.20–0.35, pre-upscale off, tiled VAE if needed. Expected practical winner is branch D (facetools → ReActor → FV → warp-back), but the benchmark decides. |
| 5 | ComfyUI_FaceShaper | Benchmark only | Experimental geometry branch (C) after baseline works. |
| 6 | ComfyUI-Fayens | Benchmark only | Optional color/mask utilities if a measured gap remains. |
| 7 | ComfyUI_InfiniteYou (ByteDance) | Defer | 24 GB+ generative identity; also research-constrained licensing. Not for the 3070. |

Benchmark = the five-target scorecard in `docs/identity-benchmark.md`, run via
`scripts/identity-benchmark.ps1`.

## Rejected (do not install)

| Project | Reason |
|---|---|
| ComfyUI-InstaSwap | Redundant with ReActor; model restrictions; dependency risk. |
| ComfyUI-DeepFuze | README incompatibility, old CUDA stack risk. |
| comfyui_face_parsing (Ryuukeisyou) | Only if RMBG/facetools masks prove insufficient — OpenCV dep risk, overlap. |
| Wan 2.1 I2V workflow (blongsta); wy67576 8GB workflow collection | Disconnected/placeholder workflow JSON — not evidence. |
| LmStudioToCursor; LM Studio unlocked backend | Redundant proxy / legacy patch; exposure risk. |
| EZhou 8GB LoRA script | Generic LLM PEFT trainer, not an image identity trainer. |
| Unreal NVIDIA GameWorks fork; NVIDIA RTX AI Toolkit | Obsolete UE4 fork / officially deprecated. |
| Leaked Claude Code mirror | **Hard reject** — proprietary leaked source; never clone, copy, or study. |

## Adopt / extract / defer (other lanes)

| Project | Disposition | Lane |
|---|---|---|
| ComfyUI-Lora-Manager (willmiao) | Adopt/test | LoRA/checkpoint/recipe management (Identity Lab first). |
| duck3244/lora-sd-custom | Candidate, isolated env | 8 GB SD1.5 image-LoRA lab. Incumbent stays `train-carey-meina-lora.ps1` (sd-scripts) — eight benchmarked runs of history; candidate must beat it on the same fixed prompts. |
| Wan 2.2 Q4 dual-stage (v8turbo420517-prog) | Adopt/test (P4) | Highest-priority isolated video benchmark; reproduce exactly before customizing. |
| Genna/FLOAT Background Lock | Adapt pattern (P4) | Foreground-only animation over untouched background + outside-mask distortion score. |
| ComfyFlow (wy67576) | Extract | API/CLI patterns only — ByrdHouse stays the canonical queue. |
| RyanOnTheInside; Isi-dev animation nodes | Defer | After core video works. |
| IndexTTS2/2.5 (official, not the wrapper) | Defer (P5) | Voice lab with consent package + duration control. |
| OpenCode-LM Studio (agustif) | Adopt/test now (P3) | Pinned version, isolated config, read-only first. |
| ComfyUI-LM-Studio (gabe-init) | Adopt later | Vision analysis/prompt rewriting; unload before diffusion. |
| AionUi; JoyBoy; Z-Fusion | UX benchmarks only | Study patterns (Doctor, queues, permissions, before/after viewer); never replace ByrdHouse. |
| TextGen (oobabooga) | Standby | Redundant with LM Studio today. |
| LocalMultiAgent; qwen3_mcp; Codex proxy; AgentWebSearch-MCP | Extract/sandbox | Tool schemas + routing patterns; permission surfaces too broad for production. |
| NVIDIA/skills | Adopt selectively | Model for a governed ByrdHouse skill catalog (versioned dirs, manifest, tests, provenance, rollback). |
| NVIDIA SDXL Workbench / GenAI Creator Toolkit | Future/high-VRAM reference | Not for the 3070. |
| dataleveling IPAdapter-FaceIDv2 workflow | Benchmark reference, private lane | FaceID = InsightFace dependency; never funded lane. |
| Clarity refiners UI | Benchmark | Creative upscale with before/after identity scoring only. |
| Deno custom nodes | Adopt selectively | Multi-reference loading/comparison utilities. |
| Flux Continuum / All-in-One FluxDev / FLUX-under-8GB | Extract/reference | Routing + lazy-load ideas only; no wholesale adoption on 8 GB. |
| Flux2 Klein workflow (video + JSON) | Already integrated | Lives under `workflows/flux2_klein/` with install/patch scripts. |
| PyLittle | Research | Memory/offload runtime ideas for a future scheduler. |
