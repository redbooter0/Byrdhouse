# ByrdHouse architecture and Carey identity review

Review date: **2026-10-03**, America/Los_Angeles. This review describes the current single Windows PC with an RX 7900 XT, rather than the historical RTX 3070/two-PC installation.

## Scope and evidence standard

Carey's requirement is recognizable, faithful preservation of his specific facial features, skin tone, forehead, hairline and hair silhouette through still creation and subsequent animation. He has explicitly rejected approximate likeness. An embedding similarity, a heuristic measurement gate, an installed-model check or a successful render does not prove that requirement.

This was a read-only audit. It did not install models, edit runtime code, restart services, submit GPU work or rerun tests. The evidence below distinguishes direct observations from recorded prior tests, inferred failure risks and proposed changes. No exact-identity guarantee is made.

Principal sources:

- [Repository instructions](D:/ByrdHouse/repo/AGENTS.md), especially persistent image-state handoff, job accounting and metadata requirements. Its 3070/mini-PC hardware description is historical for this installation.
- [Current image-state handoff](D:/ByrdHouse/repo/docs/IMAGE_GENERATION_STATE.md:3), including the current correction and animation tests and the explicit unproven likeness verdict.
- [Current configuration](D:/ByrdHouse/byrdhouse-local.json) and [model path configuration](D:/ByrdHouse/extra-model-paths.yaml).
- [Studio server](D:/ByrdHouse/studio/server.py), [identity belt](D:/ByrdHouse/studio/identity_belt.py), [portrait animation adapter](D:/ByrdHouse/studio/portrait_animation.py), [manual recovery helper](D:/ByrdHouse/studio/recover_timed_out_jobs.py), and [report renderer](D:/ByrdHouse/studio/render_belt_report.py).

## Verified current behavior

During this audit, `GET http://127.0.0.1:8787/api/state` responded with `connected`, `base_ready`, `fast_ready`, `reference_ready`, `belt_ready` and `flux_ready` all true. These fields establish basic availability, not visual quality. Defaults were `sdxl`, `fast`, and original reference `portrait`; the photo count was 19.

`GET http://127.0.0.1:8188/queue` returned empty running and pending queues. Read-only SQLite queries showed 4 approved jobs, 30 awaiting review, 44 rejected and 1 failed, with no queued or running Studio jobs. Approval is the recorded user review state; it does not establish a calibrated exact-identity test.

SHA256 comparisons confirmed deployment/source-mirror equality for `server.py`, `identity_belt.py`, `portrait_animation.py`, `app.js` and `render_belt_report.py` between `D:/ByrdHouse/studio` and `D:/ByrdHouse/repo/windows-local/studio`. This is positive handoff evidence. The `windows-local` and `external` trees were untracked in the inspected Git checkout; matching local files do not establish that another machine can reproduce this installation from a committed revision.

The database independently confirms these recent recorded results:

| Operation | Job | Studio elapsed time | Interpretation |
| --- | --- | ---: | --- |
| Fast still, warm after restoration | `acdaef5a2ee676b581f6d658cb6dd56b` | 13.09 s | One measured warm switch; not a cold-start promise. |
| Fast still, cold | `340675dd5849d9deafabad6b45b48620` | 130.11 s | Model loading/initialization materially dominates sampling. |
| Earlier still after workflow switch | `ad4cdb700a0364dc6cfceceb0323691e` | 139.05 s | Historical pre-cache-change comparison. |
| Integrated identity correction | `3cd314ab11006a65259279a8e221d6fb` | 49.50 s | Separate review candidate; its SQLite `prompt_id` is null. |
| Studio original-photo animation | `43ec9f44984da64b6a8737de5bc39825` | 42.43 s | Short portrait-motion preview, awaiting review. |
| Retry after HIP launch failure | `1b9e8a6e8f8606f347e260ed2b41a6e0` | 56.05 s | One successful retry after configuration change. |

The failed job `e42bab0d07e78825bc19b51ab65c422c` contains a HIP launch-failure error. The handoff records that it terminated ComfyUI's prompt worker and that disabling async offload allowed the identical prompt/seed retry. Current config enables `comfy_disable_async_offload` and RAM cache headrooms of 4/8 GB. One successful retry is insufficient evidence of sustained AMD stability.

## Priority 1: one recoverable queue for all operations

### Verified queue bypass

Image generation and portrait animation go through the SQLite worker at [server.py:671](D:/ByrdHouse/studio/server.py:671). However, `/api/belt` calls `run_identity_belt()` directly from the threaded HTTP handler at [server.py:894](D:/ByrdHouse/studio/server.py:894). The belt performs examination, submits a ComfyUI workflow and waits for it inside that request; only afterward does `register_belt_candidate()` insert the completed review record at [server.py:576](D:/ByrdHouse/studio/server.py:576).

