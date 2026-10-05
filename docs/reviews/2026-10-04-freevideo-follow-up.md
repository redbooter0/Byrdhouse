# FreeVideo follow-up: newer source, Radeon alternatives, and the model license

Date: 2026-10-04, current Windows RX 7900 XT / 32 GB RAM PC. Carey supplied
the same RoundtableSpace link and screenshot again. This record supplements
the [first assessment](2026-10-04-freevideo-amd-assessment.md); it preserves
that snapshot instead of replacing its historical findings.

## Result for ByrdHouse

FreeVideo remains a source candidate, not an installed or qualified Radeon
generator. Continue using the already tested native Wan 2.2 5B route for local
Carey motion previews. Do not substitute advertised minimum memory for a
measured speed or character-continuity result on this PC.

H3 also has a material licensing constraint: the publisher's current standard
license excludes the United States, European Union, United Kingdom and Republic
of Korea. Its territorial grant and restrictions include model operation and
outputs. It describes obtaining a separate license for excluded territories.
FreeVideo's Apache-2.0 code license does not grant those model rights. No
separate authorization is recorded here; H3 remains outside this deployment.
Do not infer the user's location solely from a timezone. This records the
published terms, not a conclusion about a separate agreement Carey may hold.

Primary license: [MiniMax H3, pinned revision](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/42ed227ee7df40d41602854ae760620d6eb651fe/LICENSE).
The OpenVDN derivative's inspected license is byte-identical: SHA-256
`59b99642b95ea21630e311198ddbfffbfe05aadba0c2f5d884cbdf4efcc90f44`.

## What changed upstream

The original source checkout remains at
`98b3550ae551a70ae3f0a9a463f9dfc9a23b21a7`. A read-only fetch found
`a9098b7d893d314ce725522b0ba16e86c1a54324` on upstream main. Four newer commits
alter Windows placement choices, decoder compilation sharing, FP8 activation
storage and launcher signing. The complete diff is saved locally.

The hardware classifier, Windows Torch download manifest, Python requirement
and published execution-planning document are unchanged between these pins.
There is no new documented Radeon execution path in this diff. The inspected
classifier still lists NVIDIA architecture families, the policy retains its
NVIDIA target, and Windows setup selects CUDA 13.0 / CPython 3.12 wheels.
ByrdHouse's existing Python 3.13 / ROCm runtime does not match that installer.

Sources: [pinned hardware classifier](https://github.com/FlashML-org/FreeVideo/blob/a9098b7d893d314ce725522b0ba16e86c1a54324/freevideo_engine/hardware.py),
[execution policy](https://github.com/FlashML-org/FreeVideo/blob/a9098b7d893d314ce725522b0ba16e86c1a54324/freevideo_engine/policy.py),
[Windows Torch downloads](https://github.com/FlashML-org/FreeVideo/blob/a9098b7d893d314ce725522b0ba16e86c1a54324/freevideo_engine/torch_downloads.json),
[package requirements](https://github.com/FlashML-org/FreeVideo/blob/a9098b7d893d314ce725522b0ba16e86c1a54324/pyproject.toml).

The published Windows ten-second video benchmarks remain NVIDIA results.
The consumer 8 GB entry uses 64 GB system RAM and reports 603 seconds;
the 8 GB / 16 GB capacity headline is not that consumer benchmark. Neither
measures this Radeon, its 32 GB RAM or its model-library HDD. The lower-memory
placement can read weights from disk repeatedly, so the headline provides no
fast-episode promise here. See [the pinned measurements](https://github.com/FlashML-org/FreeVideo/blob/a9098b7d893d314ce725522b0ba16e86c1a54324/docs/execution-planning.md).

## Separate AMD implementations

AMD support for other H3 implementations is a separate question from support
in FreeVideo. Two additional primary-source snapshots were retained:

| Candidate | Publisher's reported scope | Fit with this installation |
|---|---|---|
| [GCStream/minimax-h3-rocm](https://github.com/GCStream/minimax-h3-rocm/tree/733459b4241bba54bc9a136cd1e5808a67b6cd5e) | W7900D, 48 GB VRAM, gfx1100, ROCm 7.2.1; approximately 8–9 minutes for a three-second 864x480 clip. Its GGUF diffusion load is reported around 46 GB. | Same architecture family does not make that 48 GB result a demonstrated 20 GB route. Not installed. |
| [rm-netsu RX 6700 XT profile](https://github.com/rm-netsu/comfyui-rx6700xt-minimax-h3/blob/a17b80190be05c9a254116c474d43a8364cd0207/rx6700xt-h3/README.md) | Native Windows, gfx1031 / RDNA2, pinned Python 3.12.9 and Torch 2.12, W4A8 kernels; 32 GiB RAM minimum and a default 64 GiB profile. It offers Balanced/Safe modes and describes per-prompt process recycling. | Architecture-specific fork rather than a drop-in improvement for gfx1100. Its performance and lifecycle settings are unqualified on this PC. Not installed. |

The previously saved [Windows ROCm hybrid H3 template](2026-10-04-native-wan-amd-qualification.md)
also remains a distinct candidate. Its missing custom nodes/models, external
prompt optimizer and inherited H3 model license are unresolved deployment
gates. No prompt, Carey photo or generated image was sent to an outside
optimizer. No upstream installer or source code was executed in this review.

## Existing local route was verified again

This follow-up performed read-only service and media checks, not another
generation. Studio reported connected and Wan ready. Comfy reported the native
RX 7900 XT with 21,458,059,264 bytes total VRAM. Windows reported 31.9 GiB
physical RAM. Both rendering queues were empty; services were not restarted.

Existing Carey Wan job `3d6490df1abea740c499afcbca8befe7` still has state
`needs_review`. Its retained 472.68-second render produced 33 frames at
384x576 / 24 fps, lasting 1.375 seconds. All 33 collected PNG hashes, the
approved anchor hash and the MP4 hash match their records. PyAV decoded all
33 frames at the expected dimensions and rate. Movie SHA-256:
`72e198d9b703a0fa5e87ddcca929b499900a5b5cc83599e76846e008fe87c51b`.

Preview: `D:\ByrdHouse\media\images\3d6490df1abea740c499afcbca8befe7.mp4`.
This does not establish fast production or exact animated likeness. The
[complete-frame review](2026-10-04-studio-continuity-review-validation.md)
retains the borderline afro-width flags at frames 5/7 and the mouth/detail
limitations. Carey's approved reference likeness remains canon; approving
that reference does not automatically approve every animated frame.

## Saved evidence and next work

Evidence directory:
`D:\ByrdHouse\external\workflows\freevideo-recheck-2026-10-04`.
`sources.json` records 13 source snapshots with revisions, byte counts and
SHA-256 values. `FreeVideo/changes-since-first-review.patch` preserves the
newer-source comparison. `local-health-and-preview-validation.json` records
the live read-only checks. Original staged checkout and working runtime are
unchanged. No packages, nodes or model weights were installed.

The production goal remains approved Carey stills in new poses/scenes, then
consistent shorts and episodes. Next implementation remains precise
hairline/forehead localization and target-aligned edits using the existing
mesh/semantic workflow, followed by sharper mouth/eye continuity and measured
video speed improvements. A new download does not solve those identity gates.
This follow-up changes the research record and deployment choice, not those
unfinished capabilities. No new runtime test-suite result is claimed for a
documentation-only change.
