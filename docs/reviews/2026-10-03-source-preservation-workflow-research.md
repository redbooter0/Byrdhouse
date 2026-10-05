# Source-preserved Carey editing: upstream workflow research

Research snapshot: 2026-10-03. Requested for Carey's current Windows PC: RX 7900 XT
20 GB, i9-10850K, 32 GB RAM, C: runtime and D: ByrdHouse/model library. The mini
PC is deferred. This note proposes the next image route; it does not record a
successful new render, an installation or an approved likeness result.

## Recommendation

Reuse the official ComfyUI inpainting pattern, the semantic parser already
installed on this PC, and ComfyUI's core `ImageCompositeMasked` node. Start with a
reviewed original Carey photo. Generate only the requested background or outfit,
then composite those edited pixels over the original. Keep a reviewed, binary
face-and-hair protection mask unchanged through the final saved PNG.

This gives a testable preservation target for the original pose and expression.
It does not promise an exact reconstructed Carey in a new pose. FaceID, face
swapping, GPEN restoration and LoRA are unnecessary on the protected head in this
route because their job would be to reconstruct pixels we already possess.

No inspected upstream example combines this PC's RealVisXL checkpoint, Carey's
reviewed face/hair mask and an exact post-save pixel check. The proposed graph is
a small adaptation of existing upstream nodes, not a newly discovered turnkey
workflow or a custom renderer.

## Reusable upstream examples and their limits

