# Animagine anime-anchor new-scene keyframe lab

**Date:** 2026-10-03
**Machine:** Windows, i9-10850K, Radeon RX 7900 XT (20 GB), 32 GB RAM
**Purpose:** qualify an existing SDXL anime character-workflow pattern for an
original ByrdHouse episode keyframe while protecting the owner-approved Carey
illustrated canon.

## Approved source and non-negotiable gate

Carey selected the supplied illustration as **Carey Anime Canon Anchor v1**:

`D:\ByrdHouse\assets\characters\carey-anime\anchor-v1.png`

- SHA256: `2f85df9f6efa92915b57d666dbd2c3e3467ae91e540f603156bc4084c0ff4640`
- Studio reference ID: `carey-anime-anchor`
- Status: approved visual source, **not** automatic approval for any derivative

The desired repeatable features are the irregular wide black afro, high natural
forehead/curl boundary, long-oval face, dark thick brows, warm almond eyes,
narrow rounded nose, broad smile, connected short beard/mustache, left-ear
stud, medium-brown cel-shaded skin, and clean dark linework. A render which
loses any of those is not an episode asset, even if pose or background works.

## Existing-workflow basis and local components

The shot used the established SDXL pattern from the staged CivitAI
IP-Adapter/ControlNet Union workflow and the public Game Character Multi-View
Style Transfer workflow description: a visual character reference plus a
separate pose map. Local implementation used:

| Component | Fixed setting |
|---|---|
| Base | Animagine XL 4.0 Opt, revision `2b7c1b397761bf5bd3cc42e5b39ec99314a75a96` |
| Checkpoint hash | `6327eca98bfb6538dd7a4edce22484a1bbc57a8cff6b11d075d40da1afb847ac` |
| Anchor conditioning | Existing ComfyUI IP-Adapter Plus Face, preset `PLUS FACE (portraits)`, weight `0.85`, `style transfer precise`, K+V embedding scaling |
| Pose | SDPose WholeBody from Carey's real full-body source, then ControlNet Union SDXL OpenPose |
| Pose influence | `0.65`, ending at 65% of the denoise path |
| Sampling | DPM++ 2M Karras, 30 steps, CFG 4.0, seed `381900` |

Sources: [Animagine XL 4.0 model card](https://huggingface.co/cagliostrolab/animagine-xl-4.0),
[CivitAI workflow reference](https://civitai.com/models/1024555),
and [Game Character Multi-View Style Transfer workflow](https://civitai.green/models/904547/game-character-multi-view-style-transfer-workflow?modelVersionId=1012223).
The full license/provenance decision is retained in
[`model-license-manifest.md`](../model-license-manifest.md).

## Result: reject this keyframe

| Field | Recorded value |
|---|---|
| Studio job | `97b0b62f810d753cec3bf3c836329261` |
| Output | `D:\ByrdHouse\media\images\97b0b62f810d753cec3bf3c836329261_1.png` |
| Render duration | 117.26 seconds |
| State | **Rejected** |
| Animation eligibility | **No** |

Visual review found an oversized smooth, nearly spherical afro; a small generic
face; lost beard/brow/mouth design; and a weak non-recurring background. It
does not read as the locked Carey character, so it cannot enter an anchor kit,
LoRA dataset, episode sequence, or animation queue.

The CPU face/hair/outline inspector also failed to locate a usable face in this
illustrated render. Its saved report is
`D:\ByrdHouse\media\images\97b0b62f810d753cec3bf3c836329261_1-identity-analysis.json`.
It records `similarity: null`, empty geometry values, and a detector error. That
means **inconclusive inspection / reject**, never a numeric pass or an identity
claim. Studio now captures that detector limitation as review evidence without
changing the still, auto-accepting it, or crashing the completed render.

## What changes before the next attempt

1. Make the next output a close, sharp portrait or controlled turnaround first;
   do not start with a full-body pose where the canonical face becomes tiny.
2. Preserve the locked anchor's hair silhouette and facial-hair/brow/mouth
   details in the visual review. The current generic spherical-afro outcome is a
   hard rejection criterion.
3. Build only Carey-approved front, three-quarter, profile, expression, outfit,
   and full-body frames into the illustrated anchor kit.
4. Train or qualify a show LoRA only from that reviewed kit, with source and
   settings recorded. Never use this rejected render as training material.
5. Animate a still only after visual continuity review. The separate Anchor v1
   motion test is recorded in
   [`2026-10-03-anime-anchor-motion.md`](2026-10-03-anime-anchor-motion.md).

This record preserves a real local outcome: the workflow wiring and AMD render
completed, but neither technical completion nor a detector score substitutes
for Carey's visual approval.
