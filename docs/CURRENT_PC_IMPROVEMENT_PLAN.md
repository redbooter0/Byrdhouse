# ByrdHouse on Carey's current PC

2026-10-04 boundary implementation: connected semantic head-hair selection
removes the tested eyebrow leakage; code/model hashes bind new queue reviews
to V2 measurements and a separate approved-anchor profile. The official
5.42 MB CPU mesh model and current-PC resolver now make the existing 478-point
analysis command work. 183 tests pass. This restores edit guidance foundations,
not an accepted face swap. Continue with semantic-zone/current-reference
qualification and target-aligned edits; do not use the old target-eyes/hair
defaults as automatic episode identity policy. See
[evidence and open gates](reviews/2026-10-04-hairline-v2-and-face-mesh.md).

2026-10-04 FreeVideo follow-up: newer code retains the reviewed NVIDIA/CUDA
installer path. Separate H3 Radeon ports do not supply a tested result on
this 20 GB / 32 GB PC, and the standard H3 license has explicit territorial
exclusions. Keep native Wan as the tested local preview route while advancing
Carey facial continuity and measuring speed. Read
[the newer-source and license record](reviews/2026-10-04-freevideo-follow-up.md)
before reopening an H3 installation proposal.

2026-10-04 continuity implementation: the previously operator-only examiner
now has a queued Studio action with matching approved views, all collected
video frames, saved reports and explicit inconclusive cases. Full checking
found two borderline afro-width flags missed by the sampled review. A live
CPU-check restart passed; GPU-render restart remains a separate open gate.
See [actual results and limits](reviews/2026-10-04-studio-continuity-review-validation.md).
Prioritize precise boundary localization and target-aligned face edits next;
new regenerated poses and episode-quality mouth detail are still unfinished.

2026-10-04 implementation update: the official native Wan 2.2 5B workflow
now renders through Studio on the RX 7900 XT. The 1.375-second Carey candidate
took 472.68 s; this proves a local preview route, not fast episode production.
Static VRAM resolved the first loader failure, while enabling MIOpen worsened
the controlled run and was rolled back. Sources, sampled memory, current
startup and remaining face/motion gates are saved in
[the native video record](reviews/2026-10-04-native-wan-amd-qualification.md).
Avoid concurrent large language-model loading during these near-32-GB RAM
video runs. Further model expansion is secondary to visual continuity and
measured model-load/decode improvements.

Baseline proposal, 2026-10-03. The implementation update below records which
changes have since been completed. Exact generated likeness and sustained AMD stability remain
unapproved. Detailed findings are indexed in [reviews/README.md](reviews/README.md).

Later on 2026-10-03, the shared correction queue and operation-specific recovery
were implemented. [63 tests and live collection evidence](reviews/2026-10-03-queue-recovery-validation.md)
document the outcome and remaining qualification gaps. The proposal below
preserves its original baseline; use that implementation record for current state.

The [source-preservation validation](reviews/2026-10-03-source-preservation-validation.md)
now records 138 passing tests, fixed per-job reference snapshots and two local
scene edits whose protected pixels were identical to the original. Both scenes
were rejected for retained background around the hair. Pixel preservation works;
boundary quality, new poses and animation exactness remain unfinished.

The PC is capable of the tested SDXL and portrait-animation workflows. I would
prioritize Carey's actual identity, recoverable jobs and less model loading
before expanding the model library. Keep mini-PC work deferred.

## Hardware allocation

| Component | Verified on this PC | Intended role |
| --- | --- | --- |
| RX 7900 XT | 20,464 MiB VRAM; native AMD execution | One active rendering workload at a time |
| i9-10850K | 10 cores / 20 threads | Reference analysis, queue, encoding and orchestration |
| RAM | Approximately 32 GB | Bounded model cache with measured Windows headroom |
| C: SATA SSD | ADATA SU635 240 GB; 27.1 GiB free | Runtime and a small active-model cache |
| D: SATA HDD | Seagate ST2000DM008 2 TB; 1,563.5 GiB free | Model library, photos, outputs and archives |

