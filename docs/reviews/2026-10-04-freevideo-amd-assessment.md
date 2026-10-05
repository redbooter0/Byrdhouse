# FreeVideo / MiniMax H3 assessment for Carey's PC

Date: 2026-10-04. Trigger: Carey supplied the RoundtableSpace post and screenshot
advertising local MiniMax H3 with 8 GB VRAM / 16 GB RAM.

## Decision for this installation

FreeVideo is a relevant existing image-to-video project, but its current
upstream implementation is **NVIDIA-focused and not qualified for this Windows
RX 7900 XT installation**. Keep it as a researched source candidate. Do not
replace the working ROCm environment with its CUDA installer or begin a custom
AMD port as a shortcut to the current production goal.

Read-only source clone: `D:\ByrdHouse\external\FreeVideo`.
Pinned commit: `98b3550ae551a70ae3f0a9a463f9dfc9a23b21a7`.
No setup scripts, package installs, model downloads, or FreeVideo generations
were run. It is outside ComfyUI's custom-node import directory.

## Hardware evidence

The installed ByrdHouse Python reports `torch 2.13.0+rocm10.0.0`, HIP
`7.15.26333`, CUDA version `null`, AMD Radeon RX 7900 XT, and Torch device
capability `(11, 0)`. ROCm exposes GPU operations through Torch's `cuda`
namespace, so finding that namespace alone does not prove NVIDIA-only code.

The stronger evidence is upstream's architecture policy and dependencies:

- `hardware.py` recognizes Ampere, Ada, Hopper and Blackwell NVIDIA families.
- `policy.py:463` explicitly states its NVIDIA target. Its numeric capability
  check alone would not reject this AMD device's `(11, 0)` value. However,
  unrecognized hardware takes the native-FP8 path rather than the measured
  Ampere BF16 weight-storage path. That is not an AMD compatibility proof.
- `torch_downloads.json` selects Python 3.12 Windows CUDA 13.0 Torch wheels.
  Current ByrdHouse uses Python 3.13 with ROCm. `pyproject.toml` requires
  Python >=3.12 and <3.13.
- `fp8_gemm.py`, attention backend selection, and runtime constraints depend on
  the project's CUDA/cuBLAS/Triton/Sage/FlashAttention ecosystem. A working
  ROCm kernel path was not found in the inspected checkout.

These findings establish that it is not a supported drop-in addition here.
They do not establish that an AMD port is mathematically impossible.

## What the memory/speed claim actually supports

The upstream capacity study uses an NVIDIA H200 with artificially limited
VRAM and RAM. Its consumer Windows timing table measures 1344x768, ten seconds
of video, two-pass sampling: RTX 5090 / 32 GB VRAM / 64 GB RAM takes 122 s;
RTX 5060 Ti / 16 GB / 32 GB takes 486 s; RTX 4060 Ti / 16 GB / 32 GB takes
558 s. The reported 8 GB consumer result uses **64 GB RAM** and takes 603 s.
Those are upstream measurements, not benchmarks of Carey's PC. Small memory
capacity does not imply fast generation; streaming can repeatedly read weights
from disk. Carey's 2 TB HDD remains an unmeasured bottleneck for that strategy.

## Fit with the show

The provided ComfyUI nodes accept first and last frames; image reference
conditioning is explicitly labeled experimental. This would fit approved
Carey-keyframe-to-motion work if hardware support is qualified later. It does
not itself establish facial continuity through every generated video frame.
The existing matching-view/hair/forehead/outline examiner and human review
would still be needed on sampled frames before episode use.

The code is Apache-2.0; H3 weights have a separate MiniMax H3 Community
License with restrictions. The screenshot's blanket open-source phrasing
does not replace the model license.

## Sources

- [FreeVideo repository](https://github.com/FlashML-org/FreeVideo)
- [Pinned hardware detection](https://github.com/FlashML-org/FreeVideo/blob/98b3550ae551a70ae3f0a9a463f9dfc9a23b21a7/freevideo_engine/hardware.py)
- [Pinned execution policy](https://github.com/FlashML-org/FreeVideo/blob/98b3550ae551a70ae3f0a9a463f9dfc9a23b21a7/freevideo_engine/policy.py)
- [Published execution and timing evidence](https://github.com/FlashML-org/FreeVideo/blob/98b3550ae551a70ae3f0a9a463f9dfc9a23b21a7/docs/execution-planning.md)
- [MiniMax H3 model license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)
- [User-supplied X post](https://x.com/roundtablespace/status/2106651786660737098)
  (web retrieval returned 403; the attached screenshot supplied its text).

## Parallel local work retained

Before this link arrived, the CivitAI-derived SDXL new-scene lab variant was
added to repo-side `windows-local/studio/server.py`. It crops the approved
anchor head for IP-Adapter and starts an empty latent while retaining the
existing SDPose/Union branch. All 160 Studio tests pass. This variant has
**not been deployed or rendered locally**; no likeness or speed qualification
is claimed. Next work should finish its live qualification and pursue an
existing AMD-compatible video workflow for reviewed Carey keyframes.