The belt's private lock at [identity_belt.py:513](D:/ByrdHouse/studio/identity_belt.py:513) serializes belt calls only. It is not shared with the Studio generation worker. ComfyUI normally serializes execution of its queued graphs, so this does **not** by itself prove simultaneous GPU kernel execution. It does permit concurrent Studio submissions, CPU examinations alongside rendering, hidden backend work and unexpected model switches outside the Studio queue's accounting.

The README's statement that SQLite prevents concurrent Studio GPU submissions therefore applies to queued still/animation jobs, but is too broad for the belt route.

### Inferred interruption and duplication risks

- A disconnected browser/request or Studio interruption can leave the belt's ComfyUI submission alive without a persisted job/prompt record. The UI cannot reliably show queued/running/failed correction progress.
- A user can repeat a correction after losing the response while the first backend submission continues. The present belt does not expose an idempotent operation identifier.
- A history-read timeout in [identity_belt.py:476](D:/ByrdHouse/studio/identity_belt.py:476) raises instead of using the still/animation history retry behavior. Rendering may continue despite a reported failure.
- A backend deadline expiring does not prove the prompt stopped. A subsequent job/retry should reconcile queue and history before assuming the GPU is free.

### Proposed change and acceptance checks

Make `/api/belt` enqueue an `identity_belt` operation and immediately return a job ID. Retain the existing SQLite queue and ComfyUI APIs. Record immutable target/reference hashes, workflow hash, selected face, submitted prompt ID and collection stage before presenting the correction as running or complete. Route all three operations through one worker and a common persisted submission/collection contract.

Acceptance: mock/API tests submit a still, a correction and an animation concurrently; all appear in queue accounting, are claimed once, and do not issue duplicate `/prompt` calls. A lost HTTP response must leave a discoverable job. History timeouts must preserve the same prompt ID. Correction failure must not approve a candidate or silently block subsequent work.

## Priority 2: restart reconciliation and operation-specific resume

### Verified current limitations

At [server.py:246](D:/ByrdHouse/studio/server.py:246), initialization changes every `running` job to `failed` with a message telling the user to submit again. It does not first inspect the persisted prompt ID in ComfyUI queue/history. That policy can conflict with an independently running ComfyUI process.

The still route accepts a resume prompt ID at [server.py:691](D:/ByrdHouse/studio/server.py:691), and its transient-history-timeout test verifies no second submission. The manual recovery helper recognizes successful node 9 image-output prefixes and failed jobs whose error contains `timed out`; see [recover_timed_out_jobs.py:26](D:/ByrdHouse/studio/recover_timed_out_jobs.py:26). It does not cover corrections, animation node 10, restart-marked failures or all crash windows.

The animation branch ignores `resume_prompt_id`; [portrait_animation.py:46](D:/ByrdHouse/studio/portrait_animation.py:46) always posts a new graph. This is a verified code property. Duplication is an inferred risk if the still resume method is later reused for animations without fixing the contract; this audit did not trigger a duplicate animation.

Animation writes `submission.json` and stores the prompt ID through a callback, which is useful audit material, but the current adapter has no resume/collect-existing-submission input. MP4 encoding interruption is also different from backend rendering interruption and should not require rerendering 44 frames.

### Proposed change and acceptance checks

On startup, reconcile unfinished operations against their exact prompt IDs and saved submission identifiers. If still queued/running, reattach monitoring; if completed, collect outputs; if terminal error, record that error; if state is genuinely ambiguous, expose a recovery state and do not automatically resubmit. Use operation-specific collectors so an animation can resume frame download/encoding without submitting new GPU work. Account for the POST-success-before-ID-persistence crash window with a unique job marker in the submitted graph/extra data and saved graph hash.

Acceptance: simulate restart while queued, while rendering, after render success, during output download and during video encoding. Each original backend graph executes at most once; outputs/sidecars remain linked to the same job; rejected animation sources stay rejected; source hash checks are repeated. Test a dead prompt worker separately from a responsive HTTP endpoint, because service reachability alone is not execution health.

## Priority 3: faithful identity through source preservation

### Verified shortcomings

The correction graph uses `inswapper_128.onnx`, optional restoration and a SAM blend; see [identity_belt.py:435](D:/ByrdHouse/studio/identity_belt.py:435). It corrects a generated face region while preserving the target hairstyle. The handoff explicitly records blur from the 128-pixel swap and that measuring hair is not hair transfer. GPEN improves observed cleanliness but reconstructs detail; it is not evidence that teeth, eyes, beard or skin texture are exactly Carey's.

