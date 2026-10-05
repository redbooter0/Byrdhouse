# Image Generation State — read before changing the GAMING image lane

## Connected hairline V2 and CPU mesh restored — 2026-10-04

Detached semantic eyebrow patches no longer become hairline points in the
tested frames. The approved anchor is unchanged; its new separate measurement
profile is `anchor-v1-profile-v2.json`. New CPU checks bind code/model hashes
and measurement version. Live V2 job `3bbf35932e789a0c427faec1fabfa4d2`
examined 33 frames in 271.37 s; existing afro-width cues remain at 5/7.
Rejected-still review `279548b6036ef1d2bad7f9b54fc1e8f6` took 10.84 s and
flags all six groups. Source states/pixels/hashes are unchanged.
Official MediaPipe weights (5,423,900 bytes, verified on D: and runtime copy)
restore the existing CPU 478-point loader. Its configured current-PC paths
and normal CLI analysis work; full semantic face editing remains unqualified.
183 tests pass. No Comfy restart or new generation occurred. Read
[the implementation record and limits](reviews/2026-10-04-hairline-v2-and-face-mesh.md).

## FreeVideo source follow-up — 2026-10-04

Carey's repeated link was checked against upstream `a9098b7…`, four commits
beyond the original source pin. No documented AMD path was added; the working
Python/ROCm runtime remains unchanged. Additional H3 Radeon examples are
different implementations/hardware, not qualified local results. The standard
H3 license excludes the US/EU/UK/Republic of Korea and requires separate
licensing for excluded territories. No H3 weights or custom nodes were added.
Existing Wan preview `3d6490df1abea740c499afcbca8befe7` decoded all 33 frames;
its frame/movie/approved-anchor hashes match and its state is `needs_review`.
Both queues were empty. See [the source and media evidence](reviews/2026-10-04-freevideo-follow-up.md).

## Matching-view checks are now in Studio — 2026-10-04 (latest)

**Check likeness** queues a read-only CPU review of an illustrated still or
every collected frame of a clip against its explicitly selected approved
view. Front/profile/rear/three-quarter choices reuse the locked sheets;
rear views make no face claim. Review/report images cannot seed animation.
No source pixels or source-job approval change. 173 tests pass, including
changed-input, cached-report and restart refusal/resume cases.

All 33 frames of Wan job `3d6490df1abea740c499afcbca8befe7` are now examined.
Frames **5 and 7** have borderline afro-width cues (0.162619/0.166566 vs the
existing 0.16 screen) that the earlier five-frame sample missed. They are
review flags, not identity verdicts; the clip remains `needs_review`.
The known rejected new-scene portrait flags all six measured feature groups,
including +53.285 parsed skin-brightness shift. A live CPU-review restart
preserved ten completed report hashes and completed the same job, with no
GPU submission. This is not live GPU-render restart proof. The full check
spanned 298 seconds including restart; warm rejected-still review took 8.08 s.
Estimated hairline points can leak onto brows; eyes/beard/teeth/mouth still
require direct visual checking. See
[the Studio integration and exact artifact paths](reviews/2026-10-04-studio-continuity-review-validation.md).

## Native Wan 5B Radeon motion candidate — 2026-10-04 (latest)

Official ComfyUI Wan 2.2 5B image-to-video is integrated into the existing
Studio queue, using verified D: models, hash-bound source/template/submission,
native tiled VAE decode and durable PNG-to-MP4 collection. No extra CUDA wheels
or custom-node packs were installed. Job `3d6490df1abea740c499afcbca8befe7`
animated the approved Carey anime anchor: 384x576, 33 frames, 24 fps,
1.375 seconds, 472.68 s total. It is **needs_review**. Matching-view review
of frames 0/8/16/24/32 passes hair, forehead and outline screens but is not
exact likeness or full temporal review; color fringing and softer mouth/teeth
still need inspection. Browser playback loaded both completed candidates.

Default dynamic VRAM failed with `HostBuffer.read_file_slice`; the same-seed
retry worked with `--disable-dynamic-vram`. This option is now saved in the
live config/launcher. MIOpen-enabled retry `fda13a693d3ab6340826dd8e1c55bfc6`
took 694.64 s and used more sampled VRAM, so that setting was rolled back.
Working-run sampled maxima: 17.54 GiB device VRAM, 30.01 GiB whole-system RAM;
these are observations at about 2-second spacing, not exact peaks. Detail
resolution, long episodes, full-body motion and lip-sync remain untested.

After rollback, SDXL source-edit `6048e11528ab334f6375f5c001377df8` completed
in 60.08 s Comfy execution / about 8 s sampling. All 499,269 semantic Carey
face/hair core pixels stayed identical. Its thin pale hair edge keeps it in
`needs_review`; it was not animated. The CivitAI new-scene portrait
`15a745b5272cda3fe8c73f8b0ed41003` was visibly rejected for identity drift
and lighter skin. 165 Studio tests pass. See
[full sources, deployment and qualification](reviews/2026-10-04-native-wan-amd-qualification.md).

## Carey four-view anime and wardrobe candidates — 2026-10-04 (latest)

Built-in ChatGPT image generation produced a four-view full-body Carey
turnaround, a matching burgundy-hoodie clothing variant, and a larger head
turnaround from the owner-approved illustrated anchor plus real Carey face and
body photos. They are saved under `D:\ByrdHouse\assets\characters\carey-anime`.
Carey subsequently approved their illustrated likeness as looking exactly
like him; stable hash-locked copies are listed in `turnaround-v1.json`. The
outfits remain unapproved placeholders. These are not a trained identity
model, layered rig, or episode assets. The head front has an extra ear stud;
a focused edit failed to fix it.
Back details are inferred because no rear photo was supplied. Details, hashes,
reference photos, wardrobe prompts, and review limits are in
[the turnaround review](reviews/2026-10-04-carey-chatgpt-turnaround.md). The
RX 7900 XT was not used for these ChatGPT-generated sheets; the local Comfy
workflow remains the episode production route.

The approved head turnaround has hash-checked front and profile crops for
read-only **matching-view** review. The side profiles are detected; comparing
them against the close-up front anchor produced misleadingly low similarity
cues because the view changed. `windows-local/studio/anime_view_review.py`
now compares a proposed new frame against the selected approved view, including
the close-up anchor for three-quarter portraits, keeps
wardrobe out of the likeness decision, and never grants automatic approval.
It is a local operator tool, not yet integrated into Studio's job report.
See [the measured record](reviews/2026-10-04-carey-multiview-belt.md).

The Brambleton scene jobs `26e31a04331739f4bd13346c1274d8c5` and
`1df18317cd9131ecb66e143feb4236fa` are **rejected** because a visible pale
halo survived around the afro even though the semantic core pixels matched
the anchor exactly. An independent-background version
`a3b1a4a04a2e2d7d7458e75a5f058ca3` removes the broad haze, preserves all
499,269 frozen core pixels, and changes 234,999 background pixels. A thin light
outline remains at full resolution, so it stays `needs_review`. See
[the scene-edge qualification](reviews/2026-10-04-anime-scene-edge-qualification.md).

## Anime canon belt now measures the approved afro and forehead — 2026-10-04 (latest)

The CPU face parser labeled the illustrated Carey afro primarily as `hat` even
though its segmentation visibly traced the correct outer curls. Studio now
uses the union of hair and hat labels only in its illustrated continuity
inspector; photoreal hats remain excluded. The owner-approved Anchor v1 has a
hash-bound local measurement profile with face box, hair bounds, median
hairline position, forehead height, afro dimensions, outline signature, and
parsed skin RGB. Its profile and registered anchor hashes are checked before
an anime report is trusted.

