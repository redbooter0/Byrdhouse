# ByrdHouse Sandbox Test Plan

*Read docs/REPO_COMPARISON.md first for the adopt/reject verdict on each repo.*
*This doc is the concrete test protocol — what to clone, what to run, what gate passes before anything touches E:\ByrdHouse.*

**Rule:** External repos go into `E:\AI_LABS\repo_tests\` only. Nothing enters ByrdHouse until a sandbox test proves value and confirms no conflict with the router/worker/ComfyUI/byrd-status.

---

## 0. One-time sandbox setup (run once on BYRD-GAMING)

```powershell
New-Item -ItemType Directory -Force "E:\AI_LABS\repo_tests" | Out-Null
```

---

## 1. ZPix — local image generation UX reference (Priority 1)

**Goal:** Understand the Create Room UX patterns — seed lock, drag-from-gallery, prompt-from-metadata, LoRA on the fly. We are NOT running ZPix as a ByrdHouse component; we are reading its UI code to extract ideas for the dashboard.

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/SamuelTallet/ZPix
```

**What to look at (read, don't install):**
- `ui/` or `app/` — the generation form layout (seed field, aspect presets, LoRA selector)
- How the gallery drag-to-reuse is implemented (drag events, prompt extraction from image EXIF/metadata)
- The "14 aspect ratios" picker — is it a dropdown or chips?
- How the LoRA trigger word is auto-inserted from safetensors metadata

**Gate to pass before touching ByrdHouse:**
- [ ] Read the UI code and confirm the seed lock/unlock pattern
- [ ] Read the gallery "extract prompt from image" logic
- [ ] Write down exactly what ByrdHouse's Create Room is still missing vs ZPix

**What NOT to do:** Do not install ZPix's Python environment. Do not run it. Do not copy its model inference code. ByrdHouse uses ComfyUI + the belt — ZPix is a UX reference only.

---

## 2. gimp-mcp — post-generation inspection booth (Priority 2)

**Goal:** Test whether GIMP-MCP can open a generated output, zoom to the face region, produce a face-framing report, and export an acceptance preview — without breaking ComfyUI or the router.

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/maorcc/gimp-mcp
```

**Setup in sandbox (not in ByrdHouse):**
```powershell
cd "E:\AI_LABS\repo_tests\gimp-mcp"
# Follow the repo's README for GIMP MCP server setup
# Typical: install GIMP 2.10+, install gimp-mcp Python plugin
# DO NOT configure this in configs/byrdcoder/opencode.example.json yet
```

**Narrow first test:**
1. Open ONE generated output (a known Gojo or Vegeta composite from `E:\ByrdHouse\artifacts\`)
2. Ask the agent (via ByrdCoder / Claude) to:
   - Open the file in GIMP via MCP
   - Use `get_state_snapshot` to see the current image state
   - Zoom to the face crop coordinates from the output's `_accept_crop.jpg`
   - Report: is the face fully in frame? Are there visible seams? Color match?
   - Export a 256px acceptance preview PNG to `E:\AI_LABS\repo_tests\gimp-mcp\test_outputs\`
3. Compare the agent's report to your own manual inspection

**Gate to pass before wiring into ByrdHouse:**
- [ ] GIMP opens the file without error
- [ ] `get_state_snapshot` returns usable state
- [ ] Zoom to face box coordinates works
- [ ] Agent report matches what a human would flag (seam visible? framing OK?)
- [ ] Export works, output is a real image, temp files are NOT in E:\ByrdHouse
- [ ] ComfyUI and router remain unaffected (run `byrd-status.ps1` before and after)
- [ ] GIMP MCP does NOT write to E:\ByrdHouse\artifacts\

**If gate passes:** wire `comfyui-lab` in `configs/byrdcoder/opencode.example.json` to include gimp-mcp as a third MCP server. Update docs/REPO_COMPARISON.md with test verdict.

**If gate fails:** record the failure in docs/REPO_COMPARISON.md and park.

---

## 3. Locally Uncensored — cockpit reference (read only)

**Goal:** Read the app shell structure. Do not run it.

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/PurpleDoubleD/locally-uncensored
```

**What to read:**
- The ComfyUI integration pattern — how does it wire the workflow picker?
- The model manager UI — checkbox per model, install/uninstall per toggle
- The feature-flag gating pattern

**Nothing to run. No gate needed — just documentation.** Add findings to docs/REPO_COMPARISON.md.

---

## 4. AionUi — cockpit reference (read only)

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/iOfficeAI/AionUi
```

**What to read:**
- Multi-agent workspace layout (task rooms, approvals, per-agent lanes)
- Approval flow for agent-submitted changes

**Nothing to run.** Add findings to docs/REPO_COMPARISON.md.

---

## 5. BlenderProc (future — clone but do not run)

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/DLR-RM/BlenderProc
```

Park. Return after face/identity stage is complete and hardware tested.

---

## 6. CogVideo (future — clone but do not run)

```powershell
cd "E:\AI_LABS\repo_tests"
git clone https://github.com/zai-org/CogVideo
```

Park. Return after still-image identity passes the 5-target benchmark.

---

## 7. LocalForge, AgenticSeek (optional — do not clone yet)

Lower priority than the above. Do not clone until ZPix and gimp-mcp tests are complete.

---

## Sandbox integrity rules

Before and after EVERY sandbox test run:

```powershell
# run from E:\ByrdHouse — must stay green
powershell -ExecutionPolicy Bypass -File scripts\byrd-status.ps1
```

If any existing service is affected — router port in use, ComfyUI config changed, worker not starting — the sandbox test has failed the isolation rule. Stop, diagnose, and record in docs/REPO_COMPARISON.md.

The sandbox NEVER writes to:
- `E:\ByrdHouse\` (any subdirectory)
- `E:\ByrdHouse\Generators\ComfyUI\models\`
- `E:\ByrdHouse\db\`
- `E:\ByrdHouse\profiles\`
- `D:\ByrdHouse\` (MINI)

---

## Minimum milestone for this pass

A successful sandbox pass produces:
1. A Gojo output with `output_acceptance.accepted = true` in its card (face fully in frame)
2. An `_accept_crop.jpg` beside it (the face crop preview saved automatically)
3. A gimp-mcp acceptance preview of that same output showing face framing (if gate passed)
4. Dashboard shows green face badge on that card

That is the signal to move to the next gate — not "video works," not "ten new repos installed."
