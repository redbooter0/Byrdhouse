# Connected hairline measurements and existing CPU face-mesh restoration

Date: 2026-10-04. Current Windows RX 7900 XT PC. This follows the
[complete-frame Studio review](2026-10-04-studio-continuity-review-validation.md)
and advances the requested face/hair/forehead examiner and target-alignment
foundation. It does not claim a finished Carey face swap or approved episode.

## Implemented and deployed

The installed photo-trained SegFormer sometimes labels illustrated eyebrow
patches as hair/headwear. The old column scan took the lowest hair-to-skin
transition above the eyes, including detached brow patches. Its median could
look reasonable while individual points were misplaced. This is why an
apparently passing forehead screen was insufficient for edit guidance.

`identity_belt.py` now uses existing OpenCV connected components on the same
semantic labels. It selects the sufficiently large component with strongest
contact in the detected forehead cap. Detached components are excluded from
head-hair measurements, with raw label areas and excluded counts retained.
No semantic pixels are dilated or bridged. Missing eye landmarks or a missing
head-hair/skin boundary produces an absent measurement. This changes an
examiner; it does not alter source artwork or generate a replacement face.

The author's [label definitions](https://huggingface.co/jonathandinu/face-parsing)
confirm separate skin, brows, hair and hat classes. The existing model is still
private research/qualification under its recorded non-commercial terms. Its
classification of an illustrated afro as hat remains explicitly reported and
is handled only in illustrated review; photographic headwear is not hair.

Measurement version: `carey-features-v2-connected-head-hair`.
New CPU review jobs freeze code hashes for the examiner, matching-view
operator, queue adapter and visual renderer, plus existing parser/detector/
landmark weight and configuration hashes. Changed code/weights after queueing,
or before publication, are refused. Partial reports must match the measurement
version and immutable input/checkpoint records. Older completed reports remain
historical evidence; incomplete jobs cannot silently mix V1 and V2 findings.

The old approved-anchor measurement profile is unchanged. New measurements
are saved separately as
`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1-profile-v2.json`,
with the old profile hash, same approved-artwork hash and new examiner binding.
The live config selects this V2 profile. Profile validation refuses mismatched
versions or examiner bindings. Carey’s approved anchor/sheets and wardrobe
decision are unchanged; only measurement provenance advances.

## Local calibration and actual clip check

Seven fixed sources were inspected with the installed CPU models: approved
anchor/front/two side views, Wan frames 5/7 and the rejected CivitAI portrait.
The legacy algorithm was replayed on identical saved semantic labels for the
comparison. Actual V2 records retain original RGB skin measurements and face
landmarks; label replay was used to compare boundary localization only.

| Source | V1 boundary point range, pixels | V2 range | V2 coverage |
|---|---|---|---:|
| Approved close-up anchor | 156–290 | 156–290 | 1.000 |
| Wan frame 5 | 67–192 | 67–134 | 1.000 |
| Wan frame 7 | 71–193 | 71–136 | 1.000 |
| Rejected new-scene portrait | 239–403 | 239–316 | 1.000 |
| Approved front crop | 106–150 | 106–150 | 1.000 |
| Approved facing-right crop | 129–256 | 129–256 | 0.805 |
| Approved facing-left crop | 128–225 | 128–225 | 0.522 |

The anchor median remains 173 px. Frame 5 excludes 415 semantic pixels from
head-hair measurements; frame 7 excludes 319. In frame 7 the median changes
from 82 to 80 px. The two profile boundaries remain measurable but are less
complete than the front; do not infer a full visible hairline from coverage.
Before/after and profile overlays were visually inspected. Some connected
beard/sideburn labels remain in profile silhouettes, so silhouette height is
still a matching-view review cue, not a perfect afro-only segmentation.

Live queue review `3bbf35932e789a0c427faec1fabfa4d2` examined all **33** saved
Wan frames in **271.37 seconds** worker time (272 s displayed wall duration).
The two borderline afro-width flags remain frames **5 and 7**. Other measured
feature groups have no change flags; this does not approve eyes, teeth, mouth,
expression or exact identity. The clip remains `needs_review`.