On a same-view comparison, the faithful source-latent redraw `346b…` passes
the hair, forehead, and outline review screens; the rejected AnimeFix redraw
`3a…` fails all three, with a `+46.936` median skin-luminance shift. The belt
now highlights which features need change on its annotated report. It never
automatically approves illustrated identity. Tests and exact values are in
[the 2026-10-04 belt validation](reviews/2026-10-04-anime-canon-belt-validation.md).
Three sampled frames of the existing 44-frame canon-anchor motion clip passed
same-view hair, forehead and outline screens, but the teeth and mustache were
visibly softer in the middle frame. It remains a motion test in `needs_review`.
The unchanged anchor examination is now cached by SHA256 within the Studio
process; repeated measurement fell from `15.836 s` cold to `0.0019 s` on this PC.

## Anime show-canon route — anchor motion passes technical playback; first new-scene keyframe rejected — 2026-10-03 (latest)

Carey selected `Carey Anime Canon Anchor v1` as the show’s illustrated visual
source of truth. The owner-approved anchor is hash-locked at
`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png` (SHA256
`2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`). The
Studio permits that explicitly approved illustrated source for a private
AdvancedLivePortrait motion test. Job `0cf48a1d6a53295f53b4727bd0efb4e7`
rendered 44 frames / 2.93 seconds; sampled frames retained the anchor’s face
and afro while adding a small blink/head shift. It remains **needs_review**:
technical playback is not animation approval.

Animagine XL 4.0 Opt is hash-verified and installed as an illustrated SDXL
keyframe candidate. The first local existing-workflow-inspired IP-Adapter Plus
Face + SDPose + ControlNet Union shot (`97b0b62f810d753cec3bf3c836329261`,
same locked seed) rendered in 117.26 seconds but was visually **rejected**. It
produced a generic small face, lost the canonical beard/brow/mouth detail,
made the afro an oversized smooth sphere, and failed to establish a recognizable
Brambleton setting. The local face/hairline review detector could not find a
usable face in that illustration, so its saved inspection is explicitly
**inconclusive** (`similarity: null`, no geometry values), never a passed score.
It must not be animated or used as an anchor-kit example.

Studio now records that illustrated-detector gap as a review failure without
crashing the completed still. The next gate is a close, sharp canonical
portrait/turnaround kit approved by Carey before another full-body or episode
pose. Do not use the rejected frame to train a LoRA or seed a replacement.
See [the detailed anime keyframe lab record](reviews/2026-10-03-anime-anchor-keyframe-lab.md).

## Existing online workflow qualification: source-latent anchor and scene swap — 2026-10-03 (latest)

Two existing open workflow repositories are staged locally with pinned commits:
Apache-2.0 `ayushchinmay/ComfyUI_Img2Img_Workflow`
(`2be98e6b6aff069a51f989cd855c4f5345906931`) and MIT
`ExMikuPro/AnimeFix-Workflow` (`4caa3dd4d3a0ccb84a6696f52af5a6a6facdbb44`).
The second workflow’s available FaceDetailer/SAM/YOLO subset was tested; its
output `3a06290e6e71c7956044964485651edd_1.png` changed the canonical face and
afro and is rejected. The detailer is disabled by default.

The first repository’s source-latent pattern is qualified: instead of starting
from empty noise, Studio encodes the locked anime anchor at low denoise before
applying the existing IP-Adapter and pose controls. Job
`346b554dc7bf47f8c986aa08aec35729` retained the canonical face/hair design
(`0.876475` read-only visual-similarity cue) but did not sufficiently change
the scene, which is expected for a likeness-first anchor-kit stage.

Studio now has an anchor-specific reviewed scene-swap route. It uses the
installed face parser/BiRefNet mask to preserve the illustrated person and
Animagine XL to inpaint only the background. In the Brambleton test
`26e31a04331739f4bd13346c1274d8c5`, 499,269 semantic face/hair/body core
pixels were exactly identical to Anchor v1; 231,775 background pixels changed.
This proves source-pose preservation only. A later full-size inspection found
a pale exterior afro halo, so the still was **rejected for show art**.

The local image belt was also corrected for the approved illustrated anchor:
the upstream photo-trained face parser labels the drawn afro primarily as
`hat`, despite visibly segmenting its full silhouette. The belt now preserves
the literal hair and headwear areas separately and evaluates their union as an
illustrated hair silhouette. This makes the forehead/hairline, afro width, and
afro height measurable review cues rather than incorrectly reporting no hair.

## PuLID v1.1 new-scene workflow works; likeness rejected — 2026-10-03 (latest)

The local RX 7900 XT now has a private PuLID v1.1 / SDPose / ControlNet Union
qualification lane based on a staged CivitAI SDXL IP-Adapter + Union workflow.
It is not a scratch-built renderer. A three-real-photo Carey identity batch and
a separate full-body real Carey pose image produced a new 832×1216 studio still
in 128.40 seconds including its first EVA encoder download. The output is
rejected: CPU identity similarity was 0.591786 against the clean smile reference
(below the 0.65 review screen), and the visual review found a taller/spikier
afro, higher/smoother hairline, narrowed midface/jaw, and regenerated beard/
mouth. Do not animate it. The full workflow, hashes, failed first wiring attempt,
annotated comparison, and next gate are in
[the PuLID/SDPose/Union lab record](reviews/2026-10-03-pulid-sdpose-union-lab.md).

ComfyUI and Studio were restored after a restart-script application-control
block by launching the trusted base Python with the exact venv site-packages.
Both respond at their normal localhost ports. The normal restart script still
needs a launch-path repair before relying on it again.

## Source pixels preserved; scene edges rejected — 2026-10-03 (latest)

Installed CPU semantic parsing and core masked SDXL/final compositing now run
through Studio's shared queue. Original analysis `377bcabf9a3e55e422fe8f3df3430ad4`
completed in 10.53 s. Scenes `25656bbecdfab3a0b1166aeb3512d8df` (45.44 s) and
`0c310b7900be3748cbfb35389007d053` (13.58 s warm) each kept all 331,764 protected
pixels identical to the native 1152×1536 working photo, with zero changes outside
the editable mask. Both scene candidates were visually **rejected** for the hard
retained tile/background halo around the afro. Exact protected pixels do not
establish a seamless scene. Neither rejected still was animated.

New stills now stage and rehash fixed reference inputs; originals are separately
hash verified for source preservation. Ambiguous submissions refuse a second
POST, known submissions resume from their exact journal, and masks cannot be
animated. 138 focused tests pass; eleven deployed/source hashes match. ComfyUI
PID 6840 remained unchanged. No new model/runtime installed; parser model scope
is private research per its model card. No during-render VRAM peak was sampled.
Both queues are empty. Full proof, model hash, source hash, workflow IDs,
rejection reasons and files are in
[source-preservation validation](reviews/2026-10-03-source-preservation-validation.md).

Next: compare existing upstream hair matting/boundary refinement. Keep facial
features and reviewed head interior fixed; record any edge-pixel changes and
their narrower guarantee. Do not shrink a mask silently or claim that exact
face/head pixels also guarantee new poses or animated frames. SSD cache,
matched-pose feature analysis, live mid-render restart and sustained AMD health
remain unfinished.

