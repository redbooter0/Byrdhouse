# ByrdHouse progress ledger

**Purpose:** persistent handoff for the Windows RX 7900 XT studio. Update this
file whenever an asset, model, workflow, evidence record, or production decision
changes. This is the source for continuing work without repeating failed tests.

**Last updated:** 2026-10-04

## Latest advance: connected hairline V2 and existing CPU mesh restored

Detached eyebrow/hair-label components are excluded from head-hair review.
Seven fixed sources were calibrated and all 33 Wan frames checked live under
bound V2 code/weights. Afro-width cues remain at 5/7; the rejected portrait
still flags all six groups. Approved artwork and the V1 profile are preserved;
the live configuration selects a separately saved V2 profile. Existing CPU
478-point MediaPipe loading and normal CLI analysis now work after restoring
the small official model and correcting the current-PC model lookup.
183 tests pass. GPU runtime/Comfy PID unchanged; no edit/warp or new render.
Saved [the detailed calibration/deployment record](reviews/2026-10-04-hairline-v2-and-face-mesh.md).

FreeVideo follow-up checked upstream `a9098b7…` and saved 13 hash-bound source
snapshots, the four-commit diff, two separate Radeon H3 implementation records
and the publisher's standard territorial license. No AMD drop-in route was
established and no H3 deployment was made. Existing Wan movie decoded all
33 frames; movie/frame/approved-anchor hashes match, services are healthy and
queues empty. The preview remains `needs_review`. This is research/media
verification, not a new speed or exact-likeness milestone. See
[the follow-up](reviews/2026-10-04-freevideo-follow-up.md).

FreeVideo was source-reviewed after Carey's link: it targets NVIDIA/CUDA and
is not a qualified addition to this Windows AMD runtime. Source pin, hardware,
performance evidence and next steps are saved in
[the assessment](reviews/2026-10-04-freevideo-amd-assessment.md).
The CivitAI-derived new-scene lab is now deployed and tested; portrait
`15a745b5272cda3fe8c73f8b0ed41003` is rejected for changed facial features,
hair and lighter skin. The full Studio suite now passes 173 tests.

## Latest advance: matching-view checking and full-clip review in Studio

Existing illustrated stills and clips have a visible-angle selector and
**Check likeness** button. The existing examiner now runs in the shared queue
and exposes per-feature findings, an annotated diagnostic and hash-checked
full-frame evidence. It does not edit, approve or animate its source.
Diagnostics are excluded from animation sources. No new model or runtime was
installed. See [the deployment and live proof](reviews/2026-10-04-studio-continuity-review-validation.md).

All 33 saved Wan frames were checked. Borderline afro-width cues appeared at
zero-based frames 5 and 7, missed by the old five-frame sample. All other
measured feature screens had no change flags. The rejected CivitAI portrait
flagged all six feature groups. The clip still needs visual approval; no
exact-identity or mouth/eye-detail claim is implied by measured geometry.
The CPU check survived a live Studio restart with ten cached report hashes
unchanged and no GPU prompt. Full wall time was 298 s including restart;
the 194.46 s prototype timer measured only the resumed portion. Timing is
now displayed from recorded start/finish times. Gold edges are estimates;
some brow leakage still needs localization work. The suite passes 173 tests.

## Latest advance: local Wan 5B animation and measured AMD settings

The official upstream ComfyUI Wan 2.2 5B image-to-video template and three
verified model files are saved on D:. Existing Studio now exposes a scene
motion button and gallery video through the shared durable queue. Approved
Carey anchor job `3d6490df1abea740c499afcbca8befe7` rendered a 1.375-second
33-frame, 384x576, 24 fps candidate in 472.68 seconds. Browser media loaded;
five selected frames passed matching-view hair/forehead/outline screens, but
mouth softness/color fringing and complete temporal likeness remain for review.
It stays `needs_review`. Sources, hashes, metrics and all frames are retained in
[the native video review](reviews/2026-10-04-native-wan-amd-qualification.md).

Preserve the tested startup options: `--cache-ram 4 8`,
`--disable-async-offload`, and now `--disable-dynamic-vram`. Dynamic loading
failed before sampling; its static-memory retry succeeded. Do not enable
`COMFYUI_ENABLE_MIOPEN=1` from the headline of an older AMD speed report:
the identical local test took 694.64 s and raised sampled VRAM use from
17.54 to 19.66 GiB. That experiment was rolled back. Working-run sampled
whole-system RAM reached 30.01 GiB; higher presets remain unqualified.

Post-rollback SDXL scene regression `6048e11528ab334f6375f5c001377df8`
completed in 60.08 s Comfy execution and preserved all 499,269 Carey core
pixels. The existing thin pale afro edge remains a visual gate. The live
launcher now uses the trusted base Python plus the existing dependency folder,
so App Control does not force another install loop. Models/runtime unchanged.

