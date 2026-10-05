# ByrdHouse Windows local Studio

Publication snapshot, 2026-10-05: see `../docs/STATE.md` for current qualification
and the Radeon/ROCm deployment. `mesh_cleanup.py` is an undeployed experiment,
not a production-approved face edit. Personal runtime configuration is ignored;
adapt the example files to your installation. Model weights and Carey art are
not included in this public source package.

Current deployment: `D:\ByrdHouse` on the Windows RX 7900 XT PC. The
configuration `byrdhouse-local.json` owns runtime paths and local addresses.
This package preserves the deployed source; it is separate from the historical
mini-PC router/worker deployment. Personal photos and model weights stay local.

Correction, still generation and animation now share the same persistent worker.
Failed jobs with a saved prompt offer **Recover existing render**, which collects
that submission without another render. Interrupted known submissions resume
from saved provenance; ambiguous/legacy submissions may require inspection.
See `../docs/reviews/2026-10-03-queue-recovery-validation.md` for 63 focused tests,
live serialized correction/animation and successful recovery of completed frames.

Launch `Start-ByrdHouse.ps1` from the deployment folder to open the Studio.
Its default engine uses the upstream FaceID Plus V2 loader and companion LoRA,
with the full original Carey portrait. Exact photo edit and FLUX.2 Klein are
alternatives; Carey LoRA can supplement photo guidance. LoRA-only jobs are
disabled while the photo-reference requirement is enabled. Every route needs
visual review; the earlier appearance adapter was incorrectly labelled FaceID.

Carey is a Black man. Every new character job requires a Carey photo and includes
skin-tone and facial-identity preservation direction. Prompt wording cannot
guarantee likeness: each generated candidate starts in `needs_review`. Compare
it with the original photo in the image dialog, then keep or reject it. Previous
unconditioned demos are rejected and hidden, with files retained.

The Create selector offers five versioned recipes: expressions (8), camera angles
(6), outfits (6), animation stills (8), and anime (6). Choose one to three versions
per shot. Each candidate has a distinct seed, job record, and metadata card.
The queue accepts an entire pack atomically and processes one image at a time.

Download stills from a finished pack. ZIPs include PNGs, metadata, and
`pack_to_blender.py`; rejected images are omitted. On the installed PC run
`Open-Carey-Pack.ps1 -PackPath <zip-or-extracted-directory>` to build and open
an editable `.blend`. Every texture is packed into the file. It provides camera
motion over stills; it does not synthesize facial or limb animation.

`Open-Blender-MotionReel.ps1` opens the latest constructed pack. `review_packs.py`
builds local QA contact sheets with the original photo and can export finished
packs. SQLite lives in `studio/jobs.sqlite3`; it is runtime data, not source.

The completed five-pack test saved 34 images with no failed records remaining;
the six timeout records were recovered without submitting another prompt.
An eight-shot `.blend` was rendered and encoded into a 16-second camera-motion
preview. `render_animatic.py` renders a small preview from a loaded project;
`encode_animatic.py` uses the local runtime's FFmpeg to encode those exact frames.

Verification: `python -m unittest discover -s studio -p "test*.py"` (25 tests).
The GPU smoke result and remaining likeness gates live in
`docs/IMAGE_GENERATION_STATE.md`; provenance is in `docs/model-license-manifest.md`.

## Identity belt

The local Identity Belt is the measured correction lane for a finished still.
It runs ReActor face swap, the ReActor mask helper with the local YOLO/SAM
models, then compares every candidate with the selected Carey reference using
InsightFace. The examiner also uses `fan2_68_landmark.onnx` for the jaw, brow,
and eye outline and the local `jonathandinu/face-parsing` SegFormer for hair,
skin, brow, and forehead masks. Reports include face-box, forehead,
eye-distance, mouth-width, hairline, and outline measurements. Results are
always marked for review; the score is a ranking signal, not an approval.
Edge-to-edge close-up references are padded for detection. Direct and restored
swaps are compared; restoration only receives a preference when scores are close.
Missing hairline/outline measurements fail the checks. Scores are not percentages.
Each new belt result includes a three-panel hairline/jaw overlay for inspection.
The default restoration uses the hash- and ONNX-verified GPEN-BFR-512 model.
Correcting a generated still creates a separate gallery record in `needs_review`,
with its original parent retained. The hairline/jaw report remains linked on the
corrected card. This measures the hairstyle; it does not transfer the reference hair.

Fast mode uses creator-published RealVisXL V5 Lightning at five steps,
DPM++ SDE/Karras, CFG 1.5. Configured cache RAM headrooms of 4/8 GB reduced one
measured warm generation after restoration to 13.09 seconds. Cold loading still
took 130.11 seconds; neither figure is a guarantee for every scene.

From PowerShell:

```powershell
python D:\ByrdHouse\studio\identity_belt.py `
  --target D:\ByrdHouse\media\images\target.png `
  --reference D:\ByrdHouse\training\carey\references\portrait.jpeg `
  --label scene-check
```

The selected PNG and its JSON report are written to
`D:\ByrdHouse\media\images\belt-<label>-<id>.png`. The Studio page also has
an **Identity belt target** control; enter a filename from the ByrdHouse image,
photo, or reference folder and inspect the preview before saving it for an
animation pack. The HTTP endpoint is `POST /api/belt` with `target`,
`reference`, and optional `label` fields.

An earlier CivitAI-labelled experiment is preserved at
`C:\Users\carey\Documents\ByrdHouse\ComfyUI\user\default\workflows\ByrdHouse_CivitAI_IPAdapterFaceID_SDXL.json`.
Its loaded Plus Face adapter did not use FaceID embeddings; earlier scores do
not validate the current FaceID workflow. Studio now uses upstream
`IPAdapterUnifiedLoaderFaceID`, FACEID PLUS V2, and its companion LoRA. The
unchanged upstream example is in `external/workflows/upstream-ipadapter-faceid.json`.
Generate a new scene, use **Correct likeness**, then compare the candidate with
the original before keeping or exporting it for animation.

## Original-photo animation preview

The Studio's **Animate original photo** action and `portrait_animation.py` adapt the upstream AdvancedLivePortrait
`Advanced_Animate_without_vid.json` example and uses the original Carey portrait.
It makes a restrained blink/head-motion preview, saves the submitted graph,
source hash, job state and all 44 frames, then encodes those frames at 15 fps.
Select a reference photo and click **Animate original photo**. For a generated
still, review it and **Keep likeness**, then choose **Animate still**. Source
approval and its file hash are checked again before rendering. Jobs use the
existing SQLite queue, preventing concurrent Studio GPU submissions. Videos
appear in the gallery with **Save video**, **Compare source**, **Keep motion**,
and **Reject**. MP4s and sidecars are under `media/images`; submitted workflows
and frames are under `media/animation/<job-id>/`. This is facial motion, not a camera pan,
but reconstruction softens details and still requires visual review.

The installed models have a local provenance file with Hub-verified hashes.
Native AMD execution completed in 44.94 seconds for the first 2.93-second clip.
The launcher disables async offloading after a documented HIP launch failure;
do not infer long-run stability from a single successful recovery.

The full Studio-button test completed in 42.43 seconds. Browser video metadata
confirmed a 1152x1536, 2.93-second playable resource; decoding verified all 44
frames. The result remains `needs_review`. Talking and full-body animation are
not implemented by this portrait-motion preset.