## Shared queue and recovered animation — 2026-10-03 (latest)

Correction now enqueues before rendering and shares the SQLite worker with stills
and animation. Submitted operations preserve prompt IDs and durable provenance;
restart reconciliation/resume and a GUI **Recover existing render** button collect
known submissions without a new render. 63 focused tests pass.

Browser correction `87e2a2d1e2336791766879e738644975` completed in 54.56 s;
animation `aafca1c98eba4c671445df41d245ae09` started after it. ComfyUI rendered 44
frames, but strict collector validation first rejected upstream FLOAT coercion.
The verified correction accepts equal int-to-float widget values while keeping
source/workflow bindings strict. GUI recovery collected the same prompt
`371274e1-790e-43e5-af31-3273b2c77938`, no second render, with accumulated execution/
collection time 42.63 s. Browser playback is 1152x1536/2.933333 s; all 44 MP4
frames decoded. Correction/animation remain `needs_review`, not exact replicas.
The corrected still still has generated spiky/tall hair and changed teeth/details.

See [full implementation proof and limits](reviews/2026-10-03-queue-recovery-validation.md).
Seven source/deployment hashes match. Live mid-render restart was not performed
(jobs completed before the attempt); recovery is mock-tested and completed-output
collection is live-tested. Sustained AMD stability, ordinary-still input rehashing,
pose matching and exact likeness remain open. Next: semantic source-preservation
with the installed upstream parser/core composite workflow.

## Saved current-PC reviews — 2026-10-03

Carey requested persistent detailed reviews for future work. The
[review index](reviews/README.md) links the hardware/runtime and
architecture/identity audits; the [implementation proposal](CURRENT_PC_IMPROVEMENT_PLAN.md)
orders the next work. The audit found correction bypasses the Studio worker,
startup recovery does not reconcile prompt IDs, and current hair/geometry checks
cannot establish exact likeness. The queue gap was subsequently fixed above;
other proposals and qualification limits remain open.
Current machine: i9-10850K, RX 7900 XT 20 GB, 32 GB RAM; C: SSD and D: 2 TB HDD.

## GPEN and gallery validation — 2026-10-03 (current)

### Studio animation integration (latest)

The tested upstream portrait-motion graph is now connected to the Studio's
SQLite queue. **Animate original photo** uses the selected original reference.
**Animate still** requires a kept still; the API also enforces this and rechecks
approval and source SHA256 before rendering. Gallery videos have playback,
download, source comparison and separate motion-review controls. Metadata stays
`identity_verified: false` / `exact_replica: false` regardless of measurement scores.

Browser-submitted job `43ec9f44984da64b6a8737de5bc39825` completed in 42.43 s.
HTTP video response is 200/video-mp4; the browser loaded it with readyState 4,
1152x1536 and duration 2.933333 s. FFmpeg decoded all 44 frames at 15 fps.
Live POST of an unreviewed generated still correctly returned HTTP 400.
25 focused tests pass, including source hash recording, approved-source
enforcement, rechecking after rejection, and request/path boundaries.
The command-line-only limitation recorded for the earlier preview below is
superseded. Talking and full-body motion remain outside this tested preset.

Founder clarification: an approximate face is unacceptable. The belt must show
which features differ, explain the correction and preserve likeness through
animation. Do not equate an embedding score or a passed geometry gate with an
exact replica. Photo variation UI wording was corrected because low denoise can
still alter facial features.

The annotated `belt-gpen-gallery-validation-3e34227396.png-analysis.png` now marks
five visually reviewed differences: hair silhouette, forehead/hairline,
eyes/brows, smile/teeth, and jaw/beard. It explains preserving original pixels
and matching pose before comparison. These are explicit visual-review notes,
not fabricated automatic measurements. The generated candidate is not exact.

An original-photo animation was completed using the upstream
`PowerHouseMan/ComfyUI-AdvancedLivePortrait` no-driving-video example, commit
`3bba732915e22f18af0d221b9c5c282990181f1b`. Five converted safetensors were
downloaded from Kijai/LivePortrait_safetensors and matched Hub SHA256 metadata;
provenance is in `D:\ByrdHouse\models\liveportrait\provenance.json`.
Local job `f0460e2ce897719fcf60ef3e26af8b8e` produced 44 frames at 15 fps
(2.93 seconds), encoded as `Carey-original-photo-motion.mp4`, in 44.94 seconds.
The source was the original portrait, not a generated surrogate. Frames 0, 14,
and 30 were visually inspected: blink and slight head movement, with some
softening of detail. LivePortrait reconstructs moving pixels; exact identity
and final animation quality are NOT approved. This is a command-line preview
lane, not yet a Studio animation button, talking animation or full-body motion.
Sample-frame examination measured similarity 0.985036 / 0.964021 / 0.985036
against the original for frames 0 / 14 / 30. All three geometry checks passed;
these uncalibrated scores do not establish exact likeness. Full measurements
are saved beside the animation in `frame-review.json`.

Stability caveat: a second warm workflow-switch test
`e42bab0d07e78825bc19b51ab65c422c` failed with HIP launch failure during VAE
decoding and terminated ComfyUI's prompt worker. Its log is preserved as
`comfy-launch-failure-20261003.log`. After verified empty queues the process was
restarted with `--disable-async-offload`; identical prompt/seed retry
`1b9e8a6e8f8606f347e260ed2b41a6e0` completed in 56.05 seconds. This mitigates a
suspected offload issue; one success does not establish long-run stability.

The native AMD lane now uses verified RealVisXL V5 Lightning, the upstream
FaceID Plus V2 paired loader, and ReActor/SAM correction with GPEN-BFR-512.
The installed GPEN file was truncated (239,304,704 bytes). The ReActor maintainer's
284,244,491-byte distribution was downloaded, its SHA256 verified against Hub
metadata, and ONNX parsing/checking passed before installation. The damaged file
is retained under external/models/reactor for audit. See the license manifest.

Same-target restoration comparison: GPEN visibility 0.6 scored 0.894661, GPEN 1.0
scored 0.890355, GFPGAN 1.0 scored 0.843990. GPEN 1.0 looked cleaner in direct
inspection and is the current restoration setting. The restored candidate gets
a small selection preference only within 0.015 of the direct similarity score;
this is a heuristic, not a calibrated likeness test. The upstream Impact Pack
FaceDetailer example is preserved unchanged; private RealVis refinements at
denoise 0.20 and 0.35 were tested and rejected (blur or identity drift), not added
to the default workflow.

Integrated correction of job `6a479e91e333b6a276aed36a018c257b` completed in
49.5 seconds and produced a separate gallery record
`3cd314ab11006a65259279a8e221d6fb`, retaining its parent and all source files.
Its forehead/hairline/jaw measurement gates passed; it remains `needs_review`
with `identity_verified: false`. The original/target/candidate overlay was viewed.
The belt preserves the generated hairstyle; measuring hair is not hair transfer.
Human approval and reliable likeness across poses remain unproven.

ComfyUI is now launched with explicit RAM headrooms `--cache-ram 4 8`, verified
in its live argv. After a cold 130.11-second generation and a restoration graph,
job `acdaef5a2ee676b581f6d658cb6dd56b` completed in 13.09 seconds Studio time
(12.68 backend), compared with the earlier 139.05-second reload. This is a
measured warm workflow switch, not a cold-start performance promise.

