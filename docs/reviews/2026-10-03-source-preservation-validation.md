# Source-preserved Carey scene editing: implementation and validation

Current Windows deployment: D:\ByrdHouse; RX 7900 XT 20 GB, i9-10850K,
32 GB RAM. This record builds on the dated hardware/architecture audits and
[upstream research](2026-10-03-source-preservation-workflow-research.md).
Exact reconstructed likeness and sustained AMD stability remain open.

## Implemented route

The new source-mask and scene-edit operations reuse the Studio SQLite worker,
submission journals and job review states. There is no separate GPU worker or
custom face renderer. CPU `comfyui_face_parsing_New` supplies semantic labels;
ComfyUI core nodes supply mask exclusion, SDXL masked generation and the final
original-pixel composite. Both operations retain exact workflow/input hashes and
prompt IDs for collecting the same submission after interruption.

The parser's 19 labels are explicitly configured. Protection includes classes
1–17: skin, facial features, ears, hair, hat, neck and accessories. The binary
protection mask has an eight-native-pixel conservative guard. The editable mask
is background class 0 (or experimental clothing class 18), multiplied by the
inverse protected mask. Saved masks must be binary, nonempty, native-size and
have no editable/protected overlap. A passing numeric check does not establish
that the parser found every curl, finger or foreground object.

The gallery inspection sheet shows the original photo beside an overlay:
green is protected, blue is editable. Inspect afro tips, forehead/hairline, face,
beard and neck before **Accept mask coverage**. This action reviews mask coverage,
not generated identity. Scene editing requires both the approved job state and
its persisted review card. A mask job cannot be sent to the animation route.

