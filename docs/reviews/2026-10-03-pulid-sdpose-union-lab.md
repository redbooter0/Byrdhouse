# PuLID v1.1 + SDPose + ControlNet Union new-scene lab — 2026-10-03

## Purpose

Qualify an existing workflow rather than inventing a new image renderer:

- CivitAI workflow archive: `external/workflows/civitai-sdxl-ipadapter-controlnet-union-v10/`
  (SHA256 archive `16255be92cd774d3d1982bbf1c59668a67caea384d874169da00091d0c733ad4`).
- PuLID v1.1 supplies identity conditioning from a native batch of real Carey photos.
- SDPose turns a distinct full-body real Carey photo into an OpenPose map.
- ControlNet Union SDXL enforces that map while RealVisXL generates a different
  setting and wardrobe.

This separates **who** (the real identity references) from **where/how the body
is posed** (the structure image). The output is newly synthesized pixels and
never an exact copy claim.

## Installed, verified local prerequisites

All files are on `D:` and recorded in `docs/model-license-manifest.md`.

| Asset | Source/license | Verification |
|---|---|---|
| PuLID v1.1 | `guozinan/PuLID`, Apache-2.0 | 984,405,232 bytes; SHA256 `4cb8ceec1078e0165399b88332ab3c5971619111b8e1730e6bae64144aabae41` |
| ControlNet Union SDXL | `xinsir/controlnet-union-sdxl-1.0`, Apache-2.0 | 2,512,030,408 bytes; SHA256 `a9e13fd61f3193887791c8a0dd07a07202174dc47d5ddaea94ea1344f07c7467` |
| SDPose WholeBody | `Comfy-Org/SDPose`, MIT | 1,916,645,792 bytes; SHA256 `63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721` |
| ComfyUI-PuLID adapter | `yashikawa3/ComfyUI-PuLID` commit `c672e2a88580afe59773bde1576ce1838abd1a0f` | Its repository has no license file despite citing Apache-licensed upstream projects. Private local qualification only. |

The node was registered live as `PulidModelLoader`, `PulidInsightFaceLoader`,
`PulidEvaClipLoader`, `ApplyPulid`, and `ApplyPulidAdvanced`. The node’s EVA
encoder cache was constrained to `D:\ByrdHouse\models\clip_vision\pulid_eva`;
the first load fetched 856,461,210 bytes there.

## Actual RX 7900 XT benchmark

Prompt `642a7b2f-c677-4726-b363-2810006cc45e` completed on the RX 7900 XT.
It used three real-photo references (`neutral`, `smile`, `night`), a separate
real full-body Carey photo only for the pose map, PuLID v1.1 `ortho_v2` /
fidelity 20 / weight 1.0, Union OpenPose strength 0.55, and RealVisXL V5
Lightning at 832×1216 / 8 steps. It took 128.40 seconds including the one-time
EVA model download.

The original attempted prompt `24354eb4-dcb6-4dab-ad4d-b8eb2bc16783` was
correctly rejected before generation because SDPose was connected to an SDXL
checkpoint rather than its dedicated pose checkpoint. That wiring issue was
fixed; no generated image exists for the failed prompt.

The output is:

`D:\ByrdHouse\media\comfy\ByrdHouse\pulid-v11-private-lab-r2_00001_.png`

The landmark/belt review is:

`D:\ByrdHouse\media\images\pulid-v11-r2-analysis.json`

`D:\ByrdHouse\media\images\pulid-v11-r2-analysis-analysis.png`

## Verdict

**Rejected for production and animation.** The workflow is technically working:
it created a new full-body scene while using a separate identity batch and pose
map. It is not sufficiently exact for Carey.

The CPU examiner returned embedding similarity `0.591786` against the clean
smile reference, below the current review screen of `0.65`. Geometry screens
passed (including face-outline error `0.077283`), which only means the detected
shape was close enough for review; it does not establish likeness.

Visual comparison found a taller/spikier crown, a smoother and higher U-shaped
hairline, a narrower/more symmetrical midface and jaw, plus regenerated beard
and mouth details. The annotated review identifies each region and its required
correction. Do not animate this still.

## Next production gate

Use the PuLID/Union graph as a private candidate route only after it is added to
the shared Studio queue. Increase reliability with a real-only four-view
reference board: clean front hairline, left three-quarter, right three-quarter,
and profile. Keep a separate held-out real photo for review. If that gate still
cannot pass Carey’s visual approval, train a real-photo SDXL identity LoRA;
never self-train from generated candidates.

## Studio queue integration — 2026-10-03

The tested graph is now exposed in the local Studio as **PuLID private lab ·
Carey pose + new scene**. This is thin queue/UI integration around the same
Comfy node classes and settings used by the benchmark; it does not add a custom
image renderer.

For each queued PuLID job, Studio stages and hashes these immutable inputs before
ComfyUI receives any prompt:

1. `neutral`, `smile`, and `night` Carey references, all registered as real
   photographs in the local reference manifest.
2. `10-Photo-10.jpg` as the separate full-body OpenPose source, SHA256
   `e6a7a03c94634a1fd5ff45ead9186a8707f4be754b036bc6fdc6e29a39f5c5b5`.

The worker revalidates the staged PNG bytes, decoded RGB pixels, metadata, and
Comfy input aliases before it submits or resumes a job. A changed photo or a
missing board member fails closed. The route uses RealVisXL Lightning at 8
steps/CFG 2.0, PuLID v1.1 `ortho_v2`/fidelity 20/weight 1.0, and Union OpenPose
strength 0.55. The UI labels every result **PULID + REAL CAREY POSE · PRIVATE
LAB** and leaves it in review; it never auto-approves or auto-animates it.

Validation before deployment: the dedicated graph-contract test and the full
Studio/identity input suite passed (`141` tests), `node --check app.js` passed,
and the live ComfyUI inventory reported the model files plus every required
node. This integration only establishes reproducibility and correct input
binding. It does not overturn the benchmark’s rejected likeness verdict.