21 focused tests pass, including separate correction review records, parent
preservation and persistent analysis links. Browser inspection confirms the
corrected gallery entry and current fast defaults. The broad goal remains active.

## Correction audit — late 2026-10-02 (supersedes earlier FaceID claims below)

The earlier route was named FaceID but loaded `ip-adapter-plus-face_sdxl_vit-h.safetensors`.
The upstream implementation detects adapter type from weights, so this did **not**
use identity embeddings. Earlier speed/quality records labelled FaceID are records
of that appearance-adapter route, not proof of FaceID Plus V2 quality.

The Studio now uses upstream `IPAdapterUnifiedLoaderFaceID`, preset FACEID PLUS V2,
with companion LoRA strength 0.6, the actual `ip-adapter-faceid-plusv2_sdxl.bin`,
and local InsightFace. The untouched upstream example is preserved in
`external/workflows/upstream-ipadapter-faceid.json` (installed upstream commit
`a0f451a5113cf9becb0847b92884cb10cbdec0ef`). Default reference is the full original
`portrait.jpeg`; cropped references can fail face detection. Carey reference is
required; LoRA-only mode is disabled. Reference+optional LoRA remains supported.

Actual corrected FaceID base test: job `504cf231aac3d8f7e823c5d230944627`, 119.12 s
including loading, 24 sampling steps in 11.9 s. Original-to-generated embedding
similarity 0.620872. ReActor/SAM belt `faceid-v2-corrected-9360b369ee` selected restored
at 0.884733. The result still looks synthetic and is NOT visually approved.
Similarity is not a calibrated percentage or proof of likeness.

Belt v2 fixes three measurement errors: first hair pixel was mistaken for the
hair/skin boundary, the ROI top was added twice, and padded detection keypoints
were passed to the parser without subtracting the padding. The jaw gate now uses
the jaw landmarks rather than all 68 points. Missing segmentation or landmarks
fail the measurement gates. Real reference/target/candidate overlays visibly trace
the hairline and jaw in `belt-faceid-v2-corrected-9360b369ee.png-analysis.png`.
Direct and restored candidates are the default; extended blur/mean-face comparisons
are opt-in via `belt_extended_candidates`. All outputs still require human review.

Downloaded creator-published `SG161222/RealVisXL_V5.0_Lightning`, revision
`f4454158cedaab9f0688c199561d6c92525f3a85`, file
`RealVisXL_V5.0_Lightning_fp16.safetensors` (6,938,065,512 bytes), verified SHA256
`fabcadd9330dcc4f9702063428d40b9d4d07168d8acefc819b8d1d9db466b3ec`.
Fast mode uses its published 5-step DPM++ SDE/Karras, CFG 1.5 settings, without
adding another Lightning LoRA. Base SDXL remains the quality route. RealVis test
`6a479e91e333b6a276aed36a018c257b` completed: 92.27 s backend including cold load,
4.8 s sampling. Warm seed variation `844092163971861342a22339f3403dce` completed
in 12 s Studio wall time / 9.19 s backend. Both were visually inspected: cleaner
texture and scene adherence, but likeness still requires review. Fast is now the
default mode; the experimental Carey LoRA strength defaults to zero and can be
raised explicitly alongside the required photo reference.

Belt `realvis-five-step-b92d52b963` completed in 53.89 s with two candidates.
Direct: similarity 0.899480, jaw-outline error 0.082064, forehead-height delta
0.012074, hair-width delta 0.009603; restored similarity 0.878202. All measurement
gates pass. Visual inspection nevertheless finds the selected direct swap blurry
at full size (128px swap limitation); restored is cleaner but softer. Do not call
this final quality or declare the broad goal achieved. Next: reuse an upstream
FaceDetailer/refinement stage to recover texture without losing identity, and
review across poses. Both candidates and the hairline/jaw overlay are retained.
The Studio gallery now has a Check likeness action and a link to the analysis.
Final saved-defaults job `ad4cdb700a0364dc6cfceceb0323691e` completed successfully
after a belt-to-generation switch: 139.05 s Studio / 138.75 s backend, with only
4.4 s spent sampling. HDD-backed model reload/initialization is a material
bottleneck. Do not advertise the 12 s warm time as an end-to-end promise.

20 focused tests pass (Studio routes, model pairing, no double acceleration,
hairline translation invariance, padding coordinates, missing-measurement rejection).
CPU examiner benchmark: warm 4 threads 7.71 s vs 10 threads 7.61 s per original;
no evidence to change the CPU thread count. ComfyUI reports native RX 7900 XT,
20,464 MiB VRAM. The broad user goal remains active: convincing likeness and a
reusable simple workflow are not proven by these measurement checks alone.

## Current Windows RX 7900 XT restoration — 2026-10-02

This PC now runs from `D:\ByrdHouse` on the attached 2 TB HDD, with
ComfyUI/runtime on C:. The owner will set up the mini PC later. The historical
3070/E: verdicts below do not describe this current hardware.

Founder direction: **all Carey generations and examples must resemble him as a
Black man**. New Studio jobs require an original local Carey photo. A prompt
mentioning race is insufficient identity proof. Previous unconditioned demos
were rejected and hidden; their files remain available for audit.

Likeness correction on 2026-10-02: the full-image SDXL IP-Adapter path copied
the reference scene and produced neon texture smearing, warped facial features,
and unusable candidates. That path is retired from the Studio UI. The default
is now SDXL **FaceID photo guidance**, using the square clean Carey reference
and the CivitAI-tested `IPAdapterFaceID` chain so pose, clothing, and lighting
can change without discarding his identity. Exact photo edit and Carey v2 LoRA
remain available as explicit alternatives, and every result still starts
`needs_review`.

The local Identity Belt now scores InsightFace similarity plus 68-point face
outline and SegFormer hair/forehead structure. It pads edge-to-edge close-ups
for detection and prefers a restored or smoothed candidate when it is within a
close likeness band of the direct swap, preventing the sharper warped composite
from winning.

Installed and tested on RX 7900 XT 20 GB, 32 GB system RAM:

- SDXL base + CivitAI-tested FaceID Plus Face adapter, local `buffalo_l`
  InsightFace, and Carey v2 rank-8 LoRA. A warm FaceID quality job completed in
  35.8 seconds; the four-step FaceID fast path completed in 3.4 seconds once
  warm (its first lightning-model load took 45.0 seconds). LoRA-only creative
  jobs remain exposed for comparison but are not the likeness default.
- FLUX.2 Klein 4B BF16 distilled + Qwen3 4B + FLUX2 VAE using core ComfyUI
  `ReferenceLatent`. First actual photo edit `d6d059c99b7f831a75e0dbc018fd1220`
  completed in 66.39 seconds including initial model load. It changes the shirt,
  background, and expression more aggressively but is now an optional candidate
  route. SDXL LoRAs are excluded from the FLUX graph. Model checksums verified;
  see license manifest.
- ComfyUI reports native RX 7900 XT with 20,464 MiB. During FLUX batch work,
  `/system_stats` reported 9,286 MiB free VRAM, 8,454 MiB Torch VRAM total.
  Core sampling completed without an out-of-memory error. This is a measured
  snapshot, not a promise of available memory during every step.

Studio source is preserved under `windows-local/`: mandatory photo reference,
automatic Carey/Black identity guidance, five versioned recipes totaling 34
variations, one to three versions per shot, atomic bounded SQLite queue,
side-by-side original/result comparison, rejected-image filtering, pack ZIPs
with full settings, and an editable Blender handoff with embedded source images.