Keep the native AMD runtime while qualifying it. Installed versions are ComfyUI
0.38.0, Torch 2.13.0+rocm10.0.0 and Python 3.13.15. Actual launch flags include
`--cache-ram 4 8 --disable-async-offload`. The current
[official ComfyUI Windows instructions](https://github.com/Comfy-Org/ComfyUI#amd-gpus-windows-rocm-100)
list the RX 7900 XT as `device-gfx1100` and document this Torch/ROCm family.
These findings do not indicate a need for a new GPU.

## Measured baseline

| Local operation | Time | Limit of this evidence |
| --- | --- | --- |
| Fast SDXL still, warm | 13.09 seconds | One measured warm workflow switch |
| Fast SDXL still, cold | 130.11 seconds | Sampling was about 4–5 seconds; loading dominates |
| Face correction | 49.5 seconds | Candidate is not approved for exact likeness |
| Original-photo portrait motion | 42.43 seconds | 44 frames, 15 fps, 2.93-second clip; visible softening |

These are observations, not speed promises. Another warm workflow switch
triggered a HIP launch failure and terminated ComfyUI's prompt worker. The
identical retry completed in 56.05 seconds after async offload was disabled.
One successful retry does not establish sustained stability. Saved job IDs,
outputs and qualifications are in [IMAGE_GENERATION_STATE.md](IMAGE_GENERATION_STATE.md).

## First: one recoverable queue

Generation and animation already use SQLite. Correction runs inside the HTTP
request handler, outside that worker, and inserts its gallery record after
finishing. Its private lock cannot serialize it with the other operations.
Studio startup marks every running job failed without checking the saved
ComfyUI prompt ID.

Enqueue correction before execution and let the existing worker own all three
operations. Persist source hashes, workflow hashes and submission IDs. After a
restart, collect completed outputs or resume waiting for the existing prompt
before considering a new submission. Animation needs a separate collection
function: calling the current `animate()` again submits another prompt.

Track actual queue/history progress. An HTTP response does not prove ComfyUI's
prompt worker is alive. On execution failure, pause later rendering, reconcile
jobs and retain the log before controlled recovery. A cold load or timeout alone
must not trigger an automatic restart or duplicate submission.

Acceptance: restart tests for each operation demonstrate one submission and one
artifact record; correction waits behind other rendering; pending jobs survive
a Studio restart. Then run a short live mixed-operation qualification.

## Second: reduce loading with a bounded SSD cache

Keep D: as the model library. Stage only the frequently used RealVisXL checkpoint
on C: first. It is 6,938,065,512 bytes, about 6.46 GiB, leaving approximately
20.6 GiB at the measured free space. Recheck space immediately before copying
and reserve at least 20 GiB for Windows. Do not put the full model library on C:.

Hash-check the copy and use ComfyUI's supported additional-model-path
configuration to prefer it while retaining the HDD copy. Benchmark identical
prompt/seed cold runs before and after. Promote the cache only after it reduces
loading without hurting stability; the improvement has not yet been measured.

Group stills, corrections and animation into deliberate phases that respect
review dependencies and visible queue order. Retain the current async-offload
mitigation during qualification. Record total time, loading, sampling and
RAM/VRAM peaks; report median and slowest runs and all failures.

## Third: preserve Carey when exactness is required

FaceID reconstructs a face. The correction belt uses a 128-pixel face-swap model
and generative restoration while retaining the target's generated hair. Hair
measurement does not transfer Carey's hairline or silhouette. Neither geometry
gates nor embedding scores prove an exact replica.

For an exact-face scene, start with a reviewed original photo and protect the
face, hairline, ears and hair during background/outfit editing. Reuse upstream
segmentation, masked editing and compositing nodes. Define a protected interior
whose pixels match the original and blend only outside it. This can preserve
source detail at the source pose; it cannot invent an exact new pose/expression.

Keep new poses and anime in a reconstructed-candidate route. FaceID and the
experimental Carey LoRA may guide it, but candidates require visual review.
Keep the existing LoRA at zero by default until it passes comparisons across
poses. LoRA loading already works; local AMD/Windows retraining has not been
qualified. Train only from a curated real-photo bank, not synthetic lookalikes.

Acceptance: one changed scene with unchanged protected face/hair pixels,
documented mask and pixel/hash checks; reconstructed results explicitly remain
candidates until Carey accepts their visible likeness.

## Fourth: useful reference selection and feature reports

Review the 19 local photos and five reference entries. Exclude screenshots,
generated contact sheets and synthetic lookalikes. Label genuine photos by head
angle, expression, hairstyle, lighting and quality. Choose a matching source
and explicitly select the target face in images containing multiple people.

Reuse InsightFace, FAN landmarks and semantic parsing on the CPU. Cache original
examinations by source SHA256 plus model/examiner versions. The recorded CPU
benchmark was 7.71 seconds at four threads versus 7.61 at ten; it does not justify
consuming every CPU core.

Show aligned source/output images and outlines for hair/forehead, eyes/brows,
nose, lips/smile/teeth and jaw/beard. Report differences, confidence and pose
mismatch. Keep lighting variation distinct from skin-tone changes. Preserve
Carey's Black identity and actual facial proportions. Similarity is never a
percentage of identity.

Current automatic gates cover only forehead/hair/jaw and are uncalibrated. The
existing five-feature annotation is manual review of one candidate, not an
automatic diagnosis for every output. Reports must distinguish measured
differences, uncertain observations and human judgment. A language model can
explain detector evidence; it must not invent measurements or approve likeness.

## Fifth: reviewed short animation, then expansion

Keep the installed upstream
[AdvancedLivePortrait workflow](https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait)
for blink and gentle head-motion previews. The Studio button is already tested.
It takes an original reference or an approved still and gives motion its own
review record. The tested output reconstructs moving face pixels and softens
details; it is not exact or final-quality animation.

Inspect sampled and transition frames for eyes, mouth, jaw and hair drift before
extending duration or adding speech. Camera motion over a retained photograph
is useful when unchanged facial pixels matter more than facial motion.
Full-body animation and talking clips require their own hardware/likeness tests.
Expand to larger video models only after the short workflow is acceptable.

## LM Studio's supporting role

[LM Studio](https://lmstudio.ai/docs/app) runs local language models. Use it for
shot planning, prompt preparation and explanations of measured review evidence.
ComfyUI owns SDXL/FLUX rendering. Unload a GPU-heavy LM Studio model before
rendering, or separately benchmark a small CPU assistant. Its service was
running during the audit, but the standard local API port refused connection;
the integration is not verified.

## Completion criteria and next handoff

Implementation order: recoverable queue; measured SSD cache; source-preserved
Carey still with a useful feature report; reviewed short animation; then expanded
pose packs, LoRA training or larger video models.

Success means Carey accepts the identity and motion, timings repeat on this PC,
restarts do not duplicate jobs, and every artifact preserves provenance/review
state. Benchmark passes alone do not satisfy the likeness requirement.

This review did not move models, reinstall runtimes or run new GPU workloads.
Deployment and principal `windows-local` files matched. Existing validation is
25 focused tests and a browser-loaded 44-frame animation. Those checks do not
mean the proposed improvements above are implemented.
