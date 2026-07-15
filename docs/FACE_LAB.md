# FACE LAB — local face swap + identity LoRA (the belt's face engine)

*ByrdHouse can now IMAGINE an image (recipes → ComfyUI) and SWAP a face onto any
image — 100% local on BYRD-GAMING. MINI/router/dashboard are optional for all of
this; the functions run straight against ComfyUI.*

## The reconciled lane map (2026-07-15 — both agents' work, one belt)

| Tier | Lane | Job / recipe | Docs |
|---|---|---|---|
| **Quality (funded/public)** | CPU-first mesh seed: 478-pt mesh + semantic zone + reference warp + optional low-denoise cleanup, SD1.5 Meina + owner LoRA (`careybh person`) | recipe `anime_face_zone_edit@1` (runner `face_zone_identity_edit`) | `docs/FACE_ZONE_EDIT_WORKFLOW.md`, state in `docs/IMAGE_GENERATION_STATE.md` |
| **Fast daily** | Preview (CPU mask, approvable) → Zone (mask-bounded edit) → Auto (FaceDetailer detect+redraw) | `image.faceswap` routes `preview`/mask/`auto` | this file |
| **Private experiments only** | ReActor direct swap/blend, IP-Adapter FaceID (`me_as_character`) — InsightFace research license, excluded from the funded lane | `image.faceswap` swap route | policy in `AGENTS.md` + `docs/MODELS.md` |

Read `docs/IMAGE_GENERATION_STATE.md` before touching the quality lane — it is
the live handoff (current verdict: architecture proven, no LoRA candidate
approved yet; CPU-only seed finish preferred on hard targets).

## The one test that matters (run on the GAMING PC)

Open **Claude Code on BYRD-GAMING** and paste this — it proves the actual
function on real hardware, end to end:

```
FIRST, protect Codex's work: run scripts\find-codex-work.ps1, and if the ByrdHouse
repo clone has uncommitted changes (Codex was editing byrdimage.py edit_face_zone,
byrdfacezone.py and integration tests locally), commit them to a branch named
codex/face-zone-wip and push it BEFORE anything else. Only then pull the branch
claude/local-face-swap-lora-68v0sq and sync E:\ByrdHouse from it. Then, per
docs/FACE_LAB.md: (1) run facelab_preflight.py and install anything it says is
missing, (2) run collect-training-images.ps1 to move my ~300 generated images
(profiles\me\references\generated_real_skit_scenes and the other generated_*
folders — the script searches those) into the carey_face dataset and show me the
manifest, (3) locate Codex's already-trained LoRA (37.9MB safetensors from
2026-07-14, checkpoints at steps 400/800/1200/1600 — step 400 gated best) and keep
every file, then run train-lora.ps1 -DryRun and show me the exact command before
starting the real run — it must create a NEW versioned file, (4) run REAL swaps of
my face onto my gojo, vegeta, luffy and link images: the AUTO route first
(facelab_preflight.py --run <image> --route auto --lora <the LoRA>) — that is the
daily driver — then the ReActor blend route (blend 0.35) and, where auto detection
misses a stylized face, the zone route with a byrdfacezone or hand mask at denoise
0.7. Show me the output files side by side. My rules: never exceed 7200MB VRAM,
use at most 16-18 CPU threads, never overwrite an existing LoRA file.
```

Or by hand, in order (PowerShell on GAMING, ComfyUI running):

