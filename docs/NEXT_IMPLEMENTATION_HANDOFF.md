# ByrdHouse — Fable Next-Implementation Handoff

**Prepared for:** Fable
**Project:** ByrdHouse
**Primary repository:** https://github.com/redbooter0/Byrdhouse
**Current phase:** Identity Engine verification, workflow tournament, app-gap analysis, and local coding independence
**Primary hardware target:** RTX 3070 8GB VRAM, i9-10850K, 32GB DDR4
**Primary outcome:** A dependable one-click local application that can take a target such as Vegeta, Gojo, a gaming character, anime character, photograph, or cinematic scene and re-create the subject as the user while preserving the target’s style, pose, expression, outfit, lighting, composition, and scene.

---

# 1. Read This First

Do not treat this as a request to install every linked workflow.

Your job is to:

1. Inspect the live ByrdHouse repository.
2. Inspect the existing working workflows and current identity code.
3. Compare the linked external workflows and MCP tools.
4. Determine what ByrdHouse is actually missing.
5. Select the smallest set of next implementations that closes those gaps.
6. Build and verify those implementations on the user’s real hardware.
7. Preserve the current working stack and provide rollback.
8. Produce a clear current phase → next action → checkpoint report.

The user does not want another collection of disconnected experiments. The user wants ByrdHouse to become a working local product.

---

# 2. The Exact User Outcome

The user wants to get home, update either BYRD-MINI or BYRD-GAMING, select an existing target such as Vegeta, Gojo, or another saved target, select the user’s identity folder, and generate a result that looks like:

> “This target character is now me, naturally integrated into the original art style and scene.”

The result must not look like:

> “A small piece of my face was pasted onto Vegeta or Gojo.”

The system must understand the difference between a basic face swap and a full character re-identity operation.

## Required operator experience

```text
Open ByrdHouse
    ↓
Choose target image
    ↓
Choose identity
    ↓
Choose mode:
    Fast Face Swap
    Head / Identity Transfer
    Full Character Re-Identity
    Realistic-to-Gaming
    Anime Identity
    Manual Rescue
    Final Refine + Upscale
    ↓
Press Generate
    ↓
ByrdHouse performs hidden operations
    ↓
User receives:
    final image
    intermediate evidence
    score
    explanation
    retry choices
```

The user should not need to understand ComfyUI node wiring.

---

# 3. What “Full Character Re-Identity” Means

ByrdHouse needs at least three clearly separated identity modes.

## Mode A — Face-only swap

Replace the inner facial identity while preserving:

- target hair
- target ears
- target neck
- target head shape
- target outfit
- target body
- target scene

This is useful for fast tests but is not enough for the main ByrdHouse vision.

## Mode B — Head and identity transfer

Replace or adapt:

- facial geometry
- jaw
- cheek structure
- eyes
- nose
- mouth
- skin tone
- ears
- hairline
- neck transition
- age and facial proportions

Preserve:

- target hairstyle when requested
- target expression
- target pose
- target costume
- target lighting
- target art style
- target scene

This should be the default for Vegeta, Gojo, anime, gaming, and cinematic targets.

## Mode C — Full character re-identity

Reconstruct the entire visible character as the user while preserving the target concept.

Potentially adapt:

- face
- head shape
- hairline
- ears
- skin
- neck
- visible body proportions
- hands when identity-relevant
- tattoos or distinguishing features
- age and build
- outfit fit
- stylized anatomy

Preserve:

- Vegeta remains recognizably Vegeta-themed
- Gojo remains recognizably Gojo-themed
- the target costume and powers remain
- target pose and expression remain
- target composition and camera remain
- target background remains unless the user asks to change it
- the final rendering remains in the target’s anime, game, realistic, or painted style

This is not ordinary face swapping. It may require a combination of:

