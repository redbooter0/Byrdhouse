# ByrdHouse Repo Comparison — External Reference Study

*Prepared 2026-07-19 per ByrdHouse_Fable_Repo_Handoff.docx*

**Core directive (never forget):** Study repos in a sandbox, extract the best
architectural ideas, then implement small safe improvements that directly help
the image/identity pipeline. Do NOT turn ByrdHouse into a pile of cloned apps.

---

## Quick verdicts

| Repo | Score | Verdict | ByrdHouse action |
|---|---|---|---|
| ZPix | 9/10 | **Adopt patterns** | Create Room spec (below) |
| gimp-mcp | 8/10 | **Adopt patterns** | Media Finisher spec (below) |
| Locally Uncensored | 8.5/10 | **Cockpit reference only** | Study app shell, no install |
| AionUi | 8/10 | **Cockpit reference only** | Study agent lanes, no install |
| BlenderProc | 7.5/10 | **Future** | SceneForge; park until stills pass |
| CogVideo | 7/10 | **Future** | Video lane; park until stills pass |
| LocalForge | 7/10 | **Optional study** | Lower priority than AionUi |
| AgenticSeek | 6.5/10 | **Optional future** | Too heavy right now |

---

## Sandbox install (BYRD-GAMING only, never into E:\ByrdHouse)

```powershell
New-Item -ItemType Directory -Force E:\AI_LABS\repo_tests | Out-Null
cd E:\AI_LABS\repo_tests
git clone https://github.com/SamuelTallet/ZPix
git clone https://github.com/maorcc/gimp-mcp
git clone https://github.com/PurpleDoubleD/locally-uncensored
git clone https://github.com/iOfficeAI/AionUi
git clone https://github.com/DLR-RM/BlenderProc
git clone https://github.com/zai-org/CogVideo
git clone https://github.com/rockbite/localforge
git clone https://github.com/Fosowl/agenticSeek
```

---

## What each repo actually does

### ZPix (adopt patterns — immediate)
Local desktop image generation app (Python Gradio + C++ WebView2). No cloud,
no ComfyUI — uses Diffusers/PEFT directly. Key patterns to extract:

- **Prompt + reference image drop** side by side — drag-and-drop from gallery or filesystem
- **LoRA load on the fly** with strength slider; trigger words auto-insert from safetensors metadata
- **Seed field** with "random" toggle — same pattern we need on the Create tab
- **Gallery with prompt extraction** — tap any past image to get its settings back
- **14 aspect ratio presets** — one-click ratio picker

What ZPix does NOT have: ComfyUI, face detection, identity profiles, metadata
sidecar cards. We don't adopt those gaps — our belt is stronger for production.

**What to extract:** the Create tab UX flow described in the spec below.

### gimp-mcp (adopt patterns — near term)
GIMP as an MCP server: 56 tools covering brightness/curves/hue, scale/rotate/
crop, layers, text, filters, and `get_state_snapshot` for live visual state.
Key patterns:

- **`get_state_snapshot`** — agent sees live image without disk save, iterates
- **Pixel inspection tools** — zoom to face region, read histogram, get selection bounds
- **Export/close cycle** — agent opens file, edits, exports acceptance preview, closes

Useful as a post-generation **finishing booth**: open the composite, agent
zooms to face, reports framing/color/seam issues, exports a review crop.
Does NOT replace ComfyUI for generation.

### Locally Uncensored (cockpit reference — no install)
Full local AI studio: ComfyUI integration, model manager, MCP wiring, local
backend detection. Interesting patterns:

- Clean model-manager UI: checkboxes per model, install/uninstall per-toggle
- ComfyUI workflow selector with parameter override sliders
- Feature flags per workflow — exactly what we need for the avenue system

Study only. Do not clone into ByrdHouse.

### AionUi (cockpit reference — no install)
Multi-agent workspace with shared task rooms, approvals, agent lanes, and task
status. Relevant for when Fable + Codex + OpenCode need to co-exist visibly.
Study the approval flow and per-agent room model.

### BlenderProc (future — park)
Procedural synthetic scene generation: RGB, depth, normals, segmentation, object
masks, camera poses. The future SceneForge lane: feed controlled scene geometry
into ComfyUI/ControlNet for structured image generation. Park until face/identity
passes.

### CogVideo (future — park)
Image-to-video. Start with approved stills → image-to-video. Do not make video
the blocker. Park.

### LocalForge, AgenticSeek (optional study)
LocalForge: simple local file-editing app, lower priority than AionUi.
AgenticSeek: local autonomous browsing/planning, potentially heavy. Optional
after core ByrdHouse is stable.

---

## Proposed ByrdHouse Create Room spec

Inspired by ZPix; wraps the existing `byrdimage`/ComfyUI/recipe belt.
**Nothing new is wired behind the scenes** — this is a dashboard UX pass over
what already works.

### Required fields on every Create run
| Field | Source | Default |
|---|---|---|
| Prompt (main) | text input | recipe default |
| Target image | file drop or Library pick | none |
| Reference folder | `profiles/me/references/` | founder profile |
| LoRA | dropdown from `recipes/` LoRA manifest | none (LoRA-free lane) |
| Workflow/recipe | dropdown (versioned list from `recipes/`) | `anime_face_zone_edit.v2` |
| Seed | number field + "random" lock toggle | random |
| Aspect ratio | 4 presets: 1:1 / 3:2 / 16:9 / 4:3 | 1:1 |
| Batch count | 1–4 | 1 |
| Run button | → `image.faceswap` or `image.face_zone` job | — |

