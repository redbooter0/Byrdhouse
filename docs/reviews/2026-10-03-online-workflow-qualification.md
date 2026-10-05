# Online workflow qualification and canonical scene preservation

**Date:** 2026-10-03
**Machine:** Windows; i9-10850K; Radeon RX 7900 XT 20 GB; 32 GB RAM
**Goal:** reuse proven public ComfyUI patterns for a Carey-consistent animated
show rather than inventing an untested image stack.

## Sources staged locally

| Source | License / pinned local copy | What was qualified |
|---|---|---|
| [ComfyUI Img2Img Workflow](https://github.com/ayushchinmay/ComfyUI_Img2Img_Workflow) | Apache-2.0; `D:\ByrdHouse\external\ComfyUI_Img2Img_Workflow`; commit `2be98e6b6aff069a51f989cd855c4f5345906931` | Start from the supplied image latent instead of empty noise; then make controlled changes. |
| [AnimeFix-Workflow](https://github.com/ExMikuPro/AnimeFix-Workflow) | MIT; `D:\ByrdHouse\external\AnimeFix-Workflow`; commit `4caa3dd4d3a0ccb84a6696f52af5a6a6facdbb44` | Its staged refine design: base image → face detail → output. Existing local Impact Pack, YOLO face detector, and SAM support its face-detail subset. |
| [Anime character-sheet workflow discussion](https://www.reddit.com/r/comfyui/comments/1ka63v2/anime_focused_character_sheet_creator_workflow/) | Community workflow post | Anchor first, keep sampling settings stable, refine/upscale the selected anchor, then make the sheet. |

No new model was installed for this qualification. Animagine XL 4.0 Opt and the
existing IP-Adapter/ControlNet/SAM/face-detector stack were already recorded in
the model manifest.

## What failed and was disabled

The AnimeFix-compatible local FaceDetailer subset completed technically in job
`3a06290e6e71c7956044964485651edd` (67.91 s). It enlarged/smoothed the afro
and changed the approved face. Its local anchor similarity cue was `0.133730`.
This output is rejected and the optional `anime_face_detailer` setting remains
`false`. A completed graph is not a continuity pass.

## What worked

The production anime-anchor route now uses the locked Anchor v1 image as the
VAE latent rather than an empty latent. Job `346b554dc7bf47f8c986aa08aec35729`
completed in 50.31 seconds and closely reproduced the visual canon. Its
read-only cue was `0.876475`; automated hair/forehead gates remained false
because the parser cannot reliably evaluate the illustrated curl boundary.
The frame stays in review and is not a claim of biometric identity.

The existing source-preservation mask/composite lane was extended only for the
explicitly locked `carey-anime-anchor` source. The scene change route follows
this sequence:

1. Freeze Anchor v1 and create parser/BiRefNet masks.
2. Review the person cutout before any scene render.
3. Inpaint just the background with Animagine and an environment-only prompt.
4. Composite the frozen anchor core back over the result.
5. Verify saved RGB equality inside that core and leave the result in review.

The mask job `e492eaaf5bae4edb96d5553a9247b43e` completed in 11.28 seconds and
visually covered the afro, face, beard, shirt, and shoulder silhouette.

The first Brambleton test `ab663a1332a3851212f851338e81ffdd` proved exact core
preservation but showed a pale outline at the afro edge, so it is rejected.
The follow-up `26e31a04331739f4bd13346c1274d8c5` used a stronger -8 px alpha
edge shrink and completed in 18.56 seconds. Its audit reports:

| Measurement | Value |
|---|---:|
| Semantic core pixels | 499,269 |
| Changed semantic-core pixels | 0 |
| Maximum semantic-core channel difference | 0 |
| Background pixels changed | 231,775 |
| Alpha-edge pixels changed | 100,310 |

This is a strong route for different **backgrounds at the locked source pose**.
It does not make a new pose, prove the matte seamless, or authorize animation.
The current frame remains `needs_review` in Studio; inspect the afro boundary at
full scale before keeping it.

## Next disciplined move

Use the source-latent route to make and review a small anchor kit: close front,
left/right three-quarter, profile, expression, and full body. Only selected
frames become LoRA training data or future pose references. Rejected renders
are never promoted to the kit. After that, use the locked-cutout scene route
for backgrounds and the reviewed pose route for shots that genuinely need a
new body position.

## Illustrated hair parsing correction

The local CPU examiner originally reported an empty hairline on the approved
anime anchor even though the ComfyUI face-parsing workflow visibly segmented
the full afro. Inspection of the upstream parser output showed why: its
photo-trained taxonomy labeled the illustrated afro mostly as `hat` (class 14)
rather than `hair` (class 13). The belt now records both raw areas and uses
their union only as the **visible hair silhouette** for illustrated-continuity
review. This restores measurable forehead height, hairline span, afro width,
and afro height without pretending the parser can prove identity or decide
whether a real-world hat is hair.
