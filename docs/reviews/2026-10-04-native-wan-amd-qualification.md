# Existing native video workflows on the Windows Radeon PC

Date: 2026-10-04. Current machine: RX 7900 XT 20 GB, i9-10850K, 32 GB RAM;
Windows Python 3.13.15, Torch 2.13.0+rocm10.0.0, ComfyUI 0.38.0.
Goal: reviewed Carey anime artwork into short scene-motion candidates through
the existing Studio job queue. No new renderer, runtime reinstall, or automatic
likeness approval.

## Sources and bounded adaptation

The [official ComfyUI Wan 2.2 examples](https://comfyanonymous.github.io/ComfyUI_examples/wan22/)
provide the complete 5B image-to-video workflow. Frozen JSON:
`D:\ByrdHouse\external\workflows\comfy-wan22-5b\image_to_video_wan22_5B.json`.
Upstream commit `f9431bb000ce792094ff345446e22cac1ea6cef3`, SHA-256
`2b1784c9d6ecf03462651d6e8ded7b5cc5e18047e9eb5e2a885fb6c89c5ac515`.
A byte-identical copy is retained at
`windows-local/workflows/upstream/comfy-wan22-5b.json`.

Models: [Comfy-Org Wan 2.2 repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged),
revision `ee6f4a40737a995bf5818954cfce6d59443b0f04`, Apache-2.0 model card.
Three files total 18,144,966,705 bytes. The modern Hugging Face CLI downloaded
only those three files. All lengths and SHA-256 values matched the Hub LFS
metadata before installation in D: model directories. Full destinations/hashes
are in `sources.json` beside the template and the model license manifest.
No video files were placed on C: and no extra CUDA wheels were installed.

The adapter keeps the upstream model/conditioning/latent links, 30 steps,
UniPC/simple, CFG 5, and sampling shift 8. Changes are:

- Carey source and movement/negative prompts replace the example subject.
- Bounded portrait previews: 384x576/33 frames or 576x832/49 frames, 24 fps.
- Native `VAEDecodeTiled`, tile 256/overlap 64, temporal 16/overlap 4 replaces
  ordinary decode. A [firsthand AMD Windows report](https://github.com/ROCm/TheRock/discussions/1477)
  identified tiled decoding as a workaround for Wan 5B VAE failures. This is
  prior evidence, not proof of stability on this PC.
- Save all decoded PNG frames into a job-bound directory; the existing
  `portrait_animation.py` durable collector verifies them and creates H.264.

Studio exposes `/api/scene-animations`, a disabled-until-installed scene-motion
button, and gallery video playback/review. Original photos, the specifically
allowed approved anime anchor, or explicitly approved still jobs can supply
the source. Unreviewed generated sources cannot enter this route. Sources,
specs, workflow, input snapshot, prompt ID and collected frames are hash-bound.
Resume collects the recorded submission without another `/prompt` POST.
Every output stays `needs_review`; changing clothes remains later work.

## Actual local tests and deployment

- 165 Studio tests pass, including template tampering, changed source,
  duplicate frame refusal, source/review gates, and recovery after removal of
  the original template. Existing LivePortrait recovery checks remain green.
- JavaScript syntax check passed. Browser confirmed the new control disabled
  before verified installation and enabled afterward. The first video job was
  queued by clicking it with `carey-anime-anchor` selected.
- Job `c4e2633cf248e124ad93e1e5895711b1`, seed `2192420816460563772`, failed
  before producing frames after 119.48 seconds. ComfyUI's dynamic VRAM
  `HostBuffer.read_file_slice` failed while fetching a Wan attention weight.
  This is a loader failure, not visual/likeness evidence and not proof that
  Radeon cannot infer the model. Full history, log, graph, and sampled
  resources are saved under the frozen template directory.
- A controlled same-source/same-seed retry, job
  `3d6490df1abea740c499afcbca8befe7`, succeeded with the existing core option
  `--disable-dynamic-vram`. Other startup settings stayed unchanged. Studio
  took **472.68 seconds**, Comfy execution **470.96 seconds**, with about
  **132 seconds** of sampling. The output is 33 frames at 384x576 / 24 fps:
  **1.375 seconds** of video. It remains `needs_review`.
- A second controlled test, job `fda13a693d3ab6340826dd8e1c55bfc6`, enabled
  Comfy's supported `COMFYUI_ENABLE_MIOPEN=1` setting. It also rendered, but
  took **694.64 seconds** in Studio and about **354 seconds** of sampling.
  It was approximately **47% slower overall** and used more VRAM. That
  setting is rejected for this tested configuration and was rolled back.
  The separate output remains `needs_review`; backend performance does not
  determine likeness acceptance.

Both successes use the same approved anchor, seed `2192420816460563772`,
movement prompt, workflow, tiled decode, and sampling parameters. The first
successful configuration used the default disabled MIOpen behavior. These are
individual cold runs, not a sustained throughput benchmark. Loading and
decoding contribute substantial time; only the sampler has a separately
observed duration, so do not assign the remaining time wholly to HDD loading.

| Run | Sampled device VRAM used | Sampled whole-system RAM used | Samples |
| --- | ---: | ---: | ---: |
| Static VRAM, default MIOpen off | 17.54 GiB | 30.01 GiB | 234, approximately 2-second spacing |
| Static VRAM, MIOpen enabled | 19.66 GiB | 29.04 GiB | 335, approximately 2-second spacing |

These are maximum sampled observations, not exact peaks or process-only RAM.
The tested PC has little RAM headroom during Wan inference. No concurrent
LM Studio model was added. The higher-resolution preset is still untested.
Full histories, logs and resource samples are saved beside `sources.json` as
`first-attempt-*`, `second-attempt-*`, `third-attempt-*` and job-bound
`*-resources.json` files. The working clip and all PNG frames are retained:

- `D:\ByrdHouse\media\images\3d6490df1abea740c499afcbca8befe7.mp4`
- `D:\ByrdHouse\media\animation\3d6490df1abea740c499afcbca8befe7\frames`
- `D:\ByrdHouse\media\animation\3d6490df1abea740c499afcbca8befe7\matching-view-review.json`
- `D:\ByrdHouse\media\animation\3d6490df1abea740c499afcbca8befe7\temporal-review.png`

The operator examiner selected the approved **three-quarter** view for frames
0, 8, 16, 24 and 32. All five passed hair, forehead and outline screens;
maximum outline error was `0.015024`, and maximum median hairline vertical
difference was `0.066103` of face height. No sampled skin-lightening warning
was raised. Visual inspection still found color fringing, some tooth/mouth
softness and shirt redraw. Sampling five frames is not full temporal review
or exact-identity proof. The examiner is still an operator tool, not an
automatic Studio approval stage.

Browser verification found both Wan videos loaded with `readyState=4`,
duration `1.375`, native controls and no media error. Their gallery cards
offer saving and separate motion review. The first successful clip is the
preferred candidate on speed grounds only.

The shared animation error report now extracts node/type/exception information
instead of truncating the tail of huge tensor dumps. This change is deployed
and passes the suite. No runtime, Torch package or custom-node reinstall was
needed for these tests. The frozen official template and source adapter remain
in the existing Studio queue; recovery collects the original prompt.

## Persisted launch and SDXL regression

After the MIOpen rollback, existing source-preservation job
`6048e11528ab334f6375f5c001377df8` completed through Studio. Comfy execution
was **60.08 seconds**, including about **8 seconds** of SDXL sampling.
All **499,269** frozen semantic Carey face-and-hair core pixels remained
byte-identical; **234,999** background pixels changed. The final image was
visually inspected. A thin light edge remains around parts of the afro, so
the candidate stays `needs_review` and was not animated. Its metadata,
Comfy history and log are saved beside `sources.json` as `sdxl-regression-*`.
This establishes one post-change SDXL regression, not sustained stability.

The live `D:\ByrdHouse\byrdhouse-local.json` now sets
`comfy_disable_dynamic_vram: true`. The existing `Start-ByrdHouse.ps1` reads
that option while retaining cache and async-offload settings. The config
also selects the already installed trusted base Python and explicit existing
`python_site_packages`; the launcher sets `PYTHONPATH` from that dependency
folder. This avoids the previously observed Windows App Control rejection of
the venv Python launcher, without installing another environment.

The persisted launcher was actually run with `-NoBrowser` after both queues
were idle. Both workers restarted successfully, Studio reported
`wan22_ready: true` and connected, and Comfy system stats confirmed the saved
arguments and unchanged Torch version. Startup again logged the default
AMD `cudnn.enabled = False`. The launcher passes PowerShell syntax parsing;
its source/deployed copies match. Old config and launcher are backed up in
`D:\ByrdHouse\backups\2026-10-04-wan22-studio`. Restore those two files to
undo this launch change only after checking the queues are idle; no model
deletion is required. Broader live mid-render recovery remains unqualified.

## CivitAI new-scene result

The previously source-only CivitAI IP-Adapter/ControlNet new-scene adapter was
deployed with this Studio change. Job `15a745b5272cda3fe8c73f8b0ed41003`
rendered a 1024x1024 close portrait in 126.15 seconds total; Comfy execution
92.76 seconds, sampler 14 seconds, remaining time includes model load/CPU review.
Visual inspection found altered eyes, face, beard and smile plus lighter skin;
it is **rejected**. It is not used for animation or training. The measured
report flags hair/forehead/outline differences; its similarity cue 0.187697
is not an identity percentage. The approved anchor is unchanged.

## Other existing AMD sources retained for next qualification

[TheChosenOn3's Windows ROCm workflow catalog](https://github.com/TheChosenOn3/comfyui-rocm)
is frozen at `1bf423f8f1d5e1b306e7a60df713cc370d53fac2`. Wan 2.2, LTX 2.3
and MiniMax H3 hybrid JSON templates and hashes are saved read-only under
`D:\ByrdHouse\external\workflows\rocm-windows-catalog`. No installer or nodes
from that distribution were executed. Some listed UUID node types represent
workflow subgraphs, not real missing Python node packs; the raw inventory
must be expanded before importing those larger templates.

The H3 hybrid template uses
[MiniMaxH3-Easy](https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy) and
`H3SLAAttentionROCM` from
[the sparse ROCm node fork](https://github.com/ethanfel/ComfyUI-PlagueKind-Nodes-only-sparse).
Those nodes and hybrid model files are absent locally. The template also has
an enabled third-party prompt optimizer pointing outside this PC: disable it
before any local-only import. No image or prompt was sent to that endpoint.
This is a different candidate from FreeVideo's reviewed CUDA installer, and
does not invalidate the specific FreeVideo assessment or establish H3 speed
on this machine.

The LightX2V 4-step LoRAs found in the official catalog target **14B expert
models**. They are not a valid plug-in acceleration for this installed 5B
model. Do not install them on the basis of the four-step headline.

## Remaining quality and speed gates

Inspect first, transition, middle and last frames for face outline, hairline,
afro, eyes, beard, mouth/teeth and skin-tone drift. Reuse the existing
matching-view reviewer; do not compare a profile against the straight-front
reference. Both presets are qualification previews below the official
recommended resolution, not demonstrated episode masters. Full-body action,
speech/lip-sync, shot transitions, 15–45 second sequences, and exact new-pose
stills remain unqualified. Model loading from the HDD is a separate timing
cost. Record sampled RAM/VRAM limits as sampled observations, not exact peaks.
