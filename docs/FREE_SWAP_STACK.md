# Free Swap Stack — the 100% free & open-source face-swap skeleton

The complete face-swap architecture with **zero paid licenses, zero
non-commercial restrictions, zero subscription anything**. Every component
below is free to download, open source, and safe to use on a monetized
channel. This is the skeleton the swap bot builds on going forward; the
research-licensed parts (ReActor/inswapper/InsightFace/FaceID) are OUT of
this stack entirely — they were never money-safe and they are why routes
kept getting gated "private only".

## Why the bot "doesn't work" today (honest diagnosis)

1. **No deployed identity LoRA exists** — every trained candidate was
   honestly rejected (docs/IMAGE_GENERATION_STATE.md), and the recipes no
   longer pretend otherwise (`lora: null`). Routes that need a LoRA
   therefore refuse.
2. **The ReActor direct-swap route is InsightFace-licensed** — private
   experiments only, never the real product.
3. **The mesh quality lane is now geometry-gated** — hard profile targets
   (Vegeta) correctly refuse instead of shipping broken warps.

So the working free path today is the **photo-anchored route**: identity
comes from your REAL photos through IP-Adapter plus-face — no LoRA, no
InsightFace, nothing restricted. As of this commit, the quality lane runs
**LoRA-free** whenever the workflow anchors identity to a photo.

## The stack (every piece: license, cost, commercial-safe)

| Component | Role | License | Cost | Money-safe output |
|---|---|---|---|---|
| ComfyUI | engine | GPL-3.0 | $0 | yes (outputs unaffected) |
| SD1.5 base / openrail++ checkpoints (animagine-xl-4.0, RealVisXL, DreamShaper — docs/MODELS.md) | image model | CreativeML OpenRAIL(+±) | $0 | yes (use-based restrictions only) |
| MediaPipe face mesh (478-pt) | CPU face detection/geometry (examiner, zones) | Apache-2.0 | $0 | yes |
| OpenCV | fallback detection, warps | Apache-2.0 | $0 | yes |
| IP-Adapter + **plus-face** weights (h94) | identity from your REAL photo (CLIP-based, NOT InsightFace) | Apache-2.0 | $0 | yes |
| ComfyUI_IPAdapter_plus nodes (cubiq) | IP-Adapter runtime | GPL-3.0 | $0 | yes |
| ControlNet canny (lllyasviel v1.1) | hold geometry while redrawing | openrail | $0 | yes |
| DifferentialDiffusion | seam-killer masked denoise | core ComfyUI | $0 | yes |
| Impact Pack + Subpack (FaceDetailer) | AUTO route detect→mask→redraw→composite | GPL-3.0 | $0 | yes |
| face_yolov8m.pt (Ultralytics) | anime-capable face detector | AGPL-3.0 | $0 | yes for local tool use¹ |
| GFPGAN v1.4 (TencentARC) | face restore | Apache-2.0 | $0 | yes |
| kohya sd-scripts | train YOUR identity LoRA from YOUR photos | Apache-2.0 | $0 | yes (your photos, your model) |
| Pillow / stdlib Python | compositing, guards, belt | PSF/MIT-class | $0 | yes |

¹ AGPL covers redistributing/hosting the *software*; using it locally as a
detector is fine. Don't build a public hosted service on it without review.

**Excluded on purpose (never install into this lane):** inswapper_128 /
InsightFace / ReActor swaps, IP-Adapter **FaceID** variants (InsightFace
dependency), PhotoMaker V2, Juggernaut XI (cc-by-nc-nd), ParseNet anime
parser (license unverified — private eval only), Meina V5.1 until its
provenance is verified.

## Skeleton pipeline (maps 1:1 onto the existing belt)

```
upload → examiner (MediaPipe, Apache) → geometry gate (fail-closed)
      → semantic zone + soft mask (CPU, reviewable)
      → REDRAW the approved zone:
          identity = IP-Adapter plus-face on your real photo   ← free TODAY
                     (+ your own LoRA later, once one passes)
          guidance = true diffdiff / canny controlnet
      → CPU composite with the guards (outside-mask proof, eye restore,
        hair over likeness, shard check) → sidecar card
```

Every stage already exists in the repo: examiner + gate (`byrdfacezone.py`,
`byrdimage.geometry_gate`), zone masks + composite guards
(`facezone_composite.py`), the photo-anchored graph
(`workflows/sd15_face_zone_ipadapter_api.json`, avenue B), the full-image
character generator (`recipes/me_as_character.v1.json` +
`workflows/sdxl_ipadapter_face_api.json`), guidance graphs (true diffdiff /
canny), and the trainer for your own LoRA (`train-lora.ps1`).

## Free install list (one-time, all $0)

Into `E:\ByrdHouse\Generators\ComfyUI`:

1. ComfyUI Manager → install **ComfyUI_IPAdapter_plus** (cubiq), **Impact
   Pack** + **Impact Subpack**; restart.
2. Models: `h94/IP-Adapter` → `ip-adapter-plus-face_sd15.safetensors` (+
   SD1.5 CLIP-ViT-H image encoder) into `models/ipadapter` +
   `models/clip_vision`; `control_v11p_sd15_canny.safetensors` into
   `models/controlnet`; GFPGANv1.4 into `models/facerestore_models`.
3. Checkpoint: one verified openrail model from docs/MODELS.md (SD1.5 base
   for the zone lane, animagine-xl-4.0 for full-image "me as character").
4. Verify: `python scripts\facelab_preflight.py` — it names anything missing.

## Run it (free lane commands)

```powershell
# full-image "me as character" (photo-anchored, works with zero LoRA):
#   dashboard -> Create -> me_as_character   (uses profiles/me/references)

# swap the face in an UPLOADED image, photo-anchored (no LoRA needed):
facelab.ps1 quality -Image "<target>" -Workflow ipadapter
#   identity photo defaults to the preset's reviewed reference; override:
#   engine.identity_photo = a real front-lit photo of you

# hard/profile targets: the gate will route you to the reviewed-mask path
facelab.ps1 examine -Image "<target>"        # see the gate's verdict first
```

## Build checklist (skeleton → working product)

- [x] License-clean identity route exists (IP-Adapter plus-face, avenue B)
- [x] LoRA made optional for photo-anchored workflows (this commit)
- [x] Geometry gate + composite guards (outside-mask proof, eye restore,
      shard rejection) — PR #26
- [ ] Hardware proof: easy target → Gojo → Vegeta through the free lane,
      results into docs/IMAGE_GENERATION_STATE.md
- [ ] Tune plus-face weight/denoise on 3 targets; record what passes
- [ ] Train + gate YOUR identity LoRA (kohya, your photos) — adds strength
      to the same lane, still $0, still yours
- [ ] Retire the ReActor private lane from daily use entirely

## Rules that keep it free

- Any new node/model needs its row in `docs/model-license-manifest.md`
  BEFORE install — license first, download second.
- Nothing non-commercial, "research only", license-unverified, or paid ever
  enters this lane. If a tutorial says "just use ReActor", the answer is no.
- Your photos and your trained LoRAs are YOURS — they never leave the
  machines and never enter git.
