# ByrdHouse Performance — squeezing both machines

*BYRD-GAMING: i9-10850K · 32GB DDR4 · RTX 3070 8GB. BYRD-MINI: 8GB RAM, no GPU.*

## BYRD-GAMING (the muscle)

Run once (admin): `powershell -ExecutionPolicy Bypass -File scripts\tune-gaming.ps1`
— sets the High Performance power plan and reports GPU/RAM/XMP posture.

**The belt already does the big things right:** GPU modes are exclusive (the
3070 is never split between the LLM and ComfyUI), the worker unloads models
before IMAGE mode and verifies VRAM with nvidia-smi, and `_lms_load` now loads
with `--gpu max` so the whole model rides the 3070 instead of spilling to CPU.

Manual checklist (one-time):
1. **XMP in BIOS** — DDR4 at 2133 MT/s is leaving free bandwidth on the table;
   XMP to its rated speed helps SDXL's VAE/CPU stages. `tune-gaming.ps1` tells
   you what it's currently running at.
2. **LM Studio model settings** — GPU offload MAX, context 8192 (chat/judging
   never needs more; longer contexts eat VRAM), "keep model in memory" OFF so
   IMAGE-mode unloads actually free VRAM.
3. **Windows** — Game Mode ON, Hardware-accelerated GPU scheduling ON,
   pagefile on the NVMe (SDXL batch 4 peaks ~14GB system RAM; 32GB is
   comfortable, but a slow pagefile still hurts spikes).
4. **ComfyUI** — SDXL at the recipe defaults (1152x768–1344x768, batch 4,
   30 steps) fits the 8GB card. If a future workflow OOMs, drop batch to 2
   before dropping resolution.

Model picks that respect 8GB VRAM:
- **Operator/judge (one at a time):** Qwen-VL 4B-class judges fast; a 7–9B
  Q4 chat model fits fully offloaded. Bigger than ~9B Q4 starts spilling.
- **Checkpoints:** any SDXL (~6.5GB) — one loaded at a time is the rule anyway.

## BYRD-MINI (8GB RAM — small but always on)

Until the RAM upgrade, the mini can still run a **small CPU model** and make
chat always-on (the 3070 goes silent during image generation; the mini never
does):

1. Install LM Studio on the mini (or llama.cpp server).
2. Load a ~2GB Q4 small model — pick one: **Qwen2.5-3B-Instruct Q4_K_M**,
   **Llama-3.2-3B-Instruct Q4**, or **Gemma-2-2B-it Q4** (all leave ~5GB for
   the router/Qdrant; do NOT go above 4B-class on 8GB).
3. Server tab → serve on port 1234 (local is fine — the router lives here too).
4. In `D:\ByrdHouse\byrdhouse.config.json`:
   `"lmstudio_fallback": "http://localhost:1234/v1"` → restart the router.

The `/chat` endpoint tries GAMING first (big model, full quality) and falls
back to the mini's small model whenever GAMING is mid-generation or off.
The dashboard shows which model answered.

After the RAM upgrade (16GB+), the same slot fits a 7–8B Q4 and the fallback
stops feeling like a fallback.