Live review `279548b6036ef1d2bad7f9b54fc1e8f6` checked the rejected CivitAI
portrait in **10.84 seconds**. All six feature groups still flag changes.
Its source remains rejected. Neither review submitted a Comfy prompt. All
33 source-frame hashes, source approvals and approved-anchor/profile hashes
were verified; there was no new animation render. Studio's browser displayed
both loaded diagnostic images, completed counts and read-only report links.

## Reused face-mesh foundation restored on this PC

The existing `scripts/byrdfacezone.py` loader already uses ComfyUI's native
CPU MediaPipe implementation. Its missing 5.42 MB official model was restored
with the installed Hugging Face CLI; no Python package or CUDA node was added.

- Source: [Comfy-Org/mediapipe](https://huggingface.co/Comfy-Org/mediapipe/tree/f787efc1ad99492ec7d5b6564c0dd6c48d84ee49),
  revision `f787efc1ad99492ec7d5b6564c0dd6c48d84ee49`.
- File: `detection/mediapipe_face_fp32.safetensors`, **5,423,900 bytes**,
  SHA-256 `a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a`.
- License: Apache-2.0, recorded before download in the model manifest.
- Primary copy: `D:\ByrdHouse\models\detection`; small runtime copy:
  `C:\Users\carey\Documents\ByrdHouse\ComfyUI\models\detection`.

The original helper assumed `root/Generators/ComfyUI`. Its model resolver now
reads the current root's `byrdhouse-local.json` and configured `comfy_dir`,
including relative-path resolution. Historical roots retain their existing
layout. Invalid current configuration stops rather than guessing a fallback.

Direct probes returned **478 finite landmarks** on the approved anchor, front
and facing-right reference. Detector scores were 0.8807, 0.9034 and 0.7589;
warm inference observations were 0.0774, 0.0300 and 0.0310 seconds. These are
small local measurements excluding process startup, not an overall edit-speed
benchmark or identity confidence. Model parameters were verified on CPU.
The existing CLI's normal `analyze` command now succeeds against `--root
D:\ByrdHouse`, reporting 0.35 seconds analysis time and saving its report
and overview. No manual rectangle or face-zone edit was used.

The mesh's oval does not fully reach the approved high forehead/hair boundary;
the semantic examiner remains necessary. The old feature plan also preserves
target eyes/hair by default. Those legacy defaults are not a validated Carey
episode identity policy. Full preparation still needs current semantic-model
availability/license review, explicit feature selection, reviewed-reference
warping, clean eyes/ears/mouth and protected-pixel checks. No warp/GPU cleanup,
trained LoRA, rig or final animated likeness was qualified by this probe.

## Validation, saved evidence and rollback

The full Studio/CPU suite passes **183 tests**: four boundary tests cover
detached brows, curved connected hair, absent evidence and unrelated hair;
two queue cases refuse changed weights/old-version resume; profile validation
covers version/binding changes; four path tests cover current/historical roots
and invalid configuration. Existing complete-frame and source-preservation
checks still pass. Five deployed/source Studio file hashes match.

Evidence directory: `D:\ByrdHouse\external\workflows\carey-hairline-v2`.
Key files: `calibration-v2.json`, `before-after-validation.json`,
`hairline-before-after-frame5.png` and its sidecar, `deployed-validation.json`,
both deployed full reports, `face-mesh-download-plan.json`,
`face-mesh-local-probe.json`, and `existing-facezone-examiner.json/png`.
`evidence-files.json` indexes the retained files by hash and verifies seven
original sources and both pinned mesh-model copies. Calibration image/label
sidecars record their diagnostic purpose; they do not reclassify old findings
as new inference or make the diagnostic images animation inputs.

Backup: `D:\ByrdHouse\backups\2026-10-04-hairline-v2`, containing prior
Studio files/config and the tracked prior face-zone helper. Deployment
restarted only idle Studio (new PID **18188**); Comfy PID **24148** remained
unchanged. Final queues were empty. Roll back Studio files/config together
to use the old profile and algorithm; retain both profiles, old/new review
evidence and approved artwork. The new mesh weights are inert unless invoked.

Next actual production gate remains a target-aligned Carey edit through the
existing mesh/semantic workflow, with clear eyes/mouth, exact protected pixels
and visual acceptance before animation. The larger stills/shorts/episodes goal
remains active.