The current generated candidate remains visually unapproved as an exact replica. The five noted differences—hair silhouette, forehead/hairline, eyes/brows, smile/teeth and jaw/beard—are explicit manual findings for one pair. The report renderer reads optional `visual_review.findings` at [render_belt_report.py:13](D:/ByrdHouse/studio/render_belt_report.py:13). New belt runs do not automatically create those findings.

FaceID guidance, a reference latent, prompt text stating Black identity and a trained LoRA can support likeness; none establishes exactness. The low-denoise photo-edit graph still diffuses face pixels. The current animation reconstructs moving facial pixels and has recorded softening, even when driven by the original portrait.

### Proposed change and acceptance checks

Prioritize a protected original face-and-hair route for scenes matching a real reference pose: reuse upstream segmentation, masking, background/outfit editing and compositing components, retaining reviewed original identity pixels through any explicitly recorded geometric transform. Display the protected region and edge composite before approval. Do not apply generative restoration or diffusion inside that region by default when source fidelity is the objective.

Keep novel poses, expressions and stylized identities as separate reconstruction candidates requiring review. Features not visible in a source cannot be established as exact by a score. A matching original reference offers stronger evidence than reconstructing an unseen profile from a frontal photo.

Acceptance: verify that protected face/hair regions pass the recorded deterministic preservation check, inspect mask boundaries/occlusions, and compare original/candidate at usable zoom. Carey reviews specific features. Any diffusion or restoration inside the protected region must be disclosed in metadata and must not receive an automatic exact-identity claim. Animation requires a second motion/identity review and cannot inherit exactness merely from still approval.

## Priority 4: reference bank, pose and multiface review

The reference manifest contains five entries, several derived from the same white-shirt original. The default correction uses one `portrait` reference. Nineteen library photos do not imply nineteen distinct, reviewed identities/poses; the bank needs an original-only provenance review.

The examiner selects the largest detected face at [identity_belt.py:335](D:/ByrdHouse/studio/identity_belt.py:335), whereas swap source/target indexes are both fixed to `0` at [identity_belt.py:442](D:/ByrdHouse/studio/identity_belt.py:442). They can select different people in a multiface image. This is an inferred edge-case risk from verified selection rules, not a demonstrated wrong-person render.

The jaw is normalized within the face bounding box, and [identity_belt.py:360](D:/ByrdHouse/studio/identity_belt.py:360) compares its 2D points directly. There is no 3D pose normalization or alignment to a matched view. Different yaw, pitch, smile and lens perspective can change this comparison without identity changing. The “pose-tolerant” comment exceeds the evidence.

Use a reviewed bank of genuine Carey originals tagged for pose, expression, hairstyle and capture quality. Require explicit face selection for multiface images and show the selected face before rendering. Reuse the installed upstream detector, FAN landmarks and semantic parser; add a thin matching/review layer instead of another vision framework. Align comparisons using stable landmarks, and mark occluded or pose-incompatible features as unmeasurable rather than wrong.

Acceptance: front, three-quarter and profile inputs select appropriate references; multiface examination and swap identify the same intended person; unmatched/occluded features display uncertainty; incorrect references are rejected. Keep raw and aligned comparisons with transform metadata so reviewers can see whether alignment concealed a meaningful difference.

## Priority 5: actionable measurements and faster examination

Current gates require similarity at least 0.65 plus forehead/hair/jaw checks. Thresholds are forehead-height delta ≤0.20, hair-width delta ≤0.60, jaw-outline error ≤0.24, with coverage/confidence requirements; see [identity_belt.py:387](D:/ByrdHouse/studio/identity_belt.py:387). They are uncalibrated heuristics. Eye and mouth ratios are computed, but do not establish the selected candidate's exact eye shape, nose, smile or teeth. Skin/hair darkness is affected by lighting.

Missing parsing/landmarks correctly fail the relevant gates. That useful conservative behavior should stay. Avoid converting `accepted` into likeness approval: it means only the implemented measurement screens passed. A clearer API name such as `measurement_checks_passed` should be used consistently.

Proposed review output: signed, pose-compatible differences for forehead/hairline, hair silhouette, eye spacing/shape, nose, lips, jaw and beard, alongside original and aligned overlays. Separate measured facts, manually reviewed descriptions and suggested corrections. Include parser/landmark uncertainty and pose limitations. Do not fabricate automatic findings from a generic description or a similarity score.

`run()` reinspects the original every time at [identity_belt.py:514](D:/ByrdHouse/studio/identity_belt.py:514). Cache original examinations by image SHA256, model hashes and analysis settings, invalidating on any change. Keep examiner models on CPU as presently implemented; recorded CPU timing did not justify increasing thread count.

