# Hardware and runtime review — 2026-10-03

Purpose: preserve a read-only audit of Carey's current Windows PC and the local ByrdHouse runtime, with a practical optimization order and checks that would demonstrate improvement. This review contains observations and proposals; no recommendation below has been implemented by this audit.

## Verified current hardware and storage

Windows CIM, `Get-Disk`, `Get-PhysicalDisk`, and `Get-Volume` reported:

| Component | Observed state |
|---|---|
| CPU | Intel Core i9-10850K, 10 cores / 20 logical processors |
| System memory | Approximately 32 GB usable RAM; 32,665 MiB reported by ComfyUI |
| GPU | AMD Radeon RX 7900 XT, 20,464 MiB VRAM; native AMD device reported by ComfyUI |
| GPU driver | Windows version `32.0.31041.1004`, driver date August 16, 2026 |
| C: | ADATA SU635, 240 GB SATA SSD; 27.1 GiB free at inspection |
| D: | Seagate ST2000DM008-2FR102, 2 TB SATA HDD; 1,563.5 GiB free at inspection |

These are current machine observations, not the historical RTX 3070 / two-PC arrangement described in parts of AGENTS.md. Free space and memory availability change over time. The measured hardware is sufficient for the SDXL and short portrait-motion workflows already completed locally; this does not prove suitability for every larger model or video workflow.

## Verified current runtime

The live ComfyUI `/system_stats` response reported:

- ComfyUI `0.38.0`, local Git commit `6b747c0428c343e1417219641db93a4fb7cb69ae`.
- Python `3.13.15` and PyTorch `2.13.0+rocm10.0.0`.
- GPU device `cuda:0 AMD Radeon RX 7900 XT : native`; the CUDA name is the API naming used by PyTorch, not evidence of an NVIDIA GPU.
- Frontend package `1.53.6`, workflow templates `0.11.70`, comfy-kitchen `0.2.36`, comfy-aimdo `0.5.5`.
- Launch arguments `--listen 127.0.0.1 --port 8188 --disable-api-nodes --extra-model-paths-config D:\ByrdHouse\extra-model-paths.yaml --output-directory D:\ByrdHouse\media\comfy --cache-ram 4 8 --disable-async-offload`.
- Empty running and pending ComfyUI queues at inspection.

ComfyUI/runtime reside on C:, while configured model and media libraries reside on D:. The current fast checkpoint is `RealVisXL_V5.0_Lightning_fp16.safetensors`; the base SDXL checkpoint is retained for the quality route. The RealVis file is approximately 6.46 GiB, and the CLIP Vision file approximately 2.35 GiB. These form part of a bounded active working set, not the whole model library.

An LM Studio Windows service process was present, but the standard `http://127.0.0.1:1234/api/v1/models` endpoint refused connection. This does not prove whether a model is loaded, whether another port is configured, or whether another application can reach its API.

Persistent evidence:

- [Deployment configuration](../../../byrdhouse-local.json)
- [Deployment launcher](../../../Start-ByrdHouse.ps1)
- [Current ComfyUI log](../../../logs/comfy.err.log)
- [Saved HIP failure log](../../../logs/comfy-launch-failure-20261003.log)
- [Image-lane handoff and benchmark context](../IMAGE_GENERATION_STATE.md)

The current log can be replaced on restart. The saved failure log is the retained failure evidence. Relative links to deployment files are intended for this checkout at `D:\ByrdHouse\repo`; they are machine-local evidence, not files committed inside the repository.

## Observed performance and limitations

The live Studio jobs API confirmed the following saved wall times:

| Job | Operation | Saved wall time / result |
|---|---|---|
| `844092163971861342a22339f3403dce` | Fast still | 9.78 seconds, needs review |
| `acdaef5a2ee676b581f6d658cb6dd56b` | Fast still after restoration workflow | 13.09 seconds, needs review |
| `6a479e91e333b6a276aed36a018c257b` | First RealVis still with loading | 92.71 seconds, needs review |
| `340675dd5849d9deafabad6b45b48620` | Fast still after restart | 130.11 seconds, needs review |
| `ad4cdb700a0364dc6cfceceb0323691e` | Fast still after earlier workflow switch | 139.05 seconds, needs review |
| `3cd314ab11006a65259279a8e221d6fb` | Identity correction | 49.5 seconds, needs review |
| `e42bab0d07e78825bc19b51ab65c422c` | Fast still | Failed after 95.57 seconds with HIP launch failure |
| `1b9e8a6e8f8606f347e260ed2b41a6e0` | Same-prompt retry after disabling async offload | 56.05 seconds, needs review |
| `43ec9f44984da64b6a8737de5bc39825` | Portrait animation | 42.43 seconds, needs review |

The handoff records approximately 4–5 seconds of sampling for the fast stills, much less than the cold/reload wall times. Loading and initialization are therefore material bottlenecks. This is consistent with an HDD-backed model library, but the audit did not isolate filesystem time from initialization or measure an SSD-versus-HDD A/B test. Warm 9.78–13.09 second times are examples, not a latency guarantee, median, or sustained-throughput measurement.

The saved failure log shows an unspecified HIP launch failure during VAE work and a subsequent prompt-worker termination. The identical retry succeeded after `--disable-async-offload` was enabled. That is evidence for retaining the mitigation while testing; it is not proof of root cause or long-run stability.

The CPU examiner benchmark in the handoff was 7.71 seconds at four threads versus 7.61 seconds at ten threads per original. This narrow observation does not justify dedicating all CPU cores to examination. It does not measure every ONNX or image workload.