- identity reference conditioning
- targeted inpainting
- face/head segmentation
- geometry-aware masks
- style conditioning
- identity LoRA
- IP-Adapter / PhotoMaker / InstantID / PuLID / similar identity methods
- a direct swapper as one branch
- local refinement
- controlled upscaling
- quality ranking

Fable must determine which combination works best on 8GB VRAM.

---

# 4. Project Outlook

ByrdHouse is becoming a local creative operating system.

## Long-term application lanes

### Identity Engine

- Managed identities for the user and approved friends/family
- Multiple reference images per identity
- Consent and usage policy
- Reference ranking
- Face/head/body feature extraction
- Identity consistency across styles
- Identity LoRA support where appropriate
- Private, funded/internal, and public/commercial route separation

### Image Engine

- Target-first image editing
- Face swap
- Head/identity transfer
- Full character re-identity
- Realistic-to-gaming
- Anime transformation
- Costume and object replacement
- Background preservation
- Auto-mask
- Manual-mask rescue
- Face repair
- Refine
- Upscale
- Metadata and evaluation

### Video Engine

Future lane:

- identity-consistent frames
- scene and skit generation
- user-approved friends and family in themed scenes
- character cutaway and memory-style skits
- automatic clipping
- captions, titles, hashtags
- review and approval
- posting schedule
- analytics
- learning feedback

### Local Coding Engine

- OpenCode or equivalent local client
- LM Studio local models
- repository read/search/patch/test/review
- feature branches
- safe command allowlist
- second-model review
- no dependence on Codex usage availability

### Learning Loop

Every generation must have:

- a purpose
- inputs
- workflow version
- models
- parameters
- masks
- intermediate outputs
- scores
- user rating
- failure reason
- retry history
- eventual performance or usage result

ByrdHouse must become better at selecting workflows and parameters as more images are generated.

---

# 5. Current Hardware and Topology

## BYRD-GAMING

- Windows
- Root: `E:\ByrdHouse`
- RTX 3070
- 8GB VRAM
- Intel i9-10850K
- 32GB DDR4
- LM Studio: `http://localhost:1234`
- ComfyUI: port `8188`
- Main GPU worker
- Current image-generation and model-serving machine

## BYRD-MINI

- Windows
- Root: `D:\ByrdHouse`
- Ryzen 5 6600H reported
- 8GB RAM reported
- Qdrant
- SQLite memory
- Router
- Worker
- Dashboard
- MCP and orchestration plane

## iPad Pro

- Mobile cockpit
- Intended application control surface
- Dashboard, queue, review, approve, retry, and compare

## Planned scaling

- Keep RTX 3070 as Worker 1
- Add RTX 4080-class Worker 2
- Later add RTX 5090-class Worker 3
- Do not design the application around replacing the current machine
- Design for a worker pool

---

# 6. What Already Works

The repository contains a real foundation.

## Primary repository

- https://github.com/redbooter0/Byrdhouse

## ByrdCast Swap V0

- https://github.com/redbooter0/Byrdhouse/blob/main/scripts/byrdcast_swap.py
- https://github.com/redbooter0/Byrdhouse/blob/main/configs/byrdcast_swap_v0.json
- https://github.com/redbooter0/Byrdhouse/blob/main/workflows/byrdcast_swap_v0.json
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/BYRDCAST_SWAP_V0.md

Current intended behavior:

- validate target and references
- detect main target face
- detect reference faces
- rank references
- create face/jaw/hairline/ears/neck/skin masks
- execute ReActor through ComfyUI
- use in-process InsightFace fallback
- optionally use FaceDetailer
- score the candidate
- save intermediate evidence
- fail closed when weak

## Current planning, safety, and benchmark files

- https://github.com/redbooter0/Byrdhouse/blob/main/docs/identity-benchmark.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/identity-stack-review.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/fable-implementation-report.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/current-machine-inventory.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/model-license-manifest.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/agent-safety-policy.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/STATE.md
- https://github.com/redbooter0/Byrdhouse/blob/main/docs/DECISIONS.md