## Latest advance: approved multi-view Carey reference and matching-view belt

Carey approved the front, profile, and rear illustrated model sheets as
looking like him, while rejecting their outfits as final wardrobe. The sheet
is locked by `turnaround-v1.json`; its head views are hash-checked in
`views-v2\manifest-v2.json`. Local front/profile detection succeeded. The
new read-only `anime_view_review.py` selects the matching approved view and
explicitly excludes wardrobe and automatic approval. A facing-right
same-file sanity check returned `1.0`; all 158 Studio tests passed.
The prior independent scene still scored `0.925440` against the correct
three-quarter anchor, with hair/forehead/outline screens passing. The wrong
straight-front baseline had falsely flagged its afro width. Its visible
compositing edge still needs review; no new still was approved.
This does **not** establish a new-scene likeness or animation readiness.
See [the multi-view record](reviews/2026-10-04-carey-multiview-belt.md).

## Latest advance: measured Carey Anime Canon belt — 2026-10-04

The approved Anchor v1 now has a hash-bound local measurement profile at
`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1-profile.json`.
The face parser classed the illustrated afro as `hat`; Studio now uses
`hair ∪ hat` only for illustrated continuity review and keeps real-photo hats
excluded. Same-view reports measure afro silhouette, hairline, forehead,
face outline, and median skin brightness, with `CHANGE` markers on large drift.
The faithful `346b…` redraw passed hair/forehead/outline screens; the rejected
`3a…` detailer failed all three and was `+46.936` brighter in median parsed
skin luminance. Both remain in their prior human-review states. The Studio
checks the saved profile and approved anchor hash before trusting a report.
The belt caches unchanged anchor inspections by file SHA256: `15.836 s` cold
for the first anchor pass versus `0.0019 s` for a repeated pass in the same
process. Three sampled frames (0, 22, 43) of the existing Anchor v1 motion
clip passed hair/forehead/outline screens with similarity near `0.908`, but
frame 22 visibly softened teeth/mustache lines. The clip remains `needs_review`.
See [the belt validation record](reviews/2026-10-04-anime-canon-belt-validation.md).

## Current production goal

Build **ByrdHouse**, an original adult animated sitcom for social-media shorts:
recognizable recurring town, original recurring cast, motivated cutaway gags,
and a visually consistent illustrated Carey. Produce approved still keyframes
first; only animate reviewed keyframes. See
[the show bible](BYRDHOUSE_ANIMATED_SHOW_BIBLE.md).

## Locked and accepted

| Item | Status | Evidence / location |
|---|---|---|
| Carey Anime Canon Anchor v1 | **Approved visual canon** | Owner-supplied image copied to `D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png`; SHA256 `2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`; machine-readable lock `anchor-v1.json`. |
| Carey anime reference registration | Registered in the live Studio | `D:\ByrdHouse\training\carey\references\manifest.json`, ID `carey-anime-anchor`; source is illustrated canon only, never a substitute for real Carey photography in photoreal likeness claims. |
| Carey Anime Canon Anchor v1 motion test | **Rendered; awaiting Carey review** | Job `0cf48a1d6a53295f53b4727bd0efb4e7`; 44-frame / 2.93-second local MP4, 205.72 s. Source hash matches Anchor v1. Sampled frames preserve the face design and afro; motion is a gentle blink and minor head shift. |
| Anime anchor image-to-image qualification | **Technically passed; visual review pending** | Job `346b554dc7bf47f8c986aa08aec35729`; 50.31 s. The locked anchor is now the starting SDXL latent, not empty noise. Read-only similarity `0.876475` is a review cue only. This establishes the likeness-preserving anchor-kit starting point. |
| Anime-anchor Brambleton scene swap | **Rejected for show art** | Job `26e31a04331739f4bd13346c1274d8c5` has 499,269 byte-identical semantic core pixels, but the visible pale halo around the afro fails visual review. |
| ChatGPT Carey turnaround kit | **Carey-approved illustrated likeness; outfits are placeholders** | Four full-body views and enlarged head views copied to stable `-v1.png` assets and hash-locked in `D:\ByrdHouse\assets\characters\carey-anime\turnaround-v1.json`. Carey said all models look exactly like him, then said he dislikes the outfits. See [turnaround review](reviews/2026-10-04-carey-chatgpt-turnaround.md). No rig or LoRA is claimed. |
| Independent-background Brambleton still | **Rendered; Carey review pending** | Job `a3b1a4a04a2e2d7d7458e75a5f058ca3`; the broad white halo is removed, a thin light edge remains. All 499,269 frozen face/hair core pixels match Anchor v1; 234,999 background pixels changed. See [scene-edge review](reviews/2026-10-04-anime-scene-edge-qualification.md). |
| Animagine XL 4.0 Opt | Installed and hash-verified | `D:\ByrdHouse\models\checkpoints\animagine-xl-4.0-opt.safetensors`; 6,938,350,040 bytes; SHA256 `6327eca98bfb6538dd7a4edce22484a1bbc57a8cff6b11d075d40da1afb847ac`; manifest row records revision and license. |
| RX 7900 XT local workflow components | Installed and verified | PuLID v1.1, ControlNet Union SDXL, SDPose, documented in [model manifest](model-license-manifest.md) and [lab review](reviews/2026-10-03-pulid-sdpose-union-lab.md). |