The edit graph reuses the [official inpainting pattern](https://docs.comfy.org/tutorials/basic/inpaint):
checkpoint and CLIP encoding → `VAEEncodeForInpaint(grow_mask_by=0)` → sampler →
VAE decode. Crucially, `ImageCompositeMasked` uses the untouched working photo as
destination, decoded scene as source and the frozen editable mask at native
dimensions, with no resize. Five-step RealVisXL Lightning is the initial existing
checkpoint; clothing quality is not qualified by a background test.

## Fixed reference binding

New ordinary FaceID, SDXL photo-variation and FLUX jobs also receive a fixed
per-job reference PNG. The helper hashes the actual selected crop independently
from the manifest's original-photo hash. Original-preservation analysis instead
checks the genuine original bytes against that original hash. It refuses the
existing `clean` row as an original because its manifest hash is stale.

Snapshots use EXIF orientation normalization, RGB conversion and lossless PNG,
without resizing. The source file SHA256, decoded RGB SHA256, staged PNG SHA256,
dimensions, normalization and ComfyUI input path are recorded. After queueing,
changing/deleting a mutable photo alias or manifest cannot replace this job's
source. Changing the staged PNG or its sidecar prevents execution. Legacy stills
without a snapshot may retain their existing outputs but are refused for new
execution/resume; historical provenance cannot be reconstructed safely.

For a source edit, the reviewed mask PNG is separately copied to a new job input
bundle and hash checked. The working photo stays bound to the parent mask's
snapshot. Collectors check the completed history's internal prompt ID, graph,
save-node map and output prefix, then rehash frozen inputs after execution.
Ambiguous intent without a saved prompt ID refuses automatic resubmission.

## Pixel acceptance

The saved output PNG is decoded to uint8 RGB and compared with the frozen
working source. The check requires equal dimensions, zero changed pixels within
the protection mask, zero changed pixels outside the editable mask, and at least
one changed pixel within the requested region. Protected source/output byte
hashes and maximum channel difference are recorded. A failed check prevents
gallery promotion. This verifies source-pose pixel preservation inside a reviewed
mask; it is not a promise of an exact face synthesized in a new pose.

## Model scope and provenance

No new model or runtime was installed. The existing parser weight is
338,580,732 bytes, SHA256
`c2bec795a8c243db71bd95be538fd62559003566466c71237e45c99b920f4b62`.
The fork software README mentions MIT, but the separate
[model card](https://huggingface.co/jonathandinu/face-parsing) states non-commercial
research and educational purposes. The model row now records private local
evaluation. A software license does not override a model's stated terms.

## Validation status

Focused mock/PNG tests cover exact saved pixels, altered pixels, binary masks,
dimensions, durable intent/ID ordering, callback crash windows, existing-prompt
resume, ambiguous submission, graph/settings/source/mask mutations, stopped
execution, terminal HIP error and mismatched history/output ownership.
Real hardware evidence and final counts are added below after deployment.

### Actual local results

All **138 focused tests passed**: the prior 63 queue/identity/portrait tests,
16 mask tests, 17 fixed-reference tests, 25 saved-pixel/submission tests and
17 server boundary/queue tests. Browser controls exercised analysis, mask review,
scene queueing and rejection. JavaScript syntax and Python imports passed.
Eleven source/deployed file hashes matched. Backup:
`D:\ByrdHouse\backups\studio-source-preserve-20261003-104628`.
Only Studio restarted; ComfyUI PID **6840** stayed unchanged.

| Studio job / operation | Prompt ID | Studio execution time | Result |
| --- | --- | --- | --- |
| `377bcabf9a3e55e422fe8f3df3430ad4` / original-photo semantic masks | `63da06bc-7425-4867-bf6f-0adddacbd331` | 10.53 s | Native 1152×1536 masks; 331,764 protected pixels, 931,410 editable pixels, zero overlap. Codex visually accepted conservative head coverage for these private tests. This is not Carey's generated-likeness approval. |
| `25656bbecdfab3a0b1166aeb3512d8df` / warm creative studio background | `7ce384fc-36c7-4791-a778-59f73dc5e221` | 45.44 s | Pixel proof passed; scene **rejected** for obvious retained tile/background halo and hard hair boundary. |
| `0c310b7900be3748cbfb35389007d053` / neutral photographic backdrop | `0effbb9c-5fe4-4453-9906-ccdf40b6e72e` | 13.58 s, warm | Pixel proof passed; scene **rejected** because backdrop compatibility did not solve the retained tile halo. |

Both edits had **zero changed protected pixels**, zero channel difference within
protection, and zero changed pixels outside the editable mask. First edit changed
931,408 editable pixels; second changed all 931,410. Both retained the same
protected-source/output byte hash:
`0b0414bf4ffa92a9a8b4cea84be13614a6d07ea017a6cd7959122b0f5851aaae`.
The original JPEG remains unchanged at SHA256
`6c68fbf66c695cbbe9ea5567d98fc14e1b09abecd3a36b5efc63303ec272cbc5`.
The actual saved PNGs were inspected, not just the generated tensor or a mask
score. Rejected artifacts and their manual scene-review notes remain local.

This establishes the mechanism for preserving source pixels, **not a finished
scene workflow**. The coarse semantic boundary and conservative guard also
preserve some original background among/around curls. Hard compositing exposes
those old tiles. Prompting a similar backdrop did not repair the defect. Do not
approve these scenes or run their animation. Next compare existing upstream hair
matting/boundary refinement while freezing facial features and the reviewed head
interior. Any edge-pixel alteration must have an explicit narrower claim; never
silently shrink the protection mask and call it exact head preservation.

Fine hair edge pixels already mix hair and the original background. Holding all
such RGB pixels identical while changing the background retains that mixture.
A better transition can change boundary RGB while preserving face/head interior;
the provenance/report must say which region changed. New poses and animation
still require their own likeness review.

Machine-readable evidence:
`D:\ByrdHouse\logs\source-preservation-validation-20261003.json` and
`D:\ByrdHouse\logs\source-preserve-deployment-hashes.json`.
Each job bundle under `D:\ByrdHouse\media\source-preserved\<job-id>` retains its
submission, masks/output and inspection. Gallery cards retain their settings,
workflow and separate pixel/quality findings. Both queues were empty afterward.

Hardware observation is saved in
`D:\ByrdHouse\logs\source-preserve-hardware-samples-20261003.json`.
The first authoritative monitor read arrived after the first edit completed:
**zero during-render samples; no measured render peak**. That post-render
snapshot showed 6.33 GiB AMD dedicated usage, 6.62 GiB shared usage and
8.85 GiB free RAM. These counter readings are not model allocations or render
peaks. No new hardware/runtime/model/SSD cache was installed or benchmarked.

## Remaining qualification

Review each new photo's semantic coverage; the first portrait does not qualify
all reference views, full-body masks or new garments. Seams, retained lighting
and original pose/expression constrain scene choices. Animated movement
reconstructs pixels and needs a separate frame review; a preserved still does
not confer exactness on its video. New poses/anime Carey likeness, matched
reference feature analysis, SSD caching, live mid-render restart and longer
mixed-operation AMD stability remain unfinished. Preserve the prior audit and
queue validation instead of rewriting their dated observations.

## BiRefNet follow-up — 2026-10-03

Comfy-Org BiRefNet was installed on D: with its published SHA256 verified and
used through ComfyUI's built-in `LoadBackgroundRemovalModel` / `RemoveBackground`
nodes. It produces a visually strong whole-person matte, including Carey’s outer
afro curls. The source-preservation graph now re-applies a frozen semantic core
after the soft alpha composite and records exact RGB equality for that core.

| Job | Result |
| --- | --- |
| `4d85756225251ec7e1323c5539d3ee0f` | 309,102 semantic-core pixels had zero changes, but a visible pale outer-curl halo remained; rejected. |
| `8fd8fd7aa5eead9deeb45878d732f5b0` | Five-pixel core shrink: 299,012 semantic-core pixels unchanged; halo remained; rejected. |
| `c91e2c36fce7d828c676a975a5341c0b` | Replaced the whole backing background and shrank final alpha two pixels. Core still unchanged, but the visible fringe remained; rejected. |

The remaining artifact is alpha/color decontamination at the fringe. The actual
face and dense hair are now protected exactly, but no scene candidate with the
visible fringe is approved or eligible for animation.