## Current preflight and test files

- https://github.com/redbooter0/Byrdhouse/blob/main/scripts/byrdhouse-preflight.ps1
- https://github.com/redbooter0/Byrdhouse/blob/main/scripts/identity-benchmark.ps1
- https://github.com/redbooter0/Byrdhouse/blob/main/scripts/facelab_preflight.py

## Other existing lanes

- Direct ReActor
- ReActor style blend
- Manual zone inpaint
- Automatic FaceDetailer
- Face Lab dashboard/router/worker integration
- Realistic-to-gaming workflow experiments
- Flux2 Klein style transfer and upscale
- LoRA dataset preparation
- LoRA training scripts
- ComfyUI API execution
- Image archive and metadata
- Qdrant and SQLite memory
- Dashboard and router
- BYRD-MINI orchestration to BYRD-GAMING GPU execution

---

# 7. The Working Workflow We Want to Emulate and Improve

## Reference video

- https://youtu.be/l4CiwGS2ewY?is=TM2HZKOTLBDxQBR1

## Original shared Flux2 Klein workflow

- https://www.dropbox.com/scl/fi/ko0l707206ver40p02533/Flux2-Klein-Style-Transfer-Upscale.json?rlkey=s55r4793w4wey4sqbw83edmc8&st=wj5ab0x5&dl=0

## Related NVIDIA toolkit reference

- https://github.com/NVIDIA/NVIDIA-GenAI-Creator-Toolkit

## What the workflow proved

A single ComfyUI workspace can coordinate:

- target image
- reference image
- text instruction
- style transfer
- costume/object reference
- composition preservation
- image transformation
- upscale
- final output

## What ByrdHouse must emulate

Do not copy only the node graph.

Emulate the operating method:

```text
One visible user goal
    ↓
Multiple hidden processing stages
    ↓
Intermediate quality checks
    ↓
Automatic correction or retry
    ↓
Final output + evidence + metadata
```

ByrdHouse should eventually perform better than the source workflow because it has:

- managed identities
- reference ranking
- target classification
- workflow routing
- real quality scoring
- failure recovery
- learning memory
- multiple worker support
- application UI
- historical performance data

---

# 8. What the App Is Currently Lacking

Fable must inspect the current app and verify each gap instead of assuming it is already solved.

## 8.1 No complete target-to-result product flow

The dashboard and router exist, but the user does not yet have a reliable application flow where they can:

1. choose Vegeta, Gojo, or another target
2. choose their identity
3. choose a transformation mode
4. run it
5. compare raw and final outputs
6. rate it
7. retry with a different route
8. save the winner

## 8.2 No target understanding and route selection

The application does not yet reliably classify:

- realistic photograph
- anime
- game render
- painting
- close-up
- half-body
- full-body
- profile
- occluded face
- multiple people
- small face

It must choose a route based on the target, not send every target through one hardcoded workflow.

## 8.3 No distinction between face swap and character re-identity

The present result can look like only part of the user’s face was placed on the character.

The app needs separate modes and separate masks for:

- inner face
- full face
- head
- hairline
- ears
- neck
- visible skin
- optional body adaptation

## 8.4 No approved winning recipe registry

There are many workflows and experiments, but no formal registry containing:

- recipe ID
- purpose
- target classes
- identity method
- dependency versions
- license lane
- VRAM requirement
- runtime
- quality score
- promotion status
- rollback version

## 8.5 No reliable hardware-state controller

The app must:

- detect LM Studio VRAM use
- unload the model before GPU-heavy image work
- confirm free VRAM
- run ComfyUI
- enforce batch and resolution constraints
- capture peak VRAM and RAM
- restore the operator model when appropriate
- report failure cleanly

## 8.6 No real automatic quality gate

Current score proxies are not strong enough.

Automatic approval must require:

- real identity similarity when measurable
- target preservation
- pose/expression preservation
- face/head geometry check
- mask leakage check
- seam quality
- artifact detection
- final-stage identity retention