| Source | What is reusable | Limit for this task |
| --- | --- | --- |
| [Official ComfyUI inpainting tutorial](https://docs.comfy.org/tutorials/basic/inpaint) | Loadable example, Mask Editor, checkpoint loading and `VAEEncodeForInpaint` pattern | Demonstrates masked editing, not proof that every pixel outside the mask survives VAE reconstruction |
| [Maintainer's inpainting examples](https://comfyanonymous.github.io/ComfyUI_examples/inpaint/) | Image-embedded workflows and the documented use of both inpainting and regular checkpoints | Start from the example pattern; do not replace the installed SDXL model with its example SD 1.5 model merely to reproduce the screenshot |
| [Installed parser's upstream repository](https://github.com/isurulkh/comfyui_face_parsing_New) | CPU-selectable semantic model loader and mask parser | Segmentation must be reviewed; default toggles include clothing |
| [Facetools full inpainting example](https://github.com/dchatel/comfyui_facetools/blob/main/examples/full_inpainting.json) | Face parsing, crop/warp/paste-back concepts | Its local copy edits a face, uses an SD 1.5 checkpoint and two ControlNets. It is not a source-preserved Carey background/outfit graph |

The official tutorial links its [example workflow PNG](https://raw.githubusercontent.com/Comfy-Org/example_workflows/refs/heads/main/image/basic/sd1.5_inpaint.png).
The tutorial describes loading workflow metadata from that image. This research
viewed the asset through the browser; it did not download it, execute it, or
claim that its complete serialized graph was validated against this deployment.

A recent [ComfyUI issue proposing inpaint compositing](https://github.com/Comfy-Org/ComfyUI/issues/16434)
also identifies outside-mask VAE color changes and proposes compositing the
decoded result over the original. This is a community proposal, not an accepted
upstream guarantee. The actual core compositing implementation supports the
mechanism independently of that issue. Its linked workflow attachment was not
accessible through the browsing tool and was not inspected.

CivitAI and Reddit searches found clothing-edit and identity-consistency
examples, but none supplied verified exact preservation for the installed SDXL
stack. They are discovery material, not the technical basis for this proposal.

## What was verified locally

Read-only `/object_info` inspection exposed the following existing nodes. This
confirms registration and schemas, not successful execution of this new graph:

- `FaceParsingModelLoaderNew`, `FaceParsingProcessorLoader(FaceParsing)`,
  `FaceParse(FaceParsing)`, `FaceParsingResultsParser(FaceParsing)`.
- Core `LoadImage`, `LoadImageMask`, `CheckpointLoaderSimple`, `CLIPTextEncode`,
  `VAEEncodeForInpaint`, `VAEEncode`, `SetLatentNoiseMask`, `KSampler`,
  `VAEDecode`, `ImageCompositeMasked`, `SaveImage`.
- Core `MaskComposite`, `InvertMask`, `GrowMask`, `ThresholdMask`, `MaskPreview`,
  `MaskToImage`, `ImageToMask`, and installed `ImpactGaussianBlurMask`.

The installed parser loads weights and processor from the existing
`ComfyUI/models/face_parsing` directory. Its loader defaults to CPU and moves the
model to GPU only when explicitly requested. The parser returns a color preview
on output 0 and raw class labels on output 1; the mask parser takes output 1.
See the [local loader and parser](C:/Users/carey/Documents/ByrdHouse/ComfyUI/custom_nodes/comfyui_face_parsing_New/face_parsing_nodes.py:15).

The model's [primary model card](https://huggingface.co/jonathandinu/face-parsing)
describes a SegFormer face parser trained on CelebAMask-HQ. Local label mapping
includes skin 1, hair 13, hat 14, earrings 15, necklace 16, neck 17 and clothing
18; background is 0. This is face parsing, not a validated whole-person mask for
every full-body scene. Hands, accessories and thin curls require inspection.

Commit snapshots read locally:

- ComfyUI: `6b747c0428c343e1417219641db93a4fb7cb69ae`.
- `comfyui_face_parsing_New`: `abd627dd9a23904246b4ab1f809754d55019f808`.
  Its `__init__.py` has a local bootstrap/dependency patch, so that commit alone
  does not identify the entire deployed checkout.
- `comfyui_facetools`: `59566c54f4fb814dd94787d348f18635563e90a3`.

Prefer the already installed CPU parser fork for this route. The alternative
Facetools `JonathandinuMask` utility contains an unconditional `.cuda()` for
class-index tensors, including after its CPU fallback decision. That is a
fragile fallback and introduces avoidable GPU competition; see
[the local utility](C:/Users/carey/Documents/ByrdHouse/ComfyUI/custom_nodes/comfyui_facetools/utils.py:248).
ROCm exposes AMD operations through `torch.cuda`; the API spelling alone does
not imply an NVIDIA-only runtime.

## Proposed node wiring

Use a lossless, orientation-normalized working copy of an approved original
photo. Keep the original file and record its hash. The current 1152×1536 portrait
is divisible by 8 and is a suitable first canvas without resizing. The pipeline
below is proposed and has not been rendered during this research.

1. `LoadImage` produces the working source image `S`.
2. `FaceParsingModelLoaderNew(device="cpu")` and
   `FaceParsingProcessorLoader(FaceParsing)` feed `FaceParse(FaceParsing)` with
   `S`. Send raw output 1 to the mask parsers.
3. Build protected head mask `P`: explicitly enable skin, nose, glasses, both
   eyes, both brows, both ears, mouth, both lips, hair and hat. Initially also
   protect earrings, necklace and neck. Explicitly disable background and
   clothing. Review and repair this mask in Mask Editor; freeze a binary mask.
4. Build the requested editable region `R` using a second parser:
   background-only = class 0; outfit-only = class 18; combined = classes 0 and
   18. All other toggles must be false. Review `R` for the actual garment or
   background change, including any expanded garment silhouette.
5. Create `P_guard` with a small, reviewed `GrowMask(P, expand=...)` margin when
   needed around curls and the head boundary. Compute editable generation mask
   `E = R × (1 - P_guard)` with `InvertMask` and `MaskComposite(multiply)`.
6. Reuse checkpoint → positive/negative `CLIPTextEncode` → masked latent →
   `KSampler` → `VAEDecode`. For the official example pattern, use
   `VAEEncodeForInpaint(pixels=S, mask=E, grow_mask_by=0)`. The alternative
   already used elsewhere here is `VAEEncode(S)` followed by
   `SetLatentNoiseMask(E)`. Compare seam quality before choosing one; neither
   provides the final preservation guarantee on its own.
7. Make a final compositing mask `E_final`. For a hard boundary, use `E`.
   For a soft outside boundary, use installed `ImpactGaussianBlurMask` on the
   editable mask, then multiply by `1 - P_guard` again. Explicitly check that
   `E_final` is exactly zero everywhere `P` is one.
8. `ImageCompositeMasked(destination=S, source=decoded_result, mask=E_final,
   x=0, y=0, resize_source=false)` → `SaveImage` as PNG.
9. Collect the saved result, verify protected pixels against the working source,
   save a metadata card and require visual review before animation.

The existing RealVisXL V5 Lightning checkpoint is the first candidate for reuse.
The maintainer's example documents generic inpainting with regular checkpoints;
this does not establish that this particular Lightning checkpoint produces good
clothing edits at current denoise/step settings. That quality and timing need a
small real qualification, not a new model-library installation.

`InpaintModelConditioning` is present, but a specialized inpainting model is not
required just to construct the proposed baseline. Do not assume a regular
checkpoint accepts a specialized extra-channel inpainting architecture.

## How the mask protects Carey's actual features

Protect skin and hair together across the hairline: forehead skin lies in class
1 and hair in class 13. Protect both sides of that boundary, rather than masking
only the central face. Preserve the full afro silhouette, fine curls, ears,
eyes/brows, nose, mouth/teeth and beard region seen in the source. Use the actual
source pixels; do not redraw those details from a descriptive prompt.

The installed mask parser defaults `cloth=true`. Leaving defaults unchanged
would protect clothing and defeat outfit editing. Every Boolean must therefore
be explicit in the graph. Its eye/brow/ear parameter order also differs from the
left/right names in the model config. The all-features union avoids that issue;
feature-specific reports must read the model mapping instead of guessing sides.
See [the installed mask parser](C:/Users/carey/Documents/ByrdHouse/ComfyUI/custom_nodes/comfyui_face_parsing_New/face_parsing_nodes.py:120).

Do not fall back silently to a rectangular face box. Afro tips classified as
background would be regenerated despite a seemingly good central face mask.
Display the mask over the source; Carey must be able to inspect the forehead,
hairline, outer curls and beard before freezing it. Mask validity is an explicit
review decision, not something an embedding score can prove.

Core `FeatherMask` smooths the mask's canvas-edge margins; it is not a generic
feather operation around an internal hair silhouette. Use the installed blur
node only outside the protected core, with the subsequent guard multiplication.
Blurring the final protected mask itself would admit fractional generated pixels
into the face/hair. See [core mask operations](C:/Users/carey/Documents/ByrdHouse/ComfyUI/comfy_extras/nodes_mask.py:303).

## Exact protected-pixel verification

Core compositing uses `mask × source + (1-mask) × destination`. With an exactly
zero final edit mask, the destination is retained at that location. Its code
also resizes supplied masks to the generated source dimensions using bilinear
interpolation. Therefore enforce identical source, decoded-image and mask
dimensions; do not rely on implicit mask resizing or `resize_source=true`.
See [the deployed compositor](C:/Users/carey/Documents/ByrdHouse/ComfyUI/comfy_extras/nodes_mask.py:12)
and [the matching pinned upstream source](https://raw.githubusercontent.com/Comfy-Org/ComfyUI/6b747c0428c343e1417219641db93a4fb7cb69ae/comfy_extras/nodes_mask.py).

Latent dimensions are another alignment risk: `VAEEncodeForInpaint` crops to the
VAE's spatial compression multiple. Use a compatible native canvas; otherwise
pad without resampling and record the offset, then crop back to the correct
original coordinates. Do not silently center-crop and composite at `(0,0)`.
See [the local encoder](C:/Users/carey/Documents/ByrdHouse/ComfyUI/nodes.py:414).

Verify the PNG after saving, because the loader, float tensor conversion and
`SaveImage` uint8 conversion are part of the actual pixel path. Preserve the
canonical orientation-normalized 8-bit RGB working source alongside the job.
The original JPEG file hash and decoded RGB pixel hash answer different
questions; record both. If the working source was resized, state that exactness
is relative to that resized source, not unchanged pixels from the original JPEG.

Acceptance calculation on the final saved PNG:

```python
assert source_rgb.shape == final_rgb.shape
assert P.shape == E_final.shape == source_rgb.shape[:2]
assert not np.any((E_final > 0) & P)
delta = np.abs(final_rgb.astype(np.int16) - source_rgb.astype(np.int16))
changed = np.any(delta != 0, axis=-1)
protected_changed_pixels = int(np.count_nonzero(changed & P))
protected_max_error = int(delta[P].max())  # require a nonempty, reviewed P
outside_edit_changed_pixels = int(np.count_nonzero(changed & (E_final == 0)))
assert protected_changed_pixels == 0
assert protected_max_error == 0
assert outside_edit_changed_pixels == 0
```

This is a proof about the reviewed protected pixels on that canvas. It does not
prove the mask covers every identity feature or that the edited seam looks good.
Save the mask preview, binary protection mask, final edit mask, file/pixel/mask
hashes, canvas/transform metadata and results with the artifact. If the test
fails, do not label the output preserved or send it directly to animation.

## Open still-input hash gap

The current still job copies `reference_source_sha256` from the reference
manifest and records a mutable ComfyUI `reference_image` filename. The inspected
generation path does not rehash that actual image file immediately before
execution/resume or retain a job-specific immutable source snapshot. A source
replacement could therefore leave a valid-looking manifest/workflow hash while
the graph consumes different pixels. This gap remains open; correction and
animation source checks do not close it for ordinary still generation. Evidence:
[current make_spec reference handling](D:/ByrdHouse/repo/windows-local/studio/server.py:437).

Before this new route runs, snapshot the canonical working image and approved
masks under job-specific input names. Persist actual input hashes before
submission, verify them before submission and resume, and include those hashes
in the workflow/journal metadata. A changed input must stop the job; it must not
silently accept the reference manifest's old hash or resubmit a different image.

## Pose, lighting and animation limits

Changing background or clothes while keeping the photographed head is a useful
bounded operation. It preserves the source pose/expression. New head angles,
smiles, eyes or facial relighting require different pixels; a generated version
needs separate likeness review and cannot pass this source-pixel test. Use a
matching real photo when available instead of describing exactness in a prompt.

Keep new scene lighting compatible with the preserved source face. A strongly
different light direction may make the composite look pasted on. Fix the scene
or unprotected area rather than secretly relighting the protected face.

The parser may miss full-body foreground parts. For initial background work,
review protection of the entire foreground person, not just the head. Clothing
class 18 may be too small for a new coat silhouette; expand the editable region
visibly and keep the head/neck guard intact. Multi-person images need explicit
person selection and independent reviewed masks; this graph does not solve that
ambiguity automatically.

LivePortrait reconstructs moving face pixels. A still with zero protected pixel
changes does not establish an exact animated face. Start with a kept still,
record its hash, use small reviewed motion, and inspect frames around blinks and
the largest head turn. Check hairline, eyes/brows, nose, mouth/teeth and jaw/beard
against pose-matched references; retain separate still and motion approvals.
Large pose changes, talking and full-body motion remain separate qualification
tasks. A motion that only transforms/composites the unchanged photograph has a
different, limited preservation scope from generative face animation.

## Next implementation and acceptance gates

1. Close the still-input snapshot/hash gap and add a source-preserved edit
   operation to the existing persistent Studio queue. Reuse its prompt journal
   and restart collector; keep one active rendering workload.
2. Prepare one reviewed original-photo mask in the GUI, including the outer
   afro and forehead. Version it with a purpose and original source hash.
3. Assemble the graph above from installed nodes, save its API JSON and exact
   node/checkpoint provenance. No custom diffusion/compositing engine is needed.
4. Qualify background-only first, then outfit-only. Verify same dimensions,
   no overlap with protected pixels, zero post-save protected changes and a
   visually acceptable seam. Record real total/load/sample times and failures.
5. Test changed-input rejection and restart recovery with mocked ComfyUI:
   one submitted prompt, same immutable sources, one collected artifact.
6. After Carey keeps a still, animate only a short motion preview and require
   a separate frame review. Never promote similarity scores to exactness.

Removing unnecessary identity/restoration models from this route should reduce
loading and avoids their reconstruction drift; that is an architectural
expectation, not a measured speed claim. CPU parsing time, memory usage, new
graph image quality and sustained RX 7900 XT stability still require real tests.
No runtime changes, file downloads, installations, restarts or GPU jobs were
performed for this research note.