Real batch tests: **34/34 candidates completed**, six anime, six camera angles,
six outfits, eight expressions, and eight cinematic stills. All five complete
contact sheets were visually inspected and show Black
subjects; specific likeness remains subject to Carey's review. Profile views may
invent features not visible in the frontal input. Six anime images were packed
into an actual editable `.blend`; the eight cinematic stills were also packed
into a separate `.blend`. Camera movement is an animatic, not synthesized
facial/body motion. Final pack results are recorded in the local `media/packs/index.json`.

An extended run exposed a ComfyUI HTTP stall (one render took 250.50 seconds).
The first Studio worker marked six jobs failed after 30-second HTTP waits even
though rendering continued. Fixed: longer submission wait, retry history reads
after transient timeouts within the existing 20-minute generation deadline,
and recovery from the original backend prompt record without resubmission.
All six lost Studio records were recovered from their original ComfyUI histories;
all five packs now have no failed jobs and include complete exports.
Warm batch median: 16.23 seconds per candidate (minimum 14.32 seconds; one
250.49-second stall included in the run). Actual Blender rendering produced all
384 frames of the eight-shot, 16-second animatic at 416×608/24 fps in 16.34 seconds.
Frames 1 and 145 were visually inspected for framing and skin-tone preservation,
then FFmpeg encoded the MP4 successfully. The source `.blend` stays at 832×1216.
The Studio comparison dialog was tested and captured in `studio-likeness-review.png`.
The timeout/no-duplicate behavior and the new exact photo-edit graph are covered
by the Studio's 15 passing tests.

Fresh smoke test on 2026-10-02: three new FLUX reference-conditioned candidates
completed in 15.49–17.25 seconds (`9372f2d18134babdff8be91a400f54e7`,
`5058d5d048d784ce44992f911fcf7570`, and
`87b5ef4cec45db67fe55d382c855b902`). The outputs were visually checked as Black
Carey candidates with afro hair and beard; they remain `needs_review` and were
not promoted automatically. The first two preserved the requested black bomber
and gray shirt; the close-up chose a white shirt, so prompt adherence still needs
human review.

Those exact three outputs were packed into
`media/packs/fresh-animation-test-20261002/Carey-animation-stills.blend` and
rendered successfully as 144 frames at 416×608/24 fps. FFmpeg encoded the frames
to the six-second
`media/packs/fresh-animation-test-20261002/Carey-camera-motion-preview.mp4`.
This proves the local still-to-editable-camera-animatic path; it is camera motion
over stills, not synthesized facial or body motion.

Likeness gate remains explicit: current images start `needs_review`, no identity
LoRA is automatically approved. Carey v2 used all 19 original photos; **no held-out
evaluation occurred**. Corrected the stale manifest's claimed hold-outs without
changing its weights. Its framing-caption heuristic can mislabel portraits and
requires curation before further training. No generated images entered training.

## Historical two-PC 3070 lane (last updated July 2026)

**Last updated:** 2026-07-15 (EDT, CPU crop reroute + adapter crop-preflight gate verified on the hard Vegeta target; integration suite green)  
**Owner:** BYRD-GAMING (`E:\ByrdHouse`)  
**Rule:** Read this file before changing an image model, graph, training set, or route. Update it after every real local test.

## Current verdict

The compact local target-edit belt now performs semantic masking and CPU identity mesh seeding, but **no Carey LoRA candidate or finished face-edit lane is approved**. LoRA-only semantic edits still produce a generic light/tan face or text-like facial artifacts. Warping a reviewed Carey anime reference into the target's 478-point mesh is a real improvement: the Naruto-seeded Gojo run transfers Carey identity/color before GPU cleanup. It nevertheless fails the visual gate because of a distorted visible eye, piercing-like facial artifacts, a pale retained target ear, and a hard jaw/ear skin seam.

Do not promote or configure any candidate as the recipe's deployed identity LoRA.

## Staged 2026-07-15: guided cleanup v3 (UNTESTED on hardware — test before trusting)

Note: the two-pass v2 recipe the integration suite locks (`recipes/anime_face_zone_edit.v2.json`) was missing from the rescued branch and has been reconstructed exactly to the suite's spec (identity_fill 16/0.38 + line_harmonize 8/0.12, `skip_gpu_cleanup: true`, accessory truth per preset).

Diagnosis of "CPU beat GPU": the v1 cleanup pass was **unguided** img2img — at
denoise 0.38 it could not redraw seams/lighting (kept them), at ~0.9 it destroyed
the warped identity, and the whole-crop VAE round trip washed color either way.
The 3070 was never the limit; the pass had nothing to push against.

Staged fix (recipe `anime_face_zone_edit@3`, graph
`workflows/sd15_face_zone_controlnet_api.json`):

- **ControlNet CANNY guidance extracted from the identity mesh seed itself**
  (core ComfyUI nodes; model `control_v11p_sd15_canny.safetensors`, openrail,
  ~700MB → `models/controlnet`; Meina 2.13GB + LoRA + ControlNet ≈ well inside
  the 7200MB budget at 512px).
- Denoise raised to **0.55** with canny strength 0.55 / end 0.75: the sampler
  now redraws the WHOLE zone's linework (full face, forehead included — the
  jaw-to-jaw limitation goes away because the redraw covers the entire semantic
  mask) in the target's material while the seed's edges hold Carey's geometry.
- **Hair-over-likeness composite rule** (byrdfacezone `composite_generated`):
  after the paste, the target's hair/headwear pixels are re-asserted ON TOP of
  the likeness through a feathered `hair_headwear_exclusion` mask, so the zone
  boundary can never eat the hairline and overlapping strands win.
- v1 stays as rollback; `skip_gpu_cleanup` still selects the CPU-only finish.
- First hardware test: rerun the Gojo (Naruto-seed) and hard-Vegeta targets on
  `anime_face_zone_edit@3`; sweep denoise 0.45–0.6 × canny strength 0.45–0.65;
  record VRAM + verdicts here per the rule above.

## Staged 2026-07-15 (later): the examiner — understand before touching (UNTESTED on hardware)

Founder contract: for ANY uploaded image the system must FIRST fully understand
where it can and can't operate, then plan which features get the founder's
likeness while keeping the target's logic/shape/theme. Start small: geometry
v1, semantic enrichment next.

- `byrdfacezone.py analyze` (new subcommand, edits nothing, landmarker-only,
  runs in any GPU mode): every face → box, size, yaw proxy, mouth-open ratio,
  verdict (`operable` / `operable_with_care` / `refuse` with reasons), risk
  flags — `extreme_expression` is the Luffy-grin case that melted the
  d36/m60 run; `strong_profile`; `too_small` — and the per-feature plan
  (skin/brow/nose/mouth/jaw = generate-likeness-in-target-form; eyes =
  keep-target; forehead = likeness-if-exposed; hair/headwear = keep-target
  composited OVER the likeness; expression/pose/theme = keep-target).
  Writes `face_report.json` + ONE clean overview PNG (numbered green/yellow/red
  boxes — replaces mesh/parse spaghetti as the founder-facing diagnostic).
- **Gate wired into the quality lane**: `edit_face_zone` now runs the examiner
  first and refuses with the examiner's own reasons before any zone/GPU work;
  the report rides every card (`face_report`).