When evidence is incomplete, use:

`needs_human_review`

Do not mark it accepted simply because the workflow completed.

## 8.7 No learning-driven workflow selection

The system currently does not use prior results to answer:

- Which route works best for anime profiles?
- Which reference photo works best for Gojo?
- Which denoise setting preserves the user’s eyes?
- Which upscaler changes identity?
- Which mask expansion works for Vegeta-style hairlines?
- Which checkpoint performs best for gaming targets?

## 8.8 No safe experimental ComfyUI environment

Production ComfyUI must not be broken by installing every missing custom node.

Required:

- stable production environment
- isolated Workflow Lab
- pinned dependencies
- intake audit
- candidate testing
- promotion process
- rollback

## 8.9 No permanent local coding lane

Codex usage can run out.

Required:

- OpenCode
- LM Studio
- local coding model
- safe repository tools
- feature branches
- automated tests
- local reviewer model
- optional Fable escalation for difficult work

## 8.10 Public repository privacy risk

Audit committed images for:

- the user’s face
- friends
- girlfriend
- private screenshots
- EXIF metadata
- copyrighted target art
- files that should not be public

---

# 9. Pain Points to Solve

## 9.1 Eight-gigabyte VRAM limit

The next solution must be verified on the RTX 3070, not merely described as “8GB compatible.”

Record:

- cold-start time
- first-run time
- second-run time
- peak VRAM
- peak RAM
- disk activity
- output resolution
- model unload behavior
- whether ComfyUI must restart
- whether identity survives upscale

## 9.2 Identity resemblance

Weak scenarios:

- 45-degree faces
- profiles
- glasses
- hands across the face
- small faces
- anime faces
- gaming renders
- extreme expressions
- different skin lighting
- hairline mismatch
- jaw mismatch
- neck transition
- creative upscaler changing the user

## 9.3 Mask quality

Required regions:

- inner face
- jaw
- forehead
- hairline
- ears
- neck
- visible skin
- glasses
- hat
- occluding hands
- multi-person selection
- full-body small-face targeting

The app must support:

- automatic mask
- mask overlay
- confidence
- manual correction
- mask versioning
- retry with adjusted mask

## 9.4 Refinement erasing identity

Save and score every stage:

- target
- selected reference
- initial mask
- raw identity transfer
- inpaint result
- face restoration
- NAG or guidance refinement
- upscale
- final

## 9.5 Hardcoded workflow parameters

Current routes contain hardcoded values that should be selected through recipe configuration:

- checkpoint
- restore model
- denoise
- guide size
- maximum face size
- sampling settings
- upscale strength
- mask expansion
- style route

## 9.6 Licensing

Programmatically enforce:

- `private`
- `funded_internal`
- `public_commercial`

Record:

- identity engine
- model license
- checkpoint license
- upscaler license
- custom-node license
- output lane

## 9.7 Real testing

CI dry-run success is not evidence of real output quality.

Use real target images and real reference images.

---

# 10. Required Decision Framework for Next Implementations

Do not choose a workflow because the preview is attractive.

Score each candidate in these categories:

| Category | Weight |
|---|---:|
| Identity resemblance | 25 |
| Target style preservation | 15 |
| Pose/expression preservation | 10 |
| Whole-head/character integration | 15 |
| Mask quality | 10 |
| 8GB stability | 10 |
| Runtime | 5 |
| Dependency safety | 5 |
| License suitability | 3 |
| API/app integration | 2 |

A candidate cannot be promoted if it scores well visually but:

- breaks the stable environment
- lacks rollback
- hides non-commercial dependencies
- cannot save intermediates
- only works manually
- cannot run twice
- cannot be called through the app
- changes the target scene unnecessarily

---

# 11. Recommended Architecture Direction

Fable must validate this architecture and adjust it based on real tests.

