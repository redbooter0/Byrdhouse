# Models — the license-clear custom kit (game thumbnails)

Custom Hugging Face fine-tunes, not base models. All checkpoints below are
**`openrail++`** (CreativeML Open RAIL++-M) — **commercial use is permitted**
(use-based restrictions only), which matters for a money-gated channel. Avoid
non-commercial models (e.g. Juggernaut XI is `cc-by-nc-nd` — do not ship with it).

## The truth about "the game I wanted"
A base/fine-tuned checkpoint nails a **style**, never copyrighted **IP** — it will
not draw a screen-accurate Pikachu from words alone. Fidelity to a specific game
comes from a **real reference** (the `game_ref` recipe + an uploaded screenshot →
IP-Adapter) or a per-game LoRA. **Style model + your reference screenshot together
is the winning combo.** Pick the checkpoint by the game's *style family*:

| Game style family | Custom checkpoint (Hugging Face) | License | Use for |
|---|---|---|---|
| **Anime / stylized** | [cagliostrolab/animagine-xl-4.0](https://hf.co/cagliostrolab/animagine-xl-4.0) | openrail++ | Pokémon, Palworld creatures, Fortnite, Genshin, most Nintendo/anime titles |
| **Photoreal** | [SG161222/RealVisXL_V5.0](https://hf.co/SG161222/RealVisXL_V5.0) | openrail++ | GTA, Call of Duty, NBA 2K, sports, realistic shooters |
| **Versatile / painterly** | [Lykon/dreamshaper-xl-1-0](https://hf.co/Lykon/dreamshaper-xl-1-0) | openrail++ | splash art, fantasy, "does everything" default |
| **Fast (4-step)** | [Lykon/dreamshaper-xl-lightning](https://hf.co/Lykon/dreamshaper-xl-lightning) | openrail++ | quick drafts on the 3070 (lower steps in the recipe) |

Baseline photoreal stays [RunDiffusion/Juggernaut-XL-v9](https://hf.co/RunDiffusion/Juggernaut-XL-v9)
(openrail++, the current recipe default) — keep it; add the others alongside.

## Reference engine (required for game_ref / IP-Adapter)
Download into ComfyUI and install the node pack — this is what makes a real
screenshot steer the look:
- Models: [h94/IP-Adapter](https://hf.co/h94/IP-Adapter) → `sdxl_models/` (the
  `ip-adapter-plus_sdxl_vit-h` weights + the `image_encoder/` CLIP-ViT-H).
- Nodes: `ComfyUI_IPAdapter_plus` (cubiq) in `ComfyUI/custom_nodes`.
- Graph: `workflows/sdxl_ipadapter_api.json` (already in the repo); recipe:
  `recipes/game_ref.v1.json`.

## How to install a checkpoint
1. Download the `.safetensors` into `E:/ByrdHouse/Generators/ComfyUI/models/checkpoints`.
2. The belt resolves checkpoints by loose name with a recorded fallback
   (`byrdimage.resolve_checkpoint`), so a close name matches — but exact is safest.
3. Use it per job via the dashboard **Checkpoint** field, or set a recipe's
   `defaults.checkpoint`. (Freeze note: `DECISIONS.md` 2026-07-08 froze new model
   downloads — adding these is a founder decision to lift it for licensed
   production models.)

## Suggested mapping the bot can read
BYRD (via the memory/files tools) can use this table to auto-pick a checkpoint:
- anime/stylized game → `animagine-xl-4.0`
- realistic game → `RealVisXL_V5.0`
- unsure / splash art → `dreamshaper-xl` (or `-lightning` for speed)
- exact game look wanted → any of the above **+ `game_ref` with a real reference**
