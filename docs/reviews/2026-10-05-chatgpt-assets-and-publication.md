# ChatGPT asset fallback and Windows source publication

**Latest constraint:** Carey subsequently required all future episode production
to run 100% locally with no subscriptions or paid services. Stop further cloud
generation. Retain the assets already saved and continue with local rigging,
animation, compositing and measured Radeon inference. The earlier ChatGPT
fallback authorization is superseded for future generation.

Carey authorized ChatGPT tools for assets that did not pass local generation,
and requested publishing the post-CUDA updates to GitHub. The current GPU is
the RX 7900 XT with ROCm; historical CUDA/NVIDIA instructions are not the active
machine configuration. Continue the existing deployment rather than reinstalling.

## New locally saved assets

- `D:\ByrdHouse\assets\characters\carey-anime\expressions-v1-candidate.png`
  has six labeled expressions: neutral, closed smile, skeptical, concerned,
  delighted and blink. Its JSON card records ChatGPT provenance and review status.
- `D:\ByrdHouse\assets\locations\brambleton\stoop\carey-stoop-v1-candidate.png`
  places Carey on the recurring teal-door brick stoop, with a closed-mouth
  skeptical expression. Its JSON card preserves the full generation prompt.
  SHA-256: `38f458c6623f2725b14cdcf7b51645651ddbe60bfd0040efaab548a80bd8f0ef`.

These were generated with the built-in ChatGPT image tool using the approved
Carey anchor and reference artwork. They are **needs_review**; the approved
anchor and turnarounds were not overwritten. Clothing remains a placeholder.
The expression sheet has readable separate expressions. The stoop background
is more painterly/textured than the flat character reference and needs a style
decision before becoming the recurring set. No exact-identity claim is made.
ChatGPT generation is not evidence of successful local diffusion generation.
The images and original photo library remain on the PC, outside this public kit.

## Unfinished mesh cleanup experiment

The source-only `mesh_cleanup.py` bridge and `/api/mesh-cleanups` route are
experimental and not deployed to the running Studio. The CPU basketball trial
`carey_basketball_mesh_trial_20261004_01` completed preparation but shows a visible
forehead seam, neck mismatch and noncanonical target hair. It is unsuitable as
an episode frame. GPU cleanup has not been qualified. Private ParseNet use
keeps this experiment in local evaluation only. Do not promote its numeric
coverage gates to visual approval.

Publication validation: the Studio suite passed all 190 tests (7.320 seconds
reported test time). The historical belt integration suite also passed all
checks with PYTHONIOENCODING=utf-8. The initial cp1252 preflight-output failure
did not recur. Logs are retained in the local external/workflows/
carey-mesh-edit-qualification folder as publication-studio-tests.log and
publication-belt-tests.log. These are CPU/mock tests, not new GPU qualification.

## Continue from here

1. Keep the approved Carey anchor/body/head sheets as canon; review expressions.
2. Finish the likeness workbook using actual reference observations and editable
   review states; do not fabricate identity percentages.
3. Build reusable Brambleton scene plates and a short scene using accepted art.
4. Inspect the existing Blender files before selecting an existing rigged-body
   route. Existing still-plane camera animatics are not an editable 3D body.
5. Qualify facial/body motion and retain every frame for continuity review.
6. Train or qualify the local repeatable identity route only with accepted art.

The local Wan preview works but still has mouth softness and temporal review
flags. A production-quality 3D Carey rig, approved local identity LoRA and
finished episode animation remain outstanding. Sources for earlier experiments
and exact hardware tests are indexed in this directory's README.