```text
ByrdHouse App
│
├── Target Intake
│   ├── target classification
│   ├── face/person detection
│   ├── pose and occlusion estimate
│   └── target preservation plan
│
├── Identity Intake
│   ├── identity package
│   ├── reference ranking
│   ├── embeddings
│   ├── LoRA availability
│   └── consent/license lane
│
├── Recipe Router
│   ├── fast face swap
│   ├── head identity transfer
│   ├── full character re-identity
│   ├── realistic-to-gaming
│   ├── anime identity
│   ├── manual rescue
│   └── final refine/upscale
│
├── ComfyUI Production Executor
│   └── approved workflows only
│
├── ComfyUI Workflow Lab
│   └── experimental graph editing and repair
│
├── Evaluator
│   ├── identity
│   ├── target preservation
│   ├── artifacts
│   ├── mask/seam
│   └── final-stage regression
│
├── Human Review
│   ├── approve
│   ├── reject
│   ├── compare
│   └── targeted feedback
│
└── Learning Memory
    ├── successful recipe
    ├── failed recipe
    ├── reference ranking
    ├── parameter outcome
    ├── user rating
    └── next-run recommendation
```

---

# 12. Learning Loop

The user wants ByrdHouse to improve as more images are generated.

Do not implement unsafe automatic self-training from every output.

Use staged learning.

## Stage 1 — Complete generation telemetry

For every run save:

- job ID
- user goal
- target file/hash
- target class
- identity ID
- reference files/hashes
- selected reference
- workflow/recipe ID
- workflow hash
- model and checkpoint
- seed
- prompt
- negative prompt
- all major parameters
- masks
- raw output
- refined output
- upscaled output
- runtime
- peak VRAM
- peak RAM
- automatic scores
- user rating
- user-selected winner
- rejection reason
- retry route
- whether the asset was used

## Stage 2 — Retrieval-based recommendations

Before a new run, retrieve similar past jobs.

Example:

```text
Target: anime profile, white hair, small face
Identity: Carey
Past winner:
    route = character_consistency_v2
    reference = ref_07
    mask expansion = 14
    refine strength = 0.18
    upscaler = conservative
```

Use the prior winner as the first recommendation.

## Stage 3 — Parameter and reference ranking

Learn:

- best reference by target angle
- best route by target class
- best mask setting
- best checkpoint
- best refinement strength
- upscalers that preserve identity
- common failure reasons

Start with transparent rules and weighted statistics.

## Stage 4 — Preference ranker

After enough rated examples, train or fit a small local ranking model that predicts:

- likely best workflow
- likely best reference
- likely best parameter preset
- whether human review will be needed

## Stage 5 — Curated LoRA updates

Only approved high-quality images enter a training dataset.

Never automatically train on:

- rejected images
- weak identity results
- outputs with artifacts
- unapproved friends/family
- unverified synthetic faces
- images without provenance

Version every identity LoRA and retain rollback.

---

# 13. Core Benchmark Targets

The user specifically wants Vegeta, Gojo, and similar targets to work.

Create a permanent test set.

## Required target categories

1. Vegeta-style anime close-up
2. Vegeta-style half-body or full-body action pose
3. Gojo-style anime close-up
4. Gojo-style profile or blindfold/glasses target
5. Realistic gaming character
6. Stylized game render
7. Realistic portrait
8. 45-degree portrait
9. Profile portrait
10. Occluded face
11. Small face in a full-body scene
12. Group image
13. Different skin lighting
14. Extreme expression
15. Costume reference edit

Use only files the user is authorized to use. Keep private identity references outside the public repository.

## Success definition for Vegeta and Gojo

The output must:

- look like the user
- retain the target character’s pose
- retain anime style
- retain expression
- retain outfit and recognizable theme
- integrate jaw, ears, neck, and hairline
- avoid a pasted inner-face look
- preserve the original scene
- survive refinement and upscale
- be visually usable without a manual Photoshop repair

---

