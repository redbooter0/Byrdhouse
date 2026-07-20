# realistic_reactor_refine — the realistic-target identity lane

*Added 2026-07-20. Config: `configs/image/realistic_reactor_refine.json`.
Orchestrator: `scripts/realistic_reactor_refine.py`. Conductor wiring:
`scripts/byrdswap.py`.*

## Why this lane exists

The prior realistic lane (`quality_photo_anchored`) completed successfully but
preserved too much of the **target** identity and produced a broken/doubled
beard. The pipeline infrastructure was fine — the failure was identity routing,
facial-hair masking, and verification. This lane does an explicit **identity
transfer first**, then a **low-denoise cleanup that can never rebuild the target
person**, and refuses to call a completed ComfyUI job an accepted result.

## License — read this first

ReActor + `inswapper_128.onnx` + InsightFace are **non-commercial research
licenses**. Per `docs/DECISIONS.md` (2026-07-15/16) the monetized product path
is the Free Swap Stack (IP-Adapter plus-face / a trained identity LoRA). This
lane is **private-local-experiment only**; every sidecar it writes carries
`"non_commercial": true`. Do not ship its output commercially — use
`quality_photo_anchored` or a trained LoRA for that.

## Pipeline (Stages 1–5)

| Stage | What | Where |
|---|---|---|
| 1 | Rank the identity references, pick the best front-facing one | `rank_identity_references` (reuses `byrdcast_swap.choose_reference`) |
| 2 | ReActor identity transfer (`inswapper_128.onnx`) — Carey's eyes/brows/nose/cheeks/mouth/mustache/beard/sideburns/chin/jaw replace the target's; head angle, gaze, expression, lighting, scene, clothes, **scalp hair**, headwear preserved | `byrdcast_swap.run_swap` (validated `reactor_faceswap_api.json`) |
| 3 | Facial-hair-aware mask: facial hair **inside** the identity zone, scalp hair + headwear **outside**; lower-face boundary feathered without blending the old beard back | `build_facial_identity_mask` |
| 4 | LOW-denoise cleanup, **0.20–0.35, never 0.55** (0.55 can regenerate the target person); Carey's reference anchors identity, the target supplies only pose/expression/lighting/structure | `clamp_refine_denoise` |
| 5 | Verify the final vs Carey's reference set; a completed job is NOT accepted on its own | `verify_identity` |

### Stage 5 status codes

`IDENTITY_PASS` · `IDENTITY_FAIL` · `FACIAL_HAIR_FAIL` · `SEAM_FAIL` ·
`FACE_DETECTION_FAIL`. `accepted` is true only when `IDENTITY_PASS` is present
and no `*_FAIL` is. Unmeasured identity fails **closed** (never accepted
without a measured match). A rejected result is kept as evidence
(`status: rejected`), never shown as a normal draft.

## Debug artifacts (every run)

`selected_identity_reference.png`, `target_face_crop.png`,
`candidate_reactor.png` (initial ReActor), `masks/identity.png` (+ overlay),
`refined_output.png`, `identity_verification_report.json`,
`conductor_report.json`. Written under
`artifacts/<project>/realistic_reactor_refine/<jobid>/`.

## Conductor routing

`facelab run` (the conductor) auto-selects the lane for a **stable + front-facing
+ realistic** target with ReActor installed and references present:

1. `realistic_reactor_refine`  ← preferred for stable realistic faces
2. `quality_photo_anchored`    ← free/license-clean fallback (IP-Adapter plus-face)
3. `quality_lora_mesh`         ← only with an explicit `-Lora`
4. reviewed manual zone route  ← unstable/profile targets (gate refuses the mesh)

A stable realistic target is **never** sent straight into `anime_face_zone_edit`
without an identity transfer. Anime/stylized targets never get the reactor lane.

## Run it (BYRD-GAMING)

```powershell
Set-Location E:\ByrdHouse
$env:BYRDHOUSE_ROOT = "E:\ByrdHouse"

# preferred: let the conductor pick the lane
.\scripts\facelab.ps1 examine -Image "C:\Users\carey\Downloads\James_l_thumbnail_908893.jpg"
.\scripts\facelab.ps1 run     -Image "C:\Users\carey\Downloads\James_l_thumbnail_908893.jpg"

# or force this lane directly
.\scripts\facelab.ps1 reactor -Image "C:\Users\carey\Downloads\James_l_thumbnail_908893.jpg"

# decide-only (no GPU): see the plan + selected reference
.\scripts\facelab.ps1 reactor -Image "C:\Users\carey\Downloads\James_l_thumbnail_908893.jpg" -Quick
```

The identity source is `E:\ByrdHouse\profiles\me\references` (gitignored,
on-machine only). Baseline acceptance passes only when the result is clearly
Carey at first glance, the facial hair is naturally his with a single beard
edge, target pose/expression/scalp-hair/clothing are intact, there is no visible
seam, and the verifier returns `IDENTITY_PASS`.

## Sync repo → runtime

Everything permanent lives in `E:\Byrdhouse-Repo` (the git repo). After pulling
this branch, copy the changed lane files into the `E:\ByrdHouse` runtime
**without deleting** runtime-only models/references/outputs/config:

```powershell
# from E:\Byrdhouse-Repo, on the branch claude/local-face-swap-lora-68v0sq
$src = "E:\Byrdhouse-Repo"; $dst = "E:\ByrdHouse"
robocopy "$src\scripts"        "$dst\scripts"        realistic_reactor_refine.py byrdswap.py byrdcast_swap.py facelab.ps1 /XO
robocopy "$src\configs\image"  "$dst\configs\image"  realistic_reactor_refine.json /XO
robocopy "$src\workflows"      "$dst\workflows"      reactor_faceswap_api.json sd15_face_zone_ipadapter_api.json /XO
robocopy "$src\docs"           "$dst\docs"           REALISTIC_REACTOR_REFINE.md /XO
# /XO copies only when the source is newer; nothing under models\, profiles\,
# artifacts\, db\, or byrdhouse.config.json is touched.
```
