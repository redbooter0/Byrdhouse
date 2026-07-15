# FACE LAB — local face swap + identity LoRA (the belt's face engine)

*ByrdHouse can now IMAGINE an image (recipes → ComfyUI) and SWAP a face onto any
image (ReActor → ComfyUI) — 100% local on BYRD-GAMING. MINI/router/dashboard are
optional for all of this; the function itself runs straight against ComfyUI.*

## The one test that matters (run on the GAMING PC)

Open **Claude Code on BYRD-GAMING** and paste this — it proves the actual
function on real hardware, end to end:

```
Pull the branch claude/local-face-swap-lora-68v0sq in the ByrdHouse repo and sync
E:\ByrdHouse from it. Then, per docs/FACE_LAB.md: (1) run facelab_preflight.py and
install anything it says is missing, (2) run collect-training-images.ps1 to move my
~300 generated images into the carey_face dataset and show me the manifest, (3) run
train-lora.ps1 -DryRun and show me the exact training command before starting the
real run, (4) after training, run a REAL face swap of my face onto my gojo, vegeta
and luffy images with blend 0.35 using facelab_preflight.py --run, and show me the
output files. My rules: never exceed 7200MB VRAM, use at most 16-18 CPU threads,
never overwrite an existing LoRA file.
```

Or by hand, in order (PowerShell on GAMING, ComfyUI running):

```powershell
# 0. is the face-swap function ready on THIS machine? (told exactly what's missing)
python scripts\facelab_preflight.py

# 1. find the ~300 generated images and move them into the dataset
powershell -ExecutionPolicy Bypass -File scripts\collect-training-images.ps1 -Name carey_face -Newest 300

# 2. train a NEW LoRA file (auto-versions: carey_face_v2, _v3... never overwrites)
powershell -ExecutionPolicy Bypass -File scripts\train-lora.ps1 -Dataset carey_face

# 3. THE PROOF — real swap onto a real picture (MINI can be off; no router needed)
python scripts\facelab_preflight.py --run E:\path\to\gojo.png --blend 0.35
python scripts\facelab_preflight.py --run E:\path\to\vegeta.png --blend 0.35
python scripts\facelab_preflight.py --run E:\path\to\luffy.png --blend 0.35
```

Outputs land in `artifacts\sandbox\<month>\` with sidecar cards, like every belt
artifact. When MINI is back on, the same swaps run as `image.faceswap` jobs from
the dashboard's **Face Swap** panel (Create tab) with auto-judge + approval queue.

## One-time install on GAMING (what preflight will ask for)

1. **ReActor node pack**: ComfyUI Manager → search *ReActor* → Install → restart.
   (manual: `git clone https://github.com/Gourieff/ComfyUI-ReActor` into
   `ComfyUI\custom_nodes`, run its `install.bat`)
2. **Models** (see docs/MODELS.md → Face Lab): `inswapper_128.onnx` →
   `ComfyUI\models\insightface`; `GFPGANv1.4.pth` →
   `ComfyUI\models\facerestore_models`; `buffalo_l` downloads itself on first use.
3. **Face photos**: 5–7 clear photos in `profiles\me\references\` (front.jpg first).
4. **kohya sd-scripts** for training — `train-lora.ps1` prints the exact install
   if missing. If yesterday's training tool is already somewhere on disk, run
   `find-codex-work.ps1` to locate it and set `training.sd_scripts_dir` in the config.

## How the swap actually works (the idea, reverse-engineered)

- **The "outline and mask from the CPU" you saw is normal.** ReActor's face
  detection/alignment (insightface + onnxruntime) runs on **CPU** by default;
  only the diffusion side uses the GPU. Detection finds the face box + landmarks
  (the outline), inswapper_128 replaces identity at 128px, then a restore model
  (GFPGAN) sharpens the swapped face.
- **Why raw swaps look pasted-on for Gojo/Vegeta/Luffy:** inswapper produces a
  *photoreal* face; dropped onto anime linework the styles clash. The fix (what
  the pros do) is a **two-pass**: swap first, then a **low-denoise img2img pass
  (0.3–0.45) with an anime checkpoint** so the face melts into the art style —
  that is `workflows/reactor_faceswap_blend_api.json`, driven by
  `payload.style_blend`. Attach your identity LoRA to the blend pass so the
  face stays YOU through the diffusion.
- **Two routes, both in the belt now:**
  - `image.faceswap` — put your face on an EXISTING picture (their Gojo art).
  - `me_as_character` recipe — GENERATE you as the character from scratch
    (IP-Adapter FaceID + anime checkpoint + your LoRA). Often the better look,
    because everything is drawn in one style from the start.
- **8GB 3070 budget** (founder rule, enforced in `train-lora.ps1` + config
  `training`): ≤7200MB VRAM, 16–18 of 20 CPU threads. Training uses batch 1 +
  gradient checkpointing + Adafactor + bf16 + UNet-only + latents cached to disk.
- **Upgrades to try later** (not installed now): PuLID / InstantID give
  higher-fidelity identity transfer during generation but are heavier on VRAM;
  the LoRA + FaceID + swap combo is the right fit for 8GB.

## Honesty note (license)

`inswapper_128.onnx` (insightface) is **research/non-commercial**. For personal
experiments, fine. For monetized thumbnails, prefer the **LoRA + IP-Adapter
FaceID route** (`me_as_character`) — your own likeness, trained locally on your
own images, no license question.

## Where Codex left off

Codex's local files (sessions, AGENTS.md, uncommitted work, yesterday's training
setup) live on the PC — run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\find-codex-work.ps1
```

Its **pushed** trail is on GitHub, never merged into main (review before reusing —
main has since moved past most of it via PRs #18–#22):

| branch | last commit | what's in it |
|---|---|---|
| `fix/operator-endpoints-and-studio-config` | 2026-07-11 16:41 | **Luna Pulse job supervision**, studio endpoint fixes, LM Studio preserve + auth caveat, `integrations/` MCP configs, operator endpoint validators |
| `fix/recipe-contract-safety` | 2026-07-11 16:39 | recipe slot contract enforced at the queue boundary |
| `fix/belt-contract-and-private-operator` | 2026-07-11 15:36 | belt contract hardening + private operator MCP |
| `fix/dashboard-draft-persistence` | 2026-07-11 | draft-persistence variant (superseded by merged PRs) |
| `agent/byrdhouse-gaming-windows-safe` | 2026-07-10 | gaming U0 worker/judge flow (superseded by merged U0 work) |