# 14. Face Swap and Identity Tournament

## Candidate lanes

- `A` — Current direct ReActor
- `S` — ByrdCast Swap V0
- `K` — Existing Flux2 Klein style workflow
- `U` — Flux2 Klein Ultimate 6-in-1
- `F1` — Civitai Face Swap Workflow
- `F2` — Face Swap That Really Works
- `DU` — Faceswap, Deepfake and Upscale
- `CC` — Character Consistency / all-model workflow
- `LORA` — Identity LoRA route
- `HYBRID` — identity conditioning + mask/inpaint + conservative refine

## Required saved outputs

```text
00-target.png
01-selected-reference.png
02-face-mask.png
03-head-mask.png
04-skin-neck-mask.png
05-raw-identity.png
06-inpaint.png
07-refined.png
08-upscaled.png
09-final.png
run-metadata.json
scores.json
review.json
```

## Required measurements

- identity similarity at raw stage
- identity similarity after refine
- identity similarity after upscale
- target structural similarity
- expression preservation
- pose preservation
- scene preservation
- hairline/jaw/neck quality
- artifact count
- runtime
- peak VRAM
- peak RAM
- second-run success
- user rating

## Promotion outcome

Do not pick only one universal workflow unless testing proves it is universal.

Likely production result:

```text
Fast route
Quality realistic route
Anime route
Gaming route
Full character route
Manual rescue route
Final conservative upscale route
```

---

# 15. External Workflow and Tool Links

Download workflow JSON and documentation first. Do not automatically install all dependencies.

## 15.1 ComfyUI MCP and workflow control

### Artokun ComfyUI MCP

- https://github.com/artokun/comfyui-mcp

Potential role:

- isolated Workflow Lab
- inspect workflows
- summarize graphs
- create and repair candidate graphs
- compare workflows
- debug nodes
- optimize for 8GB
- compact tool mode for smaller local models

Initially deny:

- custom-node installation
- model download
- self-update
- panel auto-install
- public tunnel
- workflow deletion
- production writes

### Joe Norton ComfyUI MCP Server

- https://github.com/joenorton/comfyui-mcp-server

Potential role:

- approved production recipe executor
- expose curated API workflows
- constrained parameters
- job execution
- polling
- cancel
- regeneration
- metadata

Gate or remove:

- publishing
- output-root changes
- persistent defaults
- writes outside approved runtime folders

### Comfy Pilot OpenCode fork

- https://github.com/jaijia/comfy-pilot-opencode

Status:

- reference/research
- verify completeness before use

### Original Comfy Pilot

- https://github.com/ConstantineB6/comfy-pilot

Potential role:

- graph-editing reference
- Windows REST compatibility reference

---

## 15.2 Local coding and model serving

### OpenCode LM Studio bridge

- https://github.com/agustif/opencode-lmstudio

Potential role:

- LM Studio model discovery
- OpenCode local provider
- tool and vision capability information
- permanent local coding lane

### AirLLM

- https://github.com/lyogavin/airllm

Potential role:

- isolated oversized-model experiment
- one-shot review
- not the primary interactive coder due to likely disk-I/O latency

---

## 15.3 Civitai candidate workflows

### Flux2 Klein 9B Ultimate 6-in-1

- https://civitai.com/models/2543188/flux2-klein-9b-ultimate-6-in-1-workflow-face-swap-inpaint-auto-mask-nag-refine-upscale-8gb-vram

Claimed:

- face swap
- inpaint
- automatic mask
- NAG refine
- upscale
- 8GB VRAM

Highest-priority workflow candidate.

### Face Swap Workflow

- https://civitai.com/models/1089008/face-swap-workflow

Potential role:

- simple baseline

### Face Swap That Really Works

- https://civitai.com/models/1611780/face-swap-that-really-works

Potential role:

- quality comparator

### Faceswap, Deepfake and Upscale

- https://civitai.com/models/433300/faceswap-deepfake-and-upscale

