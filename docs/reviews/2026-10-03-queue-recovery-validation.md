# Shared rendering queue and recovery validation

Implemented and tested locally on 2026-10-03. This updates the open queue findings
in the earlier [architecture review](2026-10-03-architecture-identity-review.md);
that dated review remains a record of the baseline, not current queue behavior.

## Result

Studio correction now joins the existing SQLite worker used by still generation
and portrait animation. The HTTP request validates and queues the correction
before rendering. Every correction has a job ID, source hashes, persistent
submission record and its own gallery review state. It is no longer executed
inside the HTTP handler or registered only after completion.

The worker serializes all Studio rendering operations, including concurrent
calls to `run_next()`. Interrupted recorded submissions enter `recovering`.
Studio reconciles ComfyUI history/queue before collecting or waiting for the
existing prompt; it does not automatically submit a duplicate. ComfyUI already
provides these interfaces: [official server routes](https://docs.comfy.org/development/comfyui-server/comms_routes).

The GUI now offers **Recover existing render** for a failed job with a saved
ComfyUI prompt ID. This queues collection of that submission with its saved
settings. It does not offer new rendering settings or POST another workflow.

## Implementation and provenance

- [Studio server](D:/ByrdHouse/studio/server.py): shared queue, worker execution
  lock, startup reconciliation, durable still journals, queued correction,
  source rechecks and the recovery endpoint.
- [Identity belt](D:/ByrdHouse/studio/identity_belt.py): deterministic run ID,
  saved graph/output mapping/source hashes, prompt-ID callback, monitoring and
  resume collection of the same submission.
- [Portrait animation adapter](D:/ByrdHouse/studio/portrait_animation.py): v2
  submission provenance, staged-input hash, exact saved workflow hash, partial
  frame collection and idempotent encoding/collection without another render.
- [Studio UI](D:/ByrdHouse/studio/app.js): correction queue status, recovery
  button, recovering-state display and clearing the pack filter so corrected
  results are visible. Corrected cards no longer reuse a correction status
  sentence as a new generation prompt.

Existing upstream ReActor/SAM/GPEN and AdvancedLivePortrait nodes and their
rendering settings were retained. No models or runtime packages were installed
for this change. The current AMD offload/cache flags were retained.

Submission records are saved before monitoring and before the SQLite prompt-ID
callback. A journal ID can close the gap if the callback fails or Studio stops
before the DB is updated. Ambiguous submissions with no recoverable ID refuse
blind retry. Missing backend records require inspection rather than a new POST.

Ordinary still submissions save the exact graph and settings hash. Recovery
uses that graph even if the installed default checkpoint changes. A legacy
still with no journal can use the actual graph from ComfyUI history; it refuses
recovery if that graph is unavailable. Legacy animation submissions without
the v2 provenance are refused. Failed collection retains the existing job ID.

## Focused test evidence

Command, from the deployed-source mirror:

```powershell
& 'C:\Users\carey\Documents\ByrdHouse\runtime\venv\Scripts\python.exe' -m unittest discover -p 'test*.py' -q
```

**63 tests passed**: 34 Studio tests, 3 geometry tests, 10 identity-resume tests
and 16 portrait-resume tests. The added cases exercise serialization, changed
sources, durable callback interruption, completed-history collection, temporary
observation failure, a completion race between queue/history reads, missing IDs,
workflow tampering, upstream numeric coercion, partial collection and no repeated
`/prompt` submission. These are mock/CPU tests; they are not evidence of exact
likeness or sustained AMD rendering stability.

Seven deployed/source files were SHA256 compared after the final deployment;
all matched. `git diff --check` passed. Rollback copies are in:

- `D:\ByrdHouse\backups\studio-queue-20261003-100449`
- `D:\ByrdHouse\backups\studio-queue-fix-20261003-101333`

## Live Studio evidence

The browser selected an existing pack, then submitted correction and original
photo animation. Correction returned promptly as a queued job, the gallery
filter cleared, and the animation waited until correction finished.

| Operation | Studio job | ComfyUI prompt | Observed result |
| --- | --- | --- | --- |
| Correction | `87e2a2d1e2336791766879e738644975` | `5f4c29af-d838-4357-a327-9c6768a1dc4c` | 54.56 s; `needs_review` |
| Original-photo animation | `aafca1c98eba4c671445df41d245ae09` | `371274e1-790e-43e5-af31-3273b2c77938` | 42.63 s accumulated execution/collection time; `needs_review` |

Correction finished at 10:07:19 local time; animation started at 10:07:19. Its
first collection attempt failed after rendering because the strict history
hash compared integer FLOAT inputs with ComfyUI's coerced float values.

The cause was verified in installed `execution.py`: upstream input validation
changes values such as `blink=-8` to `blink=-8.0`. The corrected collector accepts
only equivalent finite integer-to-float conversion for explicit LivePortrait
FLOAT fields and the upstream node-level `is_changed` cache annotation. Node
IDs, types, input keys, links, booleans, source bindings, motion command and output
prefix remain strict; the saved workflow hash remains exact.

The GUI recovery button collected the **same completed prompt**. ComfyUI's queue
remained empty: no second render was submitted. The ComfyUI process remained
PID 6840 throughout this validation. Saved proof is
[queue-recovery-validation-20261003.json](D:/ByrdHouse/logs/queue-recovery-validation-20261003.json).

Recovered video validation:

- HTTP 200, `video/mp4`, 429,249 bytes.
- 44 saved PNG frames; FFmpeg decoded all 44 with exit code zero.
- Browser readyState 4, 1152x1536, 2.933333 seconds, no reported playback error.
- Original source was `references/portrait.jpeg`; the staged input/source hashes
  and workflow are retained alongside the frames.
- The recorded seconds include the previous rendering attempt plus recovery
  collection; they exclude the manual interval while fixing the collector.

The [corrected still](D:/ByrdHouse/media/images/87e2a2d1e2336791766879e738644975_1.png)
and [hairline/jaw report](D:/ByrdHouse/media/images/belt-87e2a2d1e2336791766879e738644975.png-analysis.png)
were visually inspected. The [recovered video](D:/ByrdHouse/media/images/aafca1c98eba4c671445df41d245ae09.mp4)
loaded in the browser; frame 14 was inspected. The corrected still retains the
generated spiky/tall hair and changed teeth/details, so it is **not an exact
replica**. Portrait motion reconstructs and softens facial details. Neither
candidate was approved; metadata continues to say `identity_verified: false`.

## Limits and next work

An attempted live interruption was skipped because the jobs had already reached
terminal states before the action. No active process was stopped for that test.
Mid-render Studio restart reconciliation is covered by mocks, not yet a live
interruption test. Two serialized live jobs and one recovered collection do not
prove sustained AMD stability or detection of a dead ComfyUI prompt worker.

Still generation currently stores a reference hash from its manifest but does
not rehash the actual ComfyUI reference input before execution. Correction and
animation recheck their sources; the ordinary-still binding gap remains open.

Next: reuse the installed semantic face/hair parser and core inpaint/composite
workflow to preserve original Carey head pixels through a scene edit. Verify a
reviewed protected mask and exact final pixel equality inside it. Then benchmark
the bounded SSD model cache. Pose-matched reference selection, feature reports
beyond hairline/jaw and exact likeness through new poses/motion remain unfinished.