Acceptance: coordinate-translation/padding tests remain green; missing data never passes; identical originals reuse cached examinations; a changed image/model invalidates the cache; output lists the actual measured discrepancy and units without calling it a calibrated identity probability. Check a small set of approved/rejected samples before choosing thresholds.

## Existing upstream components and test evidence

Preserve the verified, already-installed components rather than adding another chain of downloads:

| Component | Existing provenance and evidence | Current boundary |
| --- | --- | --- |
| RealVisXL V5 Lightning | [Creator model card](https://huggingface.co/SG161222/RealVisXL_V5.0_Lightning); local revision `f4454158cedaab9f0688c199561d6c92525f3a85`, verified SHA256 in [license manifest](D:/ByrdHouse/repo/docs/model-license-manifest.md:24). | Five-step DPM++ SDE/Karras, CFG 1.5; fast stills tested, identity unproven. |
| IP-Adapter FaceID Plus V2 | [Official FaceID model card](https://huggingface.co/h94/IP-Adapter-FaceID), installed upstream commit `a0f451a5113cf9becb0847b92884cb10cbdec0ef`, paired loader and companion LoRA; preserved example [workflow](D:/ByrdHouse/repo/external/workflows/upstream-ipadapter-faceid.json). | Corrected implementation supersedes the earlier appearance-only adapter mislabeled FaceID. |
| ReActor/SAM/GPEN | Verified repaired ONNX size 284,244,491 bytes, checksum and ONNX validation recorded in [manifest](D:/ByrdHouse/repo/docs/model-license-manifest.md:22). | Private evaluation; exact face/hair transfer unproven. |
| Impact FaceDetailer | [Upstream Impact Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) and preserved [example](D:/ByrdHouse/repo/external/workflows/upstream-impact-facedetailer.json). | Denoise 0.20/0.35 refinements were rejected for blur/drift; do not make them default without new evidence. |
| AdvancedLivePortrait | [Upstream implementation/workflows](https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait), commit `3bba732915e22f18af0d221b9c5c282990181f1b`; five model hashes/provenance under [models](D:/ByrdHouse/models/liveportrait/provenance.json). | Tested restrained blink/head movement, 44 frames at 15 fps; talking/full-body motion and exact likeness unproven. |

The handoff reports **25 focused tests passed** and records a browser/API animation test, playable video metadata and decoding of all 44 frames. This audit inspected test definitions; it did not rerun them. Coverage includes original animation hashes, approved still enforcement/rechecking, dual sidecar review, correction-parent preservation, paired FaceID loading, excluding double Lightning acceleration, timeout monitoring without still resubmission and request/path boundaries. See [Studio tests](D:/ByrdHouse/studio/test_server.py) and [structure tests](D:/ByrdHouse/studio/test_identity_belt.py).

Those tests do not yet demonstrate shared belt scheduling, restart reconciliation across operations, multiface agreement, pose-aware feature analysis, continuous AMD stability or exact visual likeness. Successful focused tests must not be described as proof of those broader requirements.

## Hardware-aware execution and durable handoff

Keep one GPU operation lane on the RX 7900 XT and avoid unnecessary SDXL/FLUX/video switching. Group requested work by operation/model while retaining explicit user order where it matters. Use the 2 TB HDD for the reference library, archives, outputs and cold models; prioritize sufficient SSD space for the active checkpoint/runtime if available. Recorded 13-second warm versus 130-second cold behavior makes storage/residency worth measuring before buying or downloading larger models. This review does not authorize deleting user files to make SSD room.

Pin extension commits, model hashes, runtime dependencies and tested API-format workflow JSON. The animation adapter currently derives inputs by zipping current `input_order` against example widget values at [portrait_animation.py:39](D:/ByrdHouse/studio/portrait_animation.py:39); an extension schema change can invalidate that mapping. Prefer a tested saved API graph with explicit schema validation and version provenance over silently translating a changed UI example at every run.

Update stale `CAREY_IDENTITY.md` and broad concurrency claims when implementing the changes. The current default is fast FaceID-guided SDXL, not the document's “Exact photo edit is the default” claim. Record the single-PC AMD deployment decision clearly so future agents do not restart old 3070/mini-PC setup loops.

Recommended implementation order: shared queue and recovery contract; source-preserving still route; reviewed reference bank and feature report; bounded likeness/motion validation; then storage/residency tuning. Use a small front/three-quarter/profile validation set and one short motion clip before expanding batches. Completion remains unproven until faithful approved stills and reviewed motion exist for the intended use cases; no metric or installation milestone substitutes for that result.
