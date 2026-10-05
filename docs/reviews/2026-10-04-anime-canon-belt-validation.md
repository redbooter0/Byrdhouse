# Carey Anime Canon belt: measured hair, forehead, outline, and skin cues

**Date:** 2026-10-04
**Machine:** Windows i9-10850K, RX 7900 XT 20 GB, 32 GB RAM
**Status:** Deployed to the local Studio; same-view illustrated review qualified on one faithful redraw and one known rejected redraw. No new still or animation was approved by an automatic score.

## Existing workflow components used

The GPU still route remains the staged CivitAI SDXL IP-Adapter + ControlNet
Union concept and the [ComfyUI image-to-image VAE latent pattern](https://github.com/comfyanonymous/ComfyUI_examples/blob/master/img2img/README.md). The local
[Apache-2.0 img2img workflow](https://github.com/ayushchinmay/ComfyUI_Img2Img_Workflow)
is pinned at `2be98e6b6aff069a51f989cd855c4f5345906931`; its VAE source-latent
pattern is already qualified in Studio. The rejected AnimeFix detailer and its
output remain disabled and excluded from the character kit.

The belt reuses the installed CPU [SegFormer face parser](https://huggingface.co/jonathandinu/face-parsing),
InsightFace detector, and FAN 68-point outline model. It does not add a new
network or train a new model. The parser model card defines separate class IDs
13 (`hair`) and 14 (`hat`). On the approved illustrated anchor the parser put
only `0.000854` of its crop in `hair` while `0.287371` went to `hat`. The visual
mask shows that the latter class traces Carey's drawn afro. The belt now uses
their union as an **illustrated review silhouette** only. Photographs continue
to use literal hair class 13 so an actual hat cannot satisfy a hair check.

## Locked Carey profile

`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1-profile.json` is a
machine-readable measurement of the owner-approved Anchor v1. The Studio now
checks its `anchor_sha256` against the registered reference and also checks
the current examiner's key measurements against the saved profile. If they
disagree, the image remains an inconclusive review instead of receiving a
misleading likeness result. The approved source SHA256 is
`2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`.

| Canon measurement | Anchor v1 value |
|---|---:|
| Face bounding box on 832×1216 canvas | `[239.34, 262.71, 676.08, 848.69]` |
| Hair silhouette bounds | `[20, 35, 809, 784]` pixels |
| Median hairline height | `173.0` pixels |
| Hairline coverage across central forehead | `1.0` |
| Visible forehead height / detected face height | `0.439693` |
| Afro width / detected face width | `1.806575` |
| Afro height / detected face height | `1.278219` |
| Median parsed skin RGB | `[125, 92, 73]` |

These are measured positions and review cues for the approved frontal portrait.
The parser and face detector can be wrong. A side view, different expression,
or changed lighting requires human judgment and approved examples of that view.
The numeric gates are conservative same-view screens, not biometric proof.

## Local contrast check

Both outputs were re-examined against the same hash-verified canonical source
after deployment. Each report includes the canon-profile hash and an annotated
side-by-side image.

| Candidate | Read-only similarity | Hairline shift | Afro-width shift | Forehead-height shift | Face-outline error | Median skin-brightness shift | Same-view screens |
|---|---:|---:|---:|---:|---:|---:|---|
| Faithful source-latent redraw `346b554dc7bf47f8c986aa08aec35729_1.png` | `0.876475` | `0.012599` | `0.018455` | `0.006898` | `0.009148` | `+2.000` | hair, forehead, outline pass; still `needs_review` |
| Rejected AnimeFix detailer `3a06290e6e71c7956044964485651edd_1.png` | `0.133730` | `0.238694` | `0.304507` | `0.147162` | `0.065714` | `+46.936` | hair, forehead, outline fail; remains rejected |

The rejected image visibly has a ballooned afro, altered hairline and face,
and lightened skin. The report now marks the out-of-range features as `CHANGE`
and points to their approximate locations. The skin cue measures brightness
only; scene lighting can change it, so it never establishes identity by itself.

## Implementation and limits

- Source: `windows-local/studio/identity_belt.py`, `server.py`, and
  `render_belt_report.py`. The live Studio copies have matching SHA256 hashes.
- Local profile: `D:\ByrdHouse\assets\characters\carey-anime\anchor-v1-profile.json`.
- Live config: `D:\ByrdHouse\byrdhouse-local.json` binds `anime_canon_profile`.
- Studio responded on `127.0.0.1:8787` with `anime_ready: true` after restart.
- 108 focused Studio/identity/input/mask tests passed after the final report
  highlighting pass; Python compilation and JavaScript syntax checks passed.

The belt now caches at most 32 examinations by exact file SHA256, path and
illustrated/photo mode. It rejects changed files during an examination. On this
PC one cold approved-anchor examination took `15.836 s`; a repeated inspection
in the same process took `0.0019 s`. This avoids re-parsing the same approved
anchor for every keyframe; it is not a claim about total render speed.

## Existing motion test sampled through the belt

The already-rendered 44-frame/15 fps Anchor v1 motion clip
`0cf48a1d6a53295f53b4727bd0efb4e7.mp4` was decoded at frames 0, 22 and 43.
All three samples retained detectable faces and passed the same-view hair,
forehead and outline screens; read-only similarity was `0.908084`, `0.907648`
and `0.907501`. The frame files, source-video hash, and cue deltas are saved
under `D:\ByrdHouse\media\animation-review\0cf48a1d6a53295f53b4727bd0efb4e7`.
Visual inspection of frame 22 still showed softer teeth and mustache lines
than the approved still. The clip remains a `needs_review` motion test, not
approved episode animation.

The known good redraw preserves the approved pose. It does not prove a
different-pose Carey, a seamless scene edge, or an episode-ready animation.
For a new pose, the belt reports a changed view as requiring visual review
rather than treating a frontal contour mismatch as a wrong identity. The next
production step is an owner-reviewed multi-angle anchor kit and a better
afro-edge composite on scene swaps; only accepted stills can become episodes.