## Rejected and never to recycle as finals

| Item | Verdict | Why |
|---|---|---|
| `32b9f87dd7d28b7a7b39be410580d62c_1.png` | **Rejected** | PuLID new-scene candidate completed in 31.26 s but genericized Carey and was too soft at full-body face scale. Read-only belt similarity to the real neutral reference: `0.365440`, below the `0.65` review screen. It must not be animated or reused as a Carey canonical asset. |
| `pulid-v11-private-lab-r2_00001_.png` | **Rejected** | Earlier technical benchmark: similarity `0.591786`; taller/spikier crown, smoother/higher hairline, narrow midface/jaw, regenerated beard/mouth. |
| Source-preservation scene swaps | **Rejected for final show art** | They retain source pixels but show a visible afro-edge halo. See image state. |
| `97b0b62f810d753cec3bf3c836329261_1.png` | **Rejected** | First Animagine / IP-Adapter Plus Face / SDPose / Union episode-keyframe test: generic small face, spherical afro, missing canonical facial-hair and feature design, weak setting. The read-only detector could not locate a usable illustrated face; saved inspection is `similarity: null`, which is an inconclusive failure rather than a pass. Never animate, train on, or reuse it as canon. |
| `3a06290e6e71c7956044964485651edd_1.png` | **Rejected** | Imported AnimeFix face-detail pass enlarged/smoothed the afro and changed the canonical face. It scored `0.133730` against the anchor and must not seed, train, or animate. The detailer is disabled by default. |
| `ab663a1332a3851212f851338e81ffdd_1.png` | **Rejected technical scene test** | First locked-anchor background swap proved exact core preservation but had a visible pale edge around the afro. Replaced by the tighter-edge follow-up `26e…`; retain only as evidence. |
| `26e31a04331739f4bd13346c1274d8c5` and `1df18317cd9131ecb66e143feb4236fa` | **Rejected illustrated scene tests** | The first BiRefNet and second tight semantic-person-mask composites both preserve the semantic face/hair core but visibly retain a pale afro halo. Both are marked rejected in Studio and must not seed an episode. The next test uses an independent full-scene background. |

## Current system state

- **ComfyUI:** local at `http://127.0.0.1:8188`, AMD Radeon RX 7900 XT.
- **Studio:** local at `http://127.0.0.1:8787`; the server contains the PuLID
  private-lab queue route plus the Animagine illustrated-keyframe route. Its
  *read-only* face/hairline/forehead/jaw inspection records detector gaps as
  inconclusive and requires visual review; it never approves an anime frame.
- **Live source inputs:** PuLID jobs freeze neutral, smile, night, and the real
  full-body pose photo before queueing; changed inputs fail closed.
- **Validation:** 141 focused Studio/identity/input tests passed before the
  automatic inspection addition; post-addition `py_compile` and 35
  `test_server` tests passed. The current full Studio suite passes **153**
  tests after the independent-background and mask-edge changes.
  `node --check app.js` passed.
- **Launch caveat:** start Studio with trusted base Python **and**
  `PYTHONPATH=C:\Users\carey\Documents\ByrdHouse\runtime\venv\Lib\site-packages`.
  The normal venv launcher can be blocked by Windows App Control when started
  from Codex.

## Sources already researched or used