```powershell
# 0. is the face-swap function ready on THIS machine? (told exactly what's missing)
python scripts\facelab_preflight.py

# 1. find the ~300 generated images and move them into the dataset
powershell -ExecutionPolicy Bypass -File scripts\collect-training-images.ps1 -Name carey_face -Newest 300

# 2. train a NEW LoRA file (auto-versions: carey_face_v2, _v3... never overwrites)
powershell -ExecutionPolicy Bypass -File scripts\train-lora.ps1 -Dataset carey_face

# 3. THE PROOF — the daily driver (AUTO route): upload any character, done.
#    Detector finds the face, masks it, redraws it as YOU in the picture's own
#    art style. Works on Gojo/Vegeta/Luffy/Link. MINI can be off.
python scripts\facelab_preflight.py --run E:\path\to\gojo.png   --route auto --lora carey_face
python scripts\facelab_preflight.py --run E:\path\to\vegeta.png --route auto --lora carey_face
python scripts\facelab_preflight.py --run E:\path\to\luffy.png  --route auto --lora carey_face
python scripts\facelab_preflight.py --run E:\path\to\link.png   --route auto --lora carey_face

# 3a. comparison — ReActor direct swap + anime blend
python scripts\facelab_preflight.py --run E:\path\to\gojo.png --blend 0.35

# 3b. CPU zone preview (inspect the mask BEFORE any GPU): saves _overlay + _mask
python scripts\byrdimage.py --swap-target E:\path\to\link.png --preview --purpose "link zone preview"

# 3c. zone route (the founder lane): GPU edits ONLY inside the mask; identity
#     from the trained LoRA + notes. Mask from the preview above, byrdfacezone.py,
#     or hand-drawn (white = change zone).
python scripts\byrdimage.py --swap-target E:\path\to\gojo.png --swap-mask E:\path\to\gojo_mask.png --lora carey_face --prompt "Gojo Satoru, cel shading, Jujutsu Kaisen style" --purpose "gojo zone edit"
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
- **The CPU pre-step, formalized** (Codex's rule: *the GPU must not decide the
  mask*): the **Preview route** (`route:"preview"`, CLI `--preview`) runs ONLY
  detection — seconds, no checkpoint, works in any GPU mode — and archives two
  artifacts: the **zone overlay** (the mask glowing on the character, failures
  inspectable before the GPU spends a step) and the **soft mask** itself. Approve
  the mask in the gallery, then paste its artifact id into the Face Swap panel's
  "zone from a preview" box (or `mask_artifact` in the payload) and the GPU edits
  exactly that zone. Original, overlay, mask, result, sidecar card — all kept.
- **Four execution routes, all in the belt now** (all `image.faceswap` except the last):
  - **AUTO (the daily driver, dashboard default)**: detector finds the
    character's face → masks it → redraws it as YOU (identity LoRA + notes) in
    the picture's own art style → composites back. One upload, one step.
    `payload.route="auto"`, CLI `--auto`, preflight `--route auto`.
  - **Zone**: same redraw but the mask is YOURS (`mask_artifact`/`--swap-mask`,
    white = change) — the fallback when a very stylized face isn't detected,
    and the lane for byrdfacezone mesh-seed cleanups.
  - **Direct swap (+ blend)**: ReActor puts your photo's face on; `style_blend`
    0.35 melts it into anime linework.
  - `me_as_character` recipe — GENERATE you as the character from scratch
    (IP-Adapter FaceID + anime checkpoint + your LoRA). Often the better look,
    because everything is drawn in one style from the start.
- **Auto-route tuning**: the detector (`image.faceswap_detector`, default
  `bbox/face_yolov8m.pt`) handles most anime faces; if a face is missed, lower
  `bbox_threshold` in `workflows/facezone_auto_api.json` (0.5 → 0.3) or use the
  zone route. Put your LoRA trigger word (the dataset name, e.g. `carey_face`)
  in the notes/prompt so the redraw pulls your identity hard.
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

## Where Codex left off (recovered from its sessions, 2026-07-14)

Two Codex sessions did the work. **"These are my references"** built the dataset:
300 audited scene images (IDs 1–300 in 100-batches, unique hashes, generated from
real photos only) via `build-100-photoreal-skit-manifest.ps1` and a second
100-brand animation catalog builder, landing in
`profiles\me\references\generated_real_skit_scenes\` (+ siblings), plus 10 real
photos `me_photo_23.jpg`–`me_photo_32.jpg` in the references root.

**"Review targets folder"** built the swap engine and got real results:

- **A LoRA was already trained**: 1600/1600 steps in 19:55, final loss 0.118,
  37.9MB file, with saved checkpoints at 400/800/1200/1600. Its gate testing found
  **step 400 the most personal**; 1200/1600 drifted generic ("too much jaw beard").
  FIND AND KEEP THESE FILES — `train-lora.ps1` versions new runs so they can never
  be overwritten.
- **The breakthrough**: CPU **mesh-to-mesh transfer** (`byrdfacezone.py` + an
  `edit_face_zone` addition inside its local copy of `byrdimage.py` — UNCOMMITTED
  on the PC). It warps the 478-point face grid into the character's pose (Gojo,
  Vegeta, Luffy each matched to their franchise style reference), keeping
  blindfold/hair/collar target-authentic. The Gojo and Vegeta seeds looked RIGHT.
- **Where it stopped**: the GPU cleanup pass. Too weak → source lighting kept +
  jaw/ear seam; ~0.9 denoise → LoRA takes over with artifacts. It was raising
  cleanup denoise into the middle corridor and planning semantic hair masking.
  That corridor is exactly what the belt's **zone route** runs (default 0.7,
  clamped 0.3–0.9, `image.faceswap` with a mask).
- **The founder rule it was told to make permanent** (now the belt's contract):
  *upload → CPU face outline → visible edit-zone overlay → approved soft mask →
  GPU executes only inside that zone → keep original, outline, mask, result +
  sidecar card.* v1 in the belt: supply the mask (`mask_artifact`/`mask_path` or
  the dashboard's Edit-zone field); next rung: auto landmark mask + approval
  overlay endpoint (ComfyUI already has the landmark tooling — it only needs the
  small Comfy-Org face-landmarker model Codex was fetching).

Locate all of it (sessions, byrdfacezone.py, the trained LoRA, uncommitted repo
changes) with:

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