Likeness remains unapproved. Hardware speed, passed geometry gates, and embedding scores do not establish an exact Carey replica. The current face swap preserves the generated hair; measuring that hair is not transferring Carey's hair. These constraints should remain visible in optimization decisions.

## Priority 1 — bounded SSD working set and fewer model switches

**Proposed:** preserve the HDD as the model library and archive, while staging the frequently used checkpoint, adapter, and encoder files in a bounded SSD cache. Configure the active paths explicitly, verify each staged file by checksum, and keep a free-space reserve for Windows, runtime updates, pagefile growth, and temporary files. Group rendering jobs by workflow/model when it does not violate user priorities or job dependencies.

C: has only 27.1 GiB free at this inspection. Copying the whole library is inappropriate; select the actual working set and its capacity before staging anything. No hardware purchase or deletion is authorized by this review.

**Why first:** fast sampling is already approximately 4–5 seconds, while loading examples exceed 90 seconds. Improving the loading path is more directly supported by evidence than changing GPUs or adopting speculative attention flags.

**Acceptance checks:**

1. Preserve model provenance and verify identical SHA256 before and after staging.
2. Record current free-space reserve and block a cache operation that would exceed its cap.
3. Run a controlled HDD-versus-SSD comparison using the same workflow, model, prompt, seed, dimensions, and current safe launch flags. Record cold startup, warm repeat, and restoration-to-generation switching separately.
4. Report loading, sampling, and total wall time separately; promote the cache only if the measured improvement is material and stable.
5. Ensure generated files, sidecars, review records, and archived models remain reachable through the configured paths.

## Priority 2 — one GPU queue with health and recovery

**Observed:** generation and animation use the Studio SQLite worker. `run_identity_belt` invokes correction synchronously through the request handler and has a separate belt lock. Its job record is registered after the work completes. It can submit Comfy work while the normal worker is active. LM Studio is not coordinated by this local worker. Studio startup currently marks every `running` job failed without reconciling its persisted Comfy prompt ID.

Source evidence: [Studio server](../../windows-local/studio/server.py), especially `__init__`, `run_identity_belt`, `run_next`, and `generate`; [identity belt](../../windows-local/studio/identity_belt.py), especially `_lock`, `_run_graph`, and `run`.

**Proposed:** submit correction through the same SQLite job queue as generation and animation, with parent/dependency records and a single GPU-ownership policy. Reconcile saved prompt IDs against Comfy history/queue before retrying or resubmitting. Add health that checks prompt progress and terminal errors, since a responding HTTP server alone does not prove a live prompt worker. Preserve the known-good runtime, extension commits, model hashes, and launch flags as a recoverable versioned profile. Coordinate LM Studio loading/unloading only after its actual API and model state are known.

Do not blindly restart on observation timeouts or blindly resubmit an ambiguous `/prompt` request. The goal is recovery without duplicated renders or interrupted valid work.

**Acceptance checks:**

1. Simultaneous generation, correction, and animation requests enter the queue and respect one GPU owner, with meaningful user-visible progress.
2. Restart Studio while a mocked backend prompt is live; reconcile the same prompt ID and produce one output set and one lineage record.
3. Simulate a dead prompt worker with a responding HTTP endpoint; health exposes the failure and queued jobs stop safely instead of appearing healthy indefinitely.
4. Confirm transient history timeouts do not produce duplicate prompt submissions.
5. After recovery checks pass, run a limited real sequence alternating generation, correction, and animation on this AMD profile, recording failures and timing. No claim of sustained stability until such evidence exists.

## Priority 3 — cache CPU reference analysis

**Observed:** the belt keeps examiner models loaded, but `run` re-examines the same reference, then the target, then both corrected candidates on each invocation. The parser and InsightFace/landmark sessions use CPU execution. Repeated analysis of unchanged original photos consumes time that can be reused without occupying the GPU.

Source evidence: [identity belt](../../windows-local/studio/identity_belt.py), especially `FaceRecord`, `_load_examiner`, `_load_face_parser`, `_load_landmarks`, and `run`; [CPU benchmark context](../IMAGE_GENERATION_STATE.md).

**Proposed:** cache original-photo embeddings, hair segmentation, hairline, jaw landmarks, pose, and image dimensions by source SHA256 plus examiner/parser model hashes and analysis schema version. Keep CPU examination on the i9 and reserve the GPU for rendering. Use these records to select pose-matched original references and populate clear feature-difference reports. Cache invalidation must accompany changes to the photo, weights, preprocessing, or metric definitions.

**Acceptance checks:**

1. An unchanged reference reuses its analysis and reproduces the uncached measurements.
2. Changing one photo byte, model hash, preprocessing version, or schema forces re-analysis.
3. Failed/missing segmentation and landmarks remain failures, never silently cached as accepted geometry.
4. Benchmark repeated belt work before and after caching, reporting CPU examination and GPU render time separately.
5. Confirm the report distinguishes measured differences from human visual notes and never labels an uncalibrated score as exact likeness.

## Audit scope

This was a read-only inspection of current Windows hardware, services, launch arguments, source, saved job results, and logs. No process restart, model install, download, GPU generation, or runtime edit was performed. The review does not validate a new model, confirm exact likeness, approve an animation, or prove sustained AMD stability. The proposals should be developed through the existing audited job and sidecar architecture rather than a parallel production bypass.