Potential role:

- raw swap vs restoration vs upscale evaluation

### Face Swap Character Consistency — Works With All Models

- https://civitai.com/models/744389/comfyui-face-swap-character-consistency-works-with-all-models

Potential role:

- identity consistency across target styles and model families

---

# 16. Required Workflow Intake

Create an isolated intake area.

```text
E:\ByrdHouse\workflows\incoming\
├── flux2-klein-ultimate-6in1\
├── civitai-face-swap-workflow\
├── face-swap-really-works\
├── faceswap-deepfake-upscale\
├── character-consistency\
├── artokun-comfyui-mcp\
└── joenorton-approved-executor\
```

Each candidate must record:

- source URL
- creator
- version
- download date
- original filename
- SHA256
- license
- screenshots
- instructions
- workflow type
- required models
- required custom nodes
- exact node versions
- Python dependencies
- Torch/CUDA impact
- expected VRAM
- expected RAM
- API export status
- intermediate-output support
- private/commercial status
- test result
- promotion status

Never alter the original intake file.

Create copies under:

```text
workflows/experiments/
```

Promote approved versions under:

```text
workflows/approved/
```

---

# 17. Stable Production vs Workflow Lab

## Production ComfyUI

Purpose:

- approved workflows only
- known dependencies
- pinned versions
- stable API
- user jobs
- no automatic installs
- no experiments

## Workflow Lab

Purpose:

- inspect external workflows
- install candidate dependencies
- edit graphs
- test new nodes
- compare versions
- fail safely
- disposable environment

No candidate enters production until:

1. dependency audit passes
2. license audit passes
3. JSON validation passes
4. real 8GB test passes
5. cold and second run pass
6. target benchmark passes
7. user approves outputs
8. rollback is documented

---

# 18. Local Coding Lane

The user is currently limited by Codex usage.

Build ByrdCoder Local V0.

```text
OpenCode
    ↓
LM Studio local provider
    ↓
Qwen / Qwopus coding model
    ↓
Safe ByrdHouse repository tools
    ↓
Feature branch
    ↓
Tests
    ↓
Second local reviewer
    ↓
User approval
```

## Required modes

- `byrd-ask`
- `byrd-patch`
- `byrd-build`
- `byrd-test`
- `byrd-review`
- `byrd-private`
- `byrd-offline`

## Safety

The local coder must not:

- write directly to main
- push or merge without approval
- access secrets
- read private identity images unnecessarily
- execute arbitrary PowerShell
- modify production ComfyUI
- download unknown models
- delete outside a disposable workspace

---

# 19. Update and Evening Operator Flow

The user wants to be able to update a PC and immediately test the latest build.

Create a reliable update command for each machine.

## BYRD-MINI update goal

One command should:

1. back up current config and state
2. pull approved repository changes
3. validate config
4. run database/memory migration if needed
5. restart router/worker/dashboard
6. run health checks
7. report green/yellow/red
8. provide rollback command

## BYRD-GAMING update goal

One command should:

1. back up current config and approved workflows
2. pull approved repository changes
3. validate Python and PowerShell
4. validate ComfyUI workflow dependencies
5. confirm LM Studio and ComfyUI paths
6. run preflight
7. restart approved services
8. run one harmless smoke test
9. report green/yellow/red
10. provide rollback command

## Desired user experience

```text
Update BYRD-MINI
Update BYRD-GAMING
Open ByrdHouse on iPad or PC
Choose Vegeta or Gojo target
Choose Carey identity
Choose Full Character Re-Identity
Generate
Review stages
Rate result
Retry if needed
Save winner
```

No hidden manual patching should be required.

---

# 20. Recommended Implementation Order

Fable must validate this order against the live repository.

## P0 — Protect and verify

- audit public images
- back up both machines
- run preflight on both machines
- verify actual hardware and paths
- verify current ByrdCast cold run
- verify current Flux2 Klein workflow
- establish rollback

