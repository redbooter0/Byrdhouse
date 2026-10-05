# New-pose likeness lab — 2026-10-03

## Purpose

Separate two capabilities that were previously being conflated:

1. **Source-preserved scene swaps** retain camera pixels of Carey at the
   original pose and replace only the background.
2. **New-pose generation** must synthesize new pixels and requires a distinct
   identity-conditioning benchmark. It cannot be represented as an exact copy
   merely because a prompt says "Carey."

## Existing upstream components assessed

The PC already contained the Apache-2.0 `nosiu/comfyui-instantId-faceswap`
adapter and the official Apache-2.0 `InstantX/InstantID` SDXL adapter:

| Asset | Local evidence | Boundary |
|---|---|---|
| `ip-adapter.bin` | 1,691,134,141 bytes; SHA256 `02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1` | InstantID uses InsightFace/antelopev2; private local benchmark only. |
| InstantID ControlNet | 2,502,139,136 bytes; SHA256 `c8127be9f174101ebdafee9964d856b49b634435cf6daa396d3f593cf0bbbb05` | Present for later pose/keypoint experiments; not used by the first text-pose test. |
| antelopev2 | Five required ONNX files present under ComfyUI's InsightFace model path | InsightFace terms make this a private lane. |

The Studio `instantid` option submits these existing ComfyUI nodes through the
normal local job queue: `LoadInsightface → FaceEmbed → LoadInstantIdAdapter →
FaceEmbedCombine → InstantIdAdapterApply → SDXL`. Each job receives an immutable
snapshot of the selected Carey reference.

## Actual RX 7900 XT tests

| Job | Reference / result | Verdict |
|---|---|---|
| `9d0639e88e765317ab3d243f8ed5100e` | `neutral` reference; failed in 37.64 s with `No face detected for face embed` | Rejected. A detected reference is a precondition, not a fallback invitation. |
| `03d0136c835c24f33c652ff73d1c0b7a` | large front-facing `portrait`; a new full-body rooftop scene completed in 54.45 s | Rejected visually: Black subject, rooftop scene and clothing followed, but facial geometry, beard and hair did not read as Carey. |
| `e618e0fb98cf3a7d138a0ed1e30c7dc4` | attempted InstantID + existing FaceID Plus V2 layering | Failed in 27.44 s: `CrossAttentionPatch` has no `add`. Reverted; no compatibility claim. |

## Decision

Keep InstantID exposed only as a **private new-pose benchmark**. Do not animate
its outputs and do not mark an output approved unless Carey recognizes the
likeness. The source-preserved BiRefNet lane is the current reliable route for
scene swaps and still-to-video at the same pose.

The next useful improvement for true new-pose Carey stills is not another
zero-shot adapter combination. It is a carefully curated, real-photo SDXL
identity training set with hold-out references and visual gates for a front,
three-quarter, profile and full-body scene. Generated candidates must remain
separate from the real-photo dataset and must never be used to self-train.
