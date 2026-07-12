# ByrdHouse Flux2 Klein Style Transfer + Upscale

This package turns the uploaded workflow into a reusable ByrdHouse operator workflow for **BYRD-GAMING / RTX 3070 8GB**.

## Use this order

1. Load `ByrdHouse_Flux2_Klein_3070_SAFE_FIRST_RUN.json` first.
2. Select a subject image in **REFERENCE 1 — SUBJECT / POSE / COMPOSITION**.
3. Select a costume or style image in **REFERENCE 2 — COSTUME / STYLE / MATERIALS**.
4. Edit **BYRDHOUSE TRANSFORMATION PROMPT** only when the job needs special instructions.
5. Queue once. The raw result saves under `output/ByrdHouse/Flux2Klein/raw/`.
6. After the safe workflow succeeds, load `ByrdHouse_Flux2_Klein_3070_PRODUCTION_ALL_IN_ONE.json` to generate and create a 4x Remacri upscale in the same queue.

## What was changed

- Replaced the example character-specific prompt with a general subject + costume transfer prompt.
- Clearly labeled Reference 1 and Reference 2.
- Added persistent `SaveImage` output for the raw generation.
- Added persistent `SaveImage` output for the 4x production upscale.
- Activated the lighter `4x_foolhardy_Remacri.pth` branch in the production file.
- Kept SeedVR2 present but bypassed by default because its 7B upscaler is the risky branch on an RTX 3070.
- Preserved the visual comparison workspace and the original full node canvas.

## Required model filenames

- `flux-2-klein-9b-fp8.safetensors`
- `qwen_3_8b_fp8mixed.safetensors`
- `flux2-vae.safetensors`
- `4x_foolhardy_Remacri.pth` for the production all-in-one file

SeedVR2 models are optional and intentionally bypassed.

## Required node packs

- ComfyUI-Use-Everywhere (`GetNode`, `SetNode`)
- rgthree-comfy
- comfyui_xiser_nodes

Optional:

- seedvr2_videoupscaler

Use ComfyUI Manager's missing-node installer after loading the workflow. Restart ComfyUI after installing node packs.

## ByrdHouse locations

Gaming workflow destination:

`E:\ByrdHouse\Images\Workflows\`

ComfyUI root used by the current ByrdHouse setup:

`E:\ByrdHouse\Generators\ComfyUI\`

## API / byrdimage-full handoff

The uploaded JSON is the editable **ComfyUI UI graph** format. ByrdHouse's `/prompt` submission requires **API-format JSON**.

After the SAFE file completes one successful queue:

1. Open ComfyUI settings and enable developer options if `Save (API Format)` is hidden.
2. Save the loaded workflow as API format.
3. Name it `byrdhouse_flux2_klein_api_v1.json`.
4. Put it in `E:\ByrdHouse\Images\Workflows\` and sync the same file to `D:\ByrdHouse\Images\Workflows\` on BYRD-MINI.
5. Use `byrdhouse_flux2_klein_api_adapter.py` to inject the prompt and two reference filenames without hardcoding node IDs.

The adapter looks for the node titles embedded in the API export, so keep the prepared titles intact.

## 3070 operating rule

Run `use-image-mode.ps1` first so LM Studio unloads the operator model and releases VRAM. Start with the SAFE file. Do not enable SeedVR2 until the Flux2 generation and Remacri upscale have both passed independently.