- **Examine route** on `image.faceswap` (`route:"examine"`, dashboard "Examine
  first", required_mode ANY): archives the overview + verdict as an artifact so
  the founder sees operability before spending anything.
- Next rungs (in order, small steps): semantic enrichment of the report
  (headwear/eye occlusion truth from the parser — Gojo blindfold), per-face
  preset auto-suggestion from flags, multi-face batch operation.
- Thorough scrutiny (founder rule, 2026-07-15 later): `analyze --thorough` is
  the DEFAULT for the quality-lane gate and the examine route (`engine.quick_report`
  / `-Quick` opt out). Adds per-face scale-stability cross-check (re-detect at 2x,
  landmark drift → `geometry_stability` 0–1), parser occlusion truth over the eye
  line, a `recommended_lane` mapped to the FACE_OPS ladder, and `analysis_seconds`
  on the report — provable effort before any edit. Operator entry point:
  `scripts/facelab.ps1` (preflight/examine/quality/zone/auto/swap/collect/train);
  full manual in `docs/FACE_OPS.md`.
- First hardware test: `python scripts\byrdfacezone.py analyze --input <image>`
  on the five calibrated targets + one group shot + one no-face image; verify
  verdicts/flags match reality (Luffy close must flag extreme_expression);
  then one `route:"examine"` job through the belt.

## Flow audit 2026-07-15 (founder ask: make the route the image takes flow)

Fixed in this pass (UNTESTED on hardware):

1. **Fixed 512 canvas was softening large faces** — every crop was forced to
   512px in and stretched back out at composite. Now the adapter picks the
   canvas from the examiner's own face measurement (512 / 640 / 768; override
   `engine.crop_size`), so a big Gojo close-up keeps native detail while small
   faces still upscale. `byrdfacezone prepare --canvas-size` carries it.
2. **One candidate per GPU submit** — the founder picks best-of anyway, so the
   v3 graph now batches N candidates through ONE submit (RepeatLatentBatch:
   encode once, sample N; `engine.batch`, clamped 1–4 for the 8GB card) and the
   adapter downloads + composites + cards EVERY candidate (`candidate x/N` on
   the card) instead of discarding all but the first output.
3. **Adapter discarded extra outputs** — fixed with (2); zone_record now lists
   `generated_crops`/`finals` per candidate.

Known flow items, staged (small steps, in order):

- **Ladder auto-fallback conductor**: examiner's `recommended_lane` exists; a
  parent_id job chain (columns already migrated) could run main lane → judge →
  next rung automatically on rejection. Greenlight-gated: changes creative output flow.
- **v3 canny sparsity off the warp**: the tone-matched (un-warped) forehead
  region has weak edges, so ControlNet holds less there — if hardware tests
  show forehead drift, blend target structural edges into the canny input
  outside the identity core.
- **Group-photo macro**: examine reports every face; a per-face loop
  (`facelab.ps1 quality -FaceIndex N` per operable face) can become one belt
  job that fans out per face and composites sequentially into the same target.
- v2 two-pass graph left untouched (proven + suite-locked); batching lands
  there only after v3's batch path proves out on hardware.

## Staged 2026-07-15 (avenues): two more ways to the same result (UNTESTED on hardware)

Founder rule: the main plan carries 3–5 backups; avenues ride as per-job
parameters (`engine.workflow`, `facelab.ps1 quality -Workflow ...`) so the
proven default never moves while new ways get tested.

- **Avenue A `sd15_face_zone_diffdiff_api.json`** — v3 guided + core
  `DifferentialDiffusion`: the graded mask becomes a per-pixel denoise strength
  map (full rebuild at the face core, feather at the boundary ring). This is
  the community's standard inpaint-seam fix, aimed squarely at the jaw/ear
  seam that failed the visual gate. Zero new models.
- **Avenue B `sd15_face_zone_ipadapter_api.json`** — v3 guided + IP-Adapter
  PLUS FACE conditioning from a REAL identity photo (`engine.identity_photo`,
  else the reviewed reference). CLIP-embedding based (h94, Apache-2.0) — not
  the insightface FaceID variant, so it stays funded-lane-eligible. Gives
  identity a third anchor (seed pixels + LoRA + photo embedding) while no LoRA
  candidate is approved. Models: ip-adapter-plus-face_sd15 + SD1.5 CLIP-ViT-H
  image encoder.
