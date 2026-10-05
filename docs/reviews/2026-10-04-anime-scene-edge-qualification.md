# Anime Carey scene-edge qualification — 2026-10-04

## Outcome

The broad white afro halo came from generating a background by inpainting the
old off-white anchor canvas. A tighter semantic person mask alone did not fix
that leak. Studio now generates the entire anime background independently with
the installed Animagine XL checkpoint and core ComfyUI `EmptyLatentImage`,
`KSampler`, and `VAEDecode` nodes, then overlays the approved source Carey
through a reviewed semantic character mask. The frozen face-and-hair core is
overlaid again to keep its saved RGB bytes exactly equal to Anchor v1.

This is a **same-pose scene swap**, not a new Carey pose or an identity model.
The final scene still is a candidate awaiting Carey visual approval. A narrow
light outline is still visible in places at full resolution, but the broad
white haze from the inpaint path has been removed.

## Controlled local test

All scene tests used the approved `carey-anime-anchor`, Animagine XL 4.0 Opt,
seed `381902`, and prompt:

> Brambleton townhouse stoop, red brick rowhouse, teal front door, crooked gold house number, potted plant, warm late-afternoon light, cozy neighborhood street

| Studio job | Method | Outcome |
|---|---|---|
| `26e31a04331739f4bd13346c1274d8c5` | BiRefNet soft alpha + masked inpaint | Rejected: broad pale halo; core exact. |
| `1df18317cd9131ecb66e143feb4236fa` | Tight semantic character mask + masked inpaint | Rejected: halo persisted; core exact. |
| `e770fe50ef7ddccbcd977ada7f1201bc` | Independent full background + semantic mask eroded 2 px | Candidate; broad haze removed, thin light outline remains. |
| `83265a080f0b54d474be30f5e5cde481` | Technical mask trial eroded 5 px | Failed closed: omitted protected face/hair core pixels. Never used for a scene. |
| `0149ac41905aa7a669c6e8a93ea69d1e` | Technical mask eroded 4 px | Reviewed/approved for use as a mask only, not an image. |
| `a3b1a4a04a2e2d7d7458e75a5f058ca3` | Independent background + 4 px mask | Best current Brambleton scene candidate; `needs_review`. |

The final candidate is at
`D:\ByrdHouse\media\images\a3b1a4a04a2e2d7d7458e75a5f058ca3_1.png`.
It took 1.46 seconds of warm execution after the same-seed background was
cached, **not** a valid cold-generation speed benchmark. The previous
independent-background test took 10.30 seconds. Its pixel audit reports
499,269 exact semantic core pixels, zero core changes, and 234,999 changed
background pixels. The code does not assert an exact new-pose Carey likeness
from this saved-pixel result.

## Implementation and checks

- Source: `windows-local/studio/source_preserve.py` now uses an independent
  empty latent for anime scene backgrounds, while photo edits keep the original
  inpaint route. The foreground/semantic-core composites use already installed
  ComfyUI nodes.
- Source: `windows-local/studio/source_masks.py` creates a 4-pixel eroded,
  softly blurred illustrated character mask from the installed face parser.
  The 5-pixel version failed the core-containment check and was not promoted.
- Tests: 153 local Studio tests pass after the change. Live ComfyUI and Studio
  completed the new mask and scene jobs on the RX 7900 XT. The output PNG,
  workflow, mask hashes, source reference hash, pixel audit, and review state
  remain in the Studio job journal and media library.
- The broad-halo jobs were explicitly marked `rejected` in Studio. The new
  scene stays `needs_review`; no automatic likeness or episode approval occurs.

The next scene upgrade is pose control from a Carey-approved multi-view sheet
or curated LoRA. A same-pose background replacement cannot prove the character
will stay recognizable after a new pose, clothes, or expression.