### Gallery behavior
- Every output card shows: thumbnail + seed + recipe + checkpoint + acceptance verdict
- Tap any card → **Rerun** button pre-fills all fields from that card's `reproduce` block
- "Accepted" badge (green face icon) when `output_acceptance.accepted = true`
- "Flagged" badge (yellow) when `output_acceptance.flags` is non-empty

### Metadata reuse
The `reproduce` block on every card carries the full 23-key parameter set.
"Rerun" reads it exactly — no manual hunting. This is the anti-"got away" fix.

### Implementation scope for the Create tab
The dashboard at `dashboard/index.html` already has a Create tab. The additions
needed are:
1. Seed lock toggle (currently missing)
2. "Rerun from card" button on gallery items
3. `output_acceptance.accepted` badge on every result card
4. Face crop preview (`output_acceptance.face_crop_preview`) shown on card expand

No backend changes needed — the belt already captures everything.

---

## Proposed Identity + Face Acceptance Layer spec

**Pain point from the handoff:** "Face detection has been wrong or incomplete.
Recent feedback: more of the face needs to be in frame."

**What's already built:** The examiner (`byrdfacezone analyze`) runs on the INPUT
target — it catches problems BEFORE generation. But nothing checked the OUTPUT
after generation until now.

**What we added (2026-07-19):** `acceptance_check()` in `byrdfacezone.py` + the
`accept` CLI subcommand + integration in `edit_face_zone()`.

### What it checks (on the final composite)
| Check | Flag | What it means |
|---|---|---|
| Face detected? | `no_face_detected` | Generation destroyed the face entirely |
| Multiple faces | `multiple_faces: N` | Wrong subject bled in |
| Left edge | `face_cropped_left` | Face extends to left border |
| Right edge | `face_cropped_right` | Face extends to right border |
| Top edge | `face_cropped_top — forehead may be cut off` | Forehead cut off |
| Bottom edge | `face_cropped_bottom — chin may be cut off` | Chin cut off |
| Face size | `face_too_small: Npx in output` | Generation shrank the face |

### What it saves
- `<output_stem>_accept_crop.jpg` — padded face crop from the output (30% padding)
- `card["output_acceptance"]` block on every sidecar card

### When to act on flags
- `face_cropped_top` → run the examiner on the target again; use a larger `canvas_size`
- `no_face_detected` → generation was a no-op or destroyed the zone; check the card
  for no-op law rejection reason
- `multiple_faces` → wrong target image or bleed from reference; re-examine the target

### Usage (standalone)
```powershell
# check any output after the fact
.venv\Scripts\python.exe scripts\byrdfacezone.py --root E:\ByrdHouse accept `
    --image "E:\ByrdHouse\artifacts\careyrpg\2026-07\20260719_..._00001_.png" `
    --output-dir "E:\ByrdHouse\artifacts\careyrpg\2026-07\"
```

---

## Proposed Media Finisher spec (gimp-mcp-inspired)

**Role:** Optional post-generation inspection booth. Not a replacement for
ComfyUI — runs AFTER the final composite exists.

**Scope for first test (narrow — sandbox only):**
1. Open a generated output in GIMP via MCP
2. Zoom to face region (use `face_crop_preview` coords from the acceptance card)
3. Agent reports: framing, seam visibility, color match, expression preserved?
4. Export an acceptance preview at 512px
5. Agent writes a one-line note to `card["finisher_notes"]` and closes GIMP

**What we do NOT do with GIMP:**
- No diffusion / no generation through GIMP
- No permanent layer edits to the canonical output
- No automatic approval — every finisher pass needs founder review

**Install path (sandbox first):**
```powershell
cd E:\AI_LABS\repo_tests\gimp-mcp
# follow the repo's README to wire it as an MCP server into ByrdCoder
# test with ONE output before touching any ByrdHouse config
```

**Gate before ByrdHouse adoption:**
- First test must produce a face zoom crop + seam report on a Gojo output
- Test must complete without GIMP crashing or leaving temp files in E:\ByrdHouse
- Review finisher_notes vs manual inspection — does the agent's report match what
  a human would flag?

---

## Minimum acceptance criteria

1. Existing ByrdHouse commands, routes, dashboard, router, worker, ComfyUI
   connector, and `byrd-status` remain unbroken (CI gate).
2. All new code is feature-gated: `acceptance_check()` never raises, its failure
   is a flagged card not a job death.
3. Every output already keeps full metadata — the `reproduce` block satisfies the
   image-stage metadata contract.
4. First milestone: one target image → output + face crop preview + acceptance
   card without manual hunting.

---

## Definition of done for this pass

ByrdHouse has:
- `byrdfacezone accept` command (post-generation output check)
- `output_acceptance` block on every `edit_face_zone` card
- `docs/REPO_COMPARISON.md` (this file) with adopt/reject/revisit verdicts
- Create Room spec, Identity Acceptance spec, Media Finisher spec documented
- CI still green; no existing belt command broken