- PhotoMaker (SDXL, Codex's smoke assets already on the branch) is the D
  avenue: license + VRAM verify before any funded use.
- Hardware test order: rerun the Gojo/Vegeta pair per avenue (A, then B, then
  A+B judgment call), batch 2, canvas auto; record verdicts here.

Parser replacement candidates for the ParseNet license gap (both LICENSE-UNVERIFIED
— treat exactly like ParseNet, private local evaluation only, until the license is
confirmed): `jonathandinu/face-parsing` (SegFormer/CelebAMask-HQ via HF
transformers, strong on real photos) and `skytnt/anime-seg` (anime character
matting — a hair/character matte source for anime targets).

## Current CPU face-zone state

The permanent target-edit architecture is **upload -> CPU 478-point mesh + semantic parser -> neck-connected face/head/ears above the neck minus hair/headwear/accessories/clothing -> CPU Carey-reference triangle warp -> CPU-only seed/composite when that looks better than GPU cleanup -> CPU soft composite -> card/review**. Its detailed handoff is [`FACE_ZONE_EDIT_WORKFLOW.md`](FACE_ZONE_EDIT_WORKFLOW.md). The belt works end to end, and the CPU crop preflight now expands and re-audits clipped head/neck envelopes before any GPU work. For the current v2 lane, CPU-only seed finishing is the preferred default because the GPU cleanup degraded the hard target. This is still not a quality or deployment approval.

- The CPU tool is `scripts/byrdfacezone.py`; the belt adapter is `scripts/byrdimage.py` (`edit_face_zone`); the worker route is `scripts/worker.py` (`face_zone_identity_edit`).
- Recipe: `recipes/anime_face_zone_edit.v1.json`. Current GPU workflow: `workflows/sd15_face_mesh_seed_refine_api.json` (`VAEEncode` + `SetLatentNoiseMask`). The older `workflows/sd15_face_zone_inpaint_api.json` is only the no-reference fallback.
- The mesh model is `Generators/ComfyUI/models/detection/mediapipe_face_fp32.safetensors`, 5,423,900 bytes (5.42 MB), SHA-256 `a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a`.
- The preferred semantic model is Google's `selfie_multiclass_256x256.tflite`, 16,371,837 bytes, SHA-256 `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`, Apache-2.0. It works on real photos but does not reliably recognize anime.
- The current anime fallback is `parsing_parsenet.pth`, 85,331,193 bytes, SHA-256 `3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2`. It is **private-local-evaluation-only** and requires a deployment license review/replacement before any funded, commercial, public, or redistributed lane.
- Do not replace the semantic route with a rectangle editor. The CLI `--manual-box` is a reviewed recovery fallback that records `manual_zone: true`; it is not a normal UI edit mode. Stop rather than silently guessing when semantic confidence fails.
- Reviewed preset references: Gojo -> `002_naruto.png`; Vegeta -> `013_yu-yu-hakusho.png`; Luffy close/full -> `003_one-piece.png`, all under `profiles/me/references/generated_anime_cartoon/`.
- The Naruto-seeded Gojo job `face_mesh_gojo_naruto_d38_m60` completed with 854 triangles and 88.008% edit-zone coverage. Output: `artifacts/image_lab/2026-07/20260714_anime_face_zone_edit_face_mesh_gojo_naruto_d38_m60_00001_.png`. It proves the architecture and identity/color transfer, but **fails** visual quality for the eye/artifact/ear/seam defects above.\n- The hard Vegeta CPU reroute `vegeta_crop_reroute_jaw_fit_foundation_06` successfully expanded the crop from `x=212,y=42,w=288,h=288` after one reroute (`crop_preflight.reroutes = 1`) and passed the full neck-to-head analysis before GPU work.\n- The local CPU-only rerun `job_19f644b00fbkrcxdf` completed with `skip_gpu_cleanup = true` and archived the better-looking seed/composite path for the hard Vegeta target.
- Current preview candidate: `artifacts/lora/candidates/carey_meina_sd15_expanded_hybrid_r32_20260714_125628-step00001200.safetensors`, rank 32 / step 1,200, SHA-256 `ad5d34e32d32099a6f0f813064dc62fdccd0b429b89ff415b0ba17e83e78fc13`. Preview only; never deployed.
- All support references are audited: generated animation/cartoon IDs `001-100` and synthetic-photoreal IDs `101-200`. They remain support material, not automatic approval of any LoRA.

## What is working locally

- GAMING hardware: RTX 3070 8 GB, 32 GB RAM.
- Base: `Meina V5.1 - Baked VAE.safetensors` (SD 1.5, 2.13 GB), SHA-256 `b4cca998e3be0c9c757527d77691d335cd194998aa845a798a68923f9a2d92ba`.
- ComfyUI runs locally at `http://127.0.0.1:8188` with dynamic VRAM. It is currently open in a visible PowerShell window.
- Local dashboard/router is open at `http://127.0.0.1:8787` for visual workflow review. It is a GAMING-local display instance; `byrd-mini` is still not resolvable, so the actual two-PC handoff is not yet live.
- Target route: `Dashboard upload → router artifact → GAMING worker → target_identity_edit → local ComfyUI → card/artifact → review`.
- Target graph: `workflows/sd15_anime_target_identity_api.json`.
- Recipe: `recipes/anime_face_edit.v1.json`; calibrated targets are Gojo, Vegeta, Luffy close, and Luffy full.
- Permanent face-zone graph: `workflows/sd15_face_mesh_seed_refine_api.json`; recipe: `recipes/anime_face_zone_edit.v1.json`; see `docs/FACE_ZONE_EDIT_WORKFLOW.md`.
- Isolated trainer: `Generators/sd-scripts/` v0.11.1 in its own venv; it passed local CUDA training without changing ComfyUI.
- `python tests/integration_test.py` passed locally after the image-lane changes and again after the hybrid/studio/PhotoMaker experiments on 2026-07-14.

## Policy and architecture

- Keep production jobs on the audited `image.generate` belt. Do not create a direct-Comfy production bypass.
- Do not use ReActor, ReSwapper, or IP-Adapter FaceID in the funded/public lane: they rely on InsightFace research/non-commercial face-recognition dependencies.
- The intended compliant lane is an owner-authorized SD1.5 identity LoRA with trigger `careybh person`.
- The supplied Gojo/Vegeta/Luffy images are **evaluation targets only**; never train an identity model on them.
- Generated anime/cartoon references never replace real-photo facial geometry. They may only be used as a separately weighted, user-approved style-support bucket after visual review.

## Reference set and staging rules

The private Carey-only source folders are:

- `profiles/me/references`
- `profiles/me/references/generated_anime_cartoon`
- `profiles/me/references/generated_real_photos`

Current strong real-photo set selected by `scripts/prepare-carey-lora-dataset.py`:

`me_photo_01`, `02`, `03`, `04`, `05`, `07`, `09`, `11`, `12`, `13`, `14`, `15`, `19`

- `06`, `08`, and `17` are optional only: cap/hard shadow, washed/redundant, or reflective glasses.
- `10`, `16`, `18`, and `20` are excluded: tiny face, motion softness, blur/hand distraction, or soft cluttered framing.
- `me_photo_21` and `22` are clean synthetic studio anchors used by the current photoreal generation stream; do not label them as camera ground truth.
- The six `ai_identity_*.png` studio portraits are synthetic, not real-photo anchors. They are useful as carefully weighted angle-support material.
- The animation library IDs `001-100` and synthetic-photoreal IDs `101-200` are complete and audited. They remain separately labeled support material; generated images never become camera-photo ground truth.

Current staged real-only dataset:

- `profiles/me/lora_dataset/identity/10_careybh`
- 13 camera originals + 26 visually verified tight/medium face crops = **39 training images**, repeat 10.
- Face crops are created by `scripts/build-carey-face-crops.py` using local OpenCV. All 26 current crops were visually checked on `artifacts/image_lab/2026-07/carey_identity_real_crops_20260714.png`; the fallback crop for braided photo 03 is also correct.

Current staged hybrid diagnostic dataset:

- `profiles/me/lora_dataset/anime-mix/5_careybh_real`: 8 real originals + 16 face crops, repeat 5.
- `profiles/me/lora_dataset/anime-mix/3_careybh_studio`: 6 generated studio-angle portraits, repeat 3.
- `profiles/me/lora_dataset/anime-mix/2_careybh_anime`: 18 visually reviewed, user-owned anime portraits, repeat 2.
- The weighted loader reports 174 effective samples. Real material remains 69% of each epoch; studio and anime assets are supporting signals only.

Current staged studio-core diagnostic dataset:

- `profiles/me/lora_dataset/studio-core/5_careybh_real`: 8 real originals + 16 verified face crops, repeat 5.
- `profiles/me/lora_dataset/studio-core/6_careybh_studio`: 6 clean studio identity views + 12 verified face crops, repeat 6.
- The weighted loader will report 228 effective samples. This deliberately removes anime scenes and gives facial geometry from clean studio views near-equal exposure to the real-photo bucket.
- A local 20-step U-Net + text-encoder smoke test completed at 2026-07-14 01:59 EDT without memory or loader errors. Its 18.11 MB file is a smoke artifact only, not a quality candidate.

## Training launcher status

`scripts/train-carey-meina-lora.ps1` is now reliable on this machine:

- `-FaceCrops` stages face-focused 512 px training images.
- `-TrainTextEncoder` removes `--network_train_unet_only` and adds `--text_encoder_lr 5e-5`.
- Comfy stop confirmation no longer treats an expected offline connection as fatal.
- LM Studio's harmless “no models to unload” stderr no longer aborts training.
- Accelerate's harmless defaults notice no longer aborts training; native exit code is checked explicitly.

Use a 10-step text-encoder smoke test before changing base model/rank/hardware. It passed on the RTX 3070. The new weighted hybrid data path also completed a 20-step GPU smoke test at 2026-07-13 23:42 EDT: 174 effective samples, 72 text-encoder modules, 192 U-Net modules, 18.11 MB candidate. It is a parser/VRAM proof only, never a quality candidate.

## Candidate test record — rejected and pending

| Candidate | Dataset / training | Result |
|---|---|---|
| `carey_meina_sd15_anime_mix_20260713_204036.safetensors` | 6 real + 9 anime, U-Net only, 300 steps | Generic Gojo; reject. |
| `carey_meina_sd15_identity_20260713_210157.safetensors` | 8 earlier real selection, U-Net only, 650 steps | Generic face at normal strength; distorted generic face at high strength; reject. |
| `carey_meina_sd15_identity_20260713_213808.safetensors` | 6 strong real + 12 crops, U-Net only, 700 steps | Generic targets; reject. |
| `carey_meina_sd15_identity_20260713_215809.safetensors` | 6 strong real + 12 crops, U-Net + text encoder, 700 steps | Correct text encoder tensors, but still generic targets; reject. |
| `carey_meina_sd15_identity_20260713_221853.safetensors` | 8 strong real + 16 crops, U-Net + text encoder, 900 steps | 792 tensors / 216 text-encoder tensors / 24 images; Gojo, Vegeta, both Luffys, and high-influence Gojo all remain generic; reject. |
| `carey_meina_sd15_anime_mix_20260714_000944.safetensors` | 8 real + 16 real crops (repeat 5), 6 studio views (repeat 3), 18 reviewed anime portraits (repeat 2), U-Net + text encoder, 1,200 steps | All four normal targets remain target-like/generic. High-influence Gojo shifts toward broad Black-male facial features, but not recognizably Carey; reject. |
| `carey_meina_sd15_studio_core_20260714_020203.safetensors` | 8 real + 16 real crops (repeat 5), 6 clean studio views + 12 studio crops (repeat 6), U-Net + text encoder, 1,200 steps | Gojo at 600, 800, 1,000, and 1,200 steps produces nearly the same generic altered face; reject before wasting the remaining three target runs. |
| `carey_meina_sd15_identity_20260714_044058.safetensors` | 13 camera originals + 26 verified face crops, per-photo variable captions, U-Net + text encoder, rank/alpha 16, 1,600 steps / 5 epochs | Target-free 1,200-1,600 gates learn a consistent Carey-like photoreal face. Normal masked anime edits remain generic; high-denoise edits paste photo appearance/backgrounds. Split model/CLIP strengths restore anime style but lose too much identity. Retain as private teacher/evaluation candidate; do not deploy. |
| `carey_meina_sd15_expanded_hybrid_r32_20260714_125628-step00001200.safetensors` | Expanded hybrid support set, U-Net + text encoder, rank/alpha 32, step 1,200 | Private preview only. LoRA-only semantic edits remain generic/light or add face text. Naruto mesh seeding transfers identity/color, but the d0.38 Gojo output fails on eye distortion, piercing-like artifacts, pale ear, and jaw/ear seam. Never deploy or promote from this result. |

Latest rejected candidate metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_identity_20260713_221853.safetensors`
- SHA-256: `88C6612386D89E716E7F0E920E7A469A8D2644FAF4B5CD02578B41D3D0C71007`
- 900 steps, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder).
- Temporary Comfy preview: `carey_meina_sd15_identity_te_8real_preview.safetensors`; preview only, never deploy.

Important discovery: earlier U-Net-only candidates had exactly zero `lora_te*` tensors. The text-encoder change fixed that technical defect, but did not make the limited source set sufficiently recognizable.

The direct text-to-image portrait diagnostic also produced only a plausible generic person with broad traits, confirming that this is not solely a target-mask issue.

PhotoMaker V2 was assessed and rejected before installation: the built-in Comfy nodes are V1-only, the V2 route requires InsightFace licensing, and official guidance calls for at least 11 GB VRAM. A partial 1.8 GB adapter download was stopped and removed completely; it is not in the project model path.

Latest rejected hybrid metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_anime_mix_20260714_000944.safetensors`
- SHA-256: `3E22C6924A9C923079514A07EB11C73132B5ED73959DBCBE88FAF4E6B3BD02A1`
- 1,200 steps, seven epochs, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder).
- Fixed-seed normal validation report: `artifacts/image_lab/2026-07/validation_hybrid_1200_20260714_011444.json`; high-influence report: `validation_hybrid_1200_boundary_20260714_014740.json`.