## P1 — Build workflow intake and tournament harness

- candidate manifest
- dependency audit
- isolated Workflow Lab
- standard output stages
- benchmark runner
- score/report schema

## P2 — Fix ByrdCast fundamentals

- require measured identity for auto-accept
- fix seam scoring
- real landmark alignment
- better artifact checks
- wire configuration into workflow
- enforce VRAM state
- style-aware checkpoint routing
- license lane enforcement

## P3 — Implement target classifier and identity modes

- target type
- face size
- angle
- occlusion
- number of people
- face-only vs head vs full-character mask plan
- route recommendation

## P4 — Integrate winning external workflow components

Do not import entire workflows blindly.

Extract only proven components:

- best auto-mask method
- best identity method
- best inpaint method
- best refinement method
- best conservative upscaler
- best 8GB offload method

Create ByrdHouse-owned recipe versions.

## P5 — Build the application flow

- select target
- select identity
- select mode
- generate
- progress stages
- compare
- approve/reject
- retry
- save winner
- view history

## P6 — Learning loop

- telemetry
- ratings
- similar-job retrieval
- reference ranking
- recipe ranking
- parameter recommendation
- curated LoRA dataset
- versioned LoRA training

## P7 — Local coding independence

- OpenCode
- LM Studio bridge
- safe tools
- model benchmark
- local reviewer
- app integration

---

# 21. Acceptance Checkpoint

This phase is not complete because code exists in the repository.

It is complete when the user can perform this real test:

1. Update BYRD-MINI with one approved command.
2. Update BYRD-GAMING with one approved command.
3. Open ByrdHouse.
4. Select a saved Vegeta or Gojo target.
5. Select the user’s identity package.
6. Choose `Full Character Re-Identity`.
7. Start the job.
8. ByrdHouse frees required VRAM automatically.
9. ByrdHouse selects and ranks references.
10. ByrdHouse creates and saves masks.
11. ByrdHouse executes the selected route.
12. ByrdHouse saves raw, refined, and upscaled stages.
13. ByrdHouse reports identity and target-preservation evidence.
14. The final result looks like the user naturally rendered as the target character.
15. The result does not look like a small pasted face.
16. A second run works without repairing ComfyUI.
17. The user can approve, reject, or retry.
18. The run is stored in learning memory.
19. The next similar run uses prior results to make a better recommendation.
20. Exact rollback is available.

---

# 22. Required Deliverables From Fable

Return:

## A. App gap report

For every required capability:

- exists
- partially exists
- missing
- broken
- unverified

Include exact file references.

## B. Implementation decision report

For every candidate workflow/tool:

- adopt
- extract components
- benchmark only
- defer
- reject

Explain why.

## C. Architecture changes

Show:

- current architecture
- proposed architecture
- minimal changes
- migration path
- rollback

## D. Real test results

Include:

- machine
- command
- target
- identity
- route
- runtime
- peak VRAM
- peak RAM
- output paths
- screenshots
- scores
- failures
- second-run result

## E. Files changed

List every file created, modified, or removed.

## F. Safety and license review

Include:

- private/public routes
- identity data handling
- external node risk
- model licenses
- repository privacy findings

## G. Final project status

Use this exact format:

```text
Current phase:
What was verified:
What was built:
What remains missing:
Next action:
Checkpoint:
Rollback:
```

---

# 23. Final Instruction to Fable

The goal is not “make face swap work.”

The goal is:

> Build a local identity and visual transformation system that understands the target, understands the user’s identity, selects the correct recipe, replaces the character naturally at the correct scope, preserves the desired scene and style, repairs weak stages, learns from every rated result, and becomes easier and more reliable with continued use.

Vegeta and Gojo are not side examples. They are benchmark targets for the central problem:

> Can ByrdHouse transform an existing character or scene into the user in a believable, complete, style-consistent way rather than pasting a partial face?

Make the next implementation decisions around that question.
