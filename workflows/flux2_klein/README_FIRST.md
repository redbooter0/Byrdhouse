# ByrdHouse Flux2 Klein — Real to Gaming Character

Converts a real photograph into a recognizable video-game character using Flux2 Klein dual-reference style transfer on **BYRD-GAMING / RTX 3070 8GB**.

## Quick Start

1. Run `use-image-mode.ps1` to free VRAM.
2. Load `safe_first_run.json` in ComfyUI.
3. Set **REFERENCE 1** to a clear photograph of the subject.
4. Set **REFERENCE 2** to a game-character reference matching the desired style.
5. Queue once. Output saves to `output/ByrdHouse/Flux2Klein/gaming/`.

## Styles

Paste the style suffix into the prompt after the base transformation text, or use the API adapter's `--style` flag.

| Style | Look |
|-------|------|
| `AAA` | Semi-realistic PBR rendering (Horizon, God of War) |
| `HERO` | Stylized hero-shooter (Overwatch, Valorant) |
| `FANTASY` | High-fantasy RPG (Baldur's Gate 3, Elder Scrolls) |
| `SCIFI` | Sci-fi operative (Mass Effect, Halo) |
| `CEL_SHADED` | Cel-shaded cartoon (Genshin Impact, BotW) |
| `GRITTY` | Dark action (The Last of Us, Dark Souls) |
| `SPLASH_ART` | Promotional splash art (League of Legends) |

Full prompt text for each style is in `recipes/real_to_gaming.v1.json`.

## Intensity Profiles

| Profile | Guidance | Ref1 MP | Ref2 MP | Effect |
|---------|----------|---------|---------|--------|
| `IDENTITY_LOCK` | 0.7 | 3 | 2 | Maximum likeness, subtle game conversion |
| `BALANCED_GAMING` | 0.9 | 2 | 3 | Strong identity + obvious game style (default) |
| `FULL_CHARACTER_REDESIGN` | 1.1 | 2 | 4 | Recognizable but dramatic game-world redesign |

Adjust in the UI by changing the GUIDANCE slider and the megapixel values on the two ImageScaleToTotalPixels nodes.

## Reference Image Guidelines

**Reference 1 — Subject (identity anchor):**
- Clear real photograph with visible face
- Adequate lighting, minimal motion blur
- Chest-up, waist-up, or full-body framing
- Unobstructed hairstyle and clothing silhouette

**Reference 2 — Gaming Target (style anchor):**
- Clean game-character screenshot or promotional render
- Matching the desired visual genre
- Should define style and materials, not replace identity

## API Automation

```powershell
python api_adapter.py `
  --workflow real_to_gaming_api_v1.json `
  --output patched.json `
  --reference-1 carey_photo.png `
  --reference-2 game_hero_ref.png `
  --style FANTASY `
  --intensity BALANCED_GAMING
```

Or provide a fully custom prompt:

```powershell
python api_adapter.py `
  --workflow real_to_gaming_api_v1.json `
  --output patched.json `
  --reference-1 carey_photo.png `
  --reference-2 game_hero_ref.png `
  --prompt "Your custom transformation prompt here."
```

## API-Controllable Node IDs

| Node ID | Title | Controls |
|---------|-------|----------|
| `92:74` | BYRDHOUSE TRANSFORMATION PROMPT | Prompt text |
| `76` | REFERENCE 1 | Subject photo filename |
| `81` | REFERENCE 2 | Game-style reference filename |
| `92:63` | GUIDANCE | CFG value (0.7–1.1) |
| `113` | SEED | Integer seed (-1 = random) |
| `115` | STEPS | Step count (default 28) |
| `92:80` | REF1 SCALE | Subject megapixels (identity strength) |
| `92:85` | REF2 SCALE | Style megapixels (style strength) |
| `126` | SAVE | Output filename prefix |

## Required Models

- `flux-2-klein-9b-fp8.safetensors`
- `qwen_3_8b_fp8mixed.safetensors`
- `flux2-vae.safetensors`
- `4x_foolhardy_Remacri.pth` (for production upscale, bypassed by default)

SeedVR2 models are optional and bypassed.

## Required Node Packs

- ComfyUI-Use-Everywhere (`GetNode`, `SetNode`)
- rgthree-comfy
- comfyui_xiser_nodes

## Output Locations

- Gaming raw: `output/ByrdHouse/Flux2Klein/gaming/`
- Production upscale: `output/ByrdHouse/Flux2Klein/upscaled/` (after enabling upscale)

## 3070 Safety Rules

- Keep batch size 1.
- Keep SeedVR2 bypassed until base generation succeeds.
- Keep upscale bypassed until identity and anatomy are validated.
- Run `use-image-mode.ps1` before generating.
- Do not load LM Studio models concurrently.