Latest rejected studio-core metadata:

- File: `artifacts/lora/candidates/carey_meina_sd15_studio_core_20260714_020203.safetensors`
- SHA-256: `5588BEBAD2BCEBB3B6050D124EF0432AB85E5B480ACE8DC32C31956763224062`
- 1,200 steps, six epochs, rank/alpha 16, `ss_text_encoder_lr=5e-05`, 792 tensors (576 U-Net + 216 text encoder); data buckets: 24 real/crop images ×5 and 18 studio/studio-crop images ×6.
- Gojo checkpoint-selection reports: `validation_studio_600_20260714_022156.json`, `validation_studio_800_20260714_022159.json`, `validation_studio_1000_20260714_022202.json`, and `validation_studio_1200_20260714_022206.json`.

PhotoMaker V1 private test:

- Official `TencentARC/PhotoMaker` V1 is Apache-2.0, direct-reference, and its 890.8 MB `photomaker-v1.bin` is present under `Generators/ComfyUI/models/photomaker/`.
- The built-in Comfy V1 nodes load without InsightFace. A private, non-app 512 px masked Gojo smoke ran at roughly 7.0 GB GPU memory, but the face output was corrupted/unusable (`artifacts/image_lab/2026-07/private_gojo_smoke_00001_.png`).
- Official PhotoMaker guidance lists 11 GB minimum; do not route V1 to the 8 GB worker. Retain the adapter only as an explicitly disabled future-hardware option.
- All temporary Carey preview copies were removed from `Generators/ComfyUI/models/loras`; the application has no active Carey identity candidate.

## Next gate — do not skip

1. Fix the Naruto-seeded Gojo cleanup defects: distorted eye, piercing-like artifacts, pale target ear, and hard jaw/ear skin seam. Re-run with the same saved semantic/mesh evidence so changes are attributable.
2. Only after Gojo passes identity, integration, and preservation, run Vegeta (`013_yu-yu-hakusho.png`) and both Luffys (`003_one-piece.png`). A single attractive crop is not enough.
3. Keep the audited IDs `001-100` and `101-200` in separate buckets. Camera photos remain ground truth; synthetic-real and animation images are support material only.
4. Do not deploy the rank-16 teacher, the rank-32 preview, or any generated-real-only derivative. A pass requires recognizable Carey identity, native anime integration, and preservation outside the saved soft zone.
5. Before any public/funded deployment, independently verify the provenance and license of `Meina V5.1 - Baked VAE.safetensors`; it is currently a private test checkpoint, not an approved public checkpoint.
6. Replace or explicitly clear the ParseNet anime fallback before funded/public deployment. If further conditioning is needed, evaluate another **license-compatible** reference-conditioning model or higher-VRAM worker before downloading/installing it; do not silently introduce InsightFace FaceID components into the funded lane.

## Exact validation settings

- Current mesh-seed baseline: 22 steps, CFG 5.0, denoise 0.38, LoRA model strength 0.60 / CLIP strength 0.75.
- Naruto-seeded Gojo baseline: seed `7124`, 854 triangles, 88.008% edit-zone coverage. It is a failed calibration baseline, not approval evidence.
- Earlier LoRA-only target diagnostics used identity strength `0.90`, 18 steps, CFG 6.0, denoise 0.48; the Gojo boundary test used identity strength `1.25`, 22 steps, CFG 6.0, denoise 0.60.
- Fixed seeds: Gojo `7124`, Vegeta `7125`, Luffy close `7126`, Luffy full `7127`, high-influence Gojo `7133`.
- A candidate must visibly read as Carey in normal target renders; a high-influence artifact is diagnostic evidence only, never a pass.
- Rank-16 split-strength diagnostics added separate `strength_model` / `strength_clip` support to `scripts/byrdimage.py`; this is an experimental calibration control, not evidence of approval.