| Source | Role | Local evidence / decision |
|---|---|---|
| [CivitAI SDXL IP-Adapter + ControlNet Union workflow](https://civitai.com/models/1024555) | Existing SDXL structure/identity workflow reference | Archive staged at `external/workflows/civitai-sdxl-ipadapter-controlnet-union-v10.zip`; adapted only by replacing the identity adapter with PuLID v1.1 while retaining the Union pose structure. |
| [Official PuLID](https://github.com/ToTheBeginning/PuLID) and [v1.1 weights](https://huggingface.co/guozinan/PuLID) | Multi-reference SDXL identity conditioning | Official code/weights are Apache-2.0; the chosen Comfy adapter’s license is unresolved, so private qualification only. |
| [ControlNet Union SDXL](https://huggingface.co/xinsir/controlnet-union-sdxl-1.0) | OpenPose/depth structure | Apache-2.0, installed and hash-verified. |
| [Comfy-Org SDPose](https://huggingface.co/Comfy-Org/SDPose) | Local whole-body pose extraction | MIT, installed and hash-verified. |
| [Character anchor guide](https://github.com/tkottke90/comfyui-character-workflow/blob/main/docs/sdxl-consistent-character-anchor-guide.md) | Anchor kit, crop-scale face repair, upscale, and lock-the-winner discipline | Used as a design reference; it confirms that full-body faces need a face-detail pass and long-running character work needs an approved anchor kit/LoRA. |
| [ComfyUI episode workflow discussion](https://github.com/Comfy-Org/ComfyUI/discussions/16004) | Short-form episode evidence | Research example uses SDXL, 15+ controlled keyframes, and a character LoRA; treat as an external example, not proof of this PC’s results. |
| [Anime img2img workflow reference](https://github.com/ayushchinmay/ComfyUI_Img2Img_Workflow) | Anime restyle/face-crop/line/depth control research | Candidate reference only. No code or model was installed from it. |
| [AnimeFix-Workflow](https://github.com/ExMikuPro/AnimeFix-Workflow) | Existing SDXL/Illustrious multi-stage refine workflow | Staged at `D:\ByrdHouse\external\AnimeFix-Workflow`, commit `4caa3dd4d3a0ccb84a6696f52af5a6a6facdbb44`, MIT. Its tested face-detail pass was rejected and disabled pending a separately qualified setting. |
| [ComfyUI Img2Img Workflow](https://github.com/ayushchinmay/ComfyUI_Img2Img_Workflow) | Existing Apache-2.0 source-latent image-to-image pattern | Staged at `D:\ByrdHouse\external\ComfyUI_Img2Img_Workflow`, commit `2be98e6b6aff069a51f989cd855c4f5345906931`. Its source-latent approach now qualifies the Carey anime anchor before scene work. |
| [Animagine XL 4.0](https://huggingface.co/cagliostrolab/animagine-xl-4.0) | SDXL-native illustrated base for Carey Anime Canon Anchor work | Revision `2b7c1b397761bf5bd3cc42e5b39ec99314a75a96`, model hash verified locally; first pose test rejected and recorded separately. |
| Built-in ChatGPT image generation via the [local imagegen skill](C:/Users/carey/.codex/skills/.system/imagegen/SKILL.md) | Four-view Carey and wardrobe candidate sheets | Generated from the approved anime anchor and two real Carey photos, saved with hashes and review status in [the turnaround record](reviews/2026-10-04-carey-chatgpt-turnaround.md). Cloud artwork creation; local RX 7900 XT production remains separate. |

## Decisions that prevent backsliding

1. Carey Anime Canon Anchor v1 is the show’s visual source of truth until Carey
   explicitly replaces it. Do not overwrite the file; create `anchor-v2` for
   any future replacement.
2. A good technical render is not an approved likeness. Keep visual acceptance
   and animation approval as separate steps.
3. Do not use photoreal RealVisXL Lightning as the episode art-direction base.
   Its fast full-body result was soft and genericized Carey.
4. Do not train from unreviewed generated images. Build an approved illustrated
   anchor kit first, then train a dedicated anime character LoRA from those
   curated assets and real source material as appropriate.
5. Add no new model until it has a row in `model-license-manifest.md` with
   source, license, size, destination, hash, lane, and rollback.

## Next concrete work

1. Review the completed Anchor v1 motion clip. Keep it only if Carey confirms
   the expression and tiny head movement belong to the canon character.
2. Visually accept or reject the independent-background Brambleton candidate `a3b1a4a04a2e2d7d7458e75a5f058ca3`; inspect the remaining thin light afro edge at full size.
3. Use the now Carey-approved multi-view likeness as the character design
   reference. Keep the current clothes as placeholders; make a changeable
   wardrobe and expression/mouth assets before rigging. Treat the head-sheet
   stud difference as a continuity detail to resolve per view, not a reason to
   erase Carey's visual approval.
4. Use pose-controlled episode keyframes from that kit. Apply the belt at
   crop-scale, reject drift, and preserve each shot’s seed/input/workflow.
5. Produce one 15–45 second Brambleton pilot short only after keyframes pass
   visual continuity review.
- 2026-10-05: Saved six-expression and stoop ChatGPT candidates with provenance. Researched existing animation systems. Updated local-only production direction. Publication checks: Studio 190/190, full mock belt passed with UTF-8; JSON and PowerShell syntax validated. See reviews/2026-10-05-chatgpt-assets-and-publication.md.
