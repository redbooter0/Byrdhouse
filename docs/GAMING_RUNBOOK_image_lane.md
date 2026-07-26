# GAMING Runbook — get the image lane producing again

**Run this on BYRD-GAMING (`E:\ByrdHouse`), by hand, in order.** It uses only
what's already in the repo. Nothing here restructures the tree or deletes a file
— pruning stays your decision. Windows PowerShell 5.1. Every command reads hosts
from `byrdhouse.config.json`, never hardcoded.

Why this order: you can't tell whether *any* change helped until a **baseline**
exists and the belt can **measure identity**. Both of those landed in the belt
(`verify_identity.py` in the judge, `byrdinventory.py`). This runbook turns them
on and runs the baseline. Then — and only then — the SDXL hero-lane switch.

> **The one rule this whole thing rests on** (your v3 blueprint): *you cannot
> buy/install a higher layer to escape a problem in a lower one.* Flux2 Klein is
> a higher layer. The identity + masking + LoRA problem is the lower one. We fix
> the lower one, measured.

---

## Phase S — Stage the new lanes WITHOUT routing them in (the validation loop)

The new lanes (identity t2i/img2img, People, video) live on PR #28 — not in
production. Prove them on real hardware first, in an isolated staging copy:

```powershell
$env:BYRDHOUSE_ROOT = "E:\ByrdHouse"
powershell -ExecutionPolicy Bypass -File E:\ByrdHouse\scripts\stage-byrdhouse.ps1
```

(One-time: pull this branch into production first so the script exists, or run it
from any checkout of the branch.) It clones the branch to `E:\ByrdHouse-staging`
with its own config/db/artifacts, points at your LIVE ComfyUI + LM Studio, and
serves a second dashboard at **http://localhost:8788**. Production is untouched.
Stop the production worker while testing — one 3070, one worker.

Prove it from the web app, in order: 1) Create → `identity_sdxl_t2i` →
likeness image in Library · 2) approve it · 3) **animate** on the approved card
→ a playable clip. When it works how you want: merge the PR, `git pull` the
production root, restart. Delete the staging folder any time.

## Phase 0 — Preflight (2 min)

```powershell
# a shell that knows the root
$env:BYRDHOUSE_ROOT = "E:\ByrdHouse"
cd $env:BYRDHOUSE_ROOT

# belt + services health (green/yellow/red). Ignore the documented yellows.
powershell -ExecutionPolicy Bypass -File scripts\byrd-status.ps1

# what the Face Lab has vs is missing, told exactly (node packs, models, schema)
powershell -ExecutionPolicy Bypass -File scripts\facelab.ps1 preflight
```

If ComfyUI / LM Studio / the router aren't up: `scripts\start-byrdhouse.ps1`.

---

## Phase 1 — Make ByrdHouse remember what it has (2 min)

```powershell
# writes docs\ASSET_INVENTORY.md + artifacts\inventory.json for THIS machine
python scripts\byrdinventory.py

# read it — especially the FLAGS section at the bottom
notepad docs\ASSET_INVENTORY.md
```

You can also refresh it from the belt (so the router remembers it as an artifact)
by queueing an `inventory.scan` job from the dashboard, or:

```powershell
$cfg    = Get-Content "$env:BYRDHOUSE_ROOT\byrdhouse.config.json" -Raw | ConvertFrom-Json
$router = $cfg.services.router
$token  = $cfg.auth.admin_token
Invoke-RestMethod -Method Post -Uri "$router/jobs" -Headers @{ Authorization = "Bearer $token" } `
  -ContentType 'application/json' `
  -Body (@{ type = 'inventory.scan'; project = 'byrdhouse'; required_mode = 'ANY'; payload = @{} } | ConvertTo-Json)
```

**Expected flags** (already confirmed from the repo): the four
`workflows\flux2_klein\*.json` are **UI-format exports** — they cannot POST to
ComfyUI's `/prompt` endpoint and never ran. That, plus fp8-on-Ampere, is the
"can't produce images" cause. Leave them for now; Phase 5 covers what to do.

---

## Phase 2 — Turn the identity gate ON (measurement)

The judge already records `identity_score` for identity outputs, but only if a
face/embedding backend is installed; otherwise it honestly records *unmeasured*.
The **same `insightface` dependency powers both** the identity measurement AND
the IP-Adapter FaceID hero lane — so this one install unlocks both.

> **Governance (handoff §12 + `docs/model-license-manifest.md`):** install into an
> **isolated Identity Lab venv**, not blindly into production. Add a row to
> `docs/model-license-manifest.md` first (model, license, size, hash, rollback).
> `insightface` recognition models (buffalo_l/antelopev2) are **non-commercial** —
> fine for local **measurement / personal** use; for **monetized** output the
> license-clean identity path is your **Carey LoRA** (+ optional IP-Adapter PLUS
> FACE, h94 Apache-2.0, CLIP-based — not insightface). Keep those lanes separate.

```powershell
# isolated lab venv — does NOT touch the ComfyUI/production python
python -m venv E:\ByrdHouse\labs\identity\.venv
E:\ByrdHouse\labs\identity\.venv\Scripts\Activate.ps1
pip install insightface onnxruntime opencv-python numpy      # ArcFace backend
# optional, license-clean, crosses the anime domain gap:
pip install open_clip_torch torch                            # CLIP backend
```

Prove it with no belt involvement — the gate's math, then a real score:

```powershell
# cosine self-test (no models needed) — must print selftest: pass
python E:\ByrdHouse\scripts\verify_identity.py --selftest

# score any output you already have against your reference library
python E:\ByrdHouse\scripts\verify_identity.py `
  --output  "E:\ByrdHouse\artifacts\<some_output>.png" `
  --reference "E:\ByrdHouse\profiles\me\references" `
  --source-target "E:\ByrdHouse\Images\Targets\<the_original_target>.png"
```

Read the result: `identity_score` (cosine to your refs), and `method_guess` —
**`recolor_only`** is the exact failure you keep hitting (output ≈ the target,
no identity). `deactivate` when done.

**Live auto-measurement (optional):** the belt measures automatically only if the
**worker's** python can import `insightface`/`open_clip`. If your worker runs
under the ComfyUI venv (where FaceID's insightface will also live), it just works.
If you keep the worker python clean, measure WO-0 by hand as above — or ask me to
wire `byrdjudge` to shell out to the lab venv (a small code change; not done here
because you chose runbook-only).

---

## Phase 3 — WO-0: the baseline (the step that ends this phase)

Assemble the five locked targets and run your **current** SDXL + Carey LoRA path
on them with **fixed seeds**, then archive it. This is the ruler everything else
is measured against.

**3a. Stage the 5 targets** (naming per `docs/identity-benchmark.md`):

```powershell
$bt = "E:\ByrdHouse\inbox\benchmark_targets"
New-Item -ItemType Directory -Force -Path $bt | Out-Null
# copy your five into $bt as:
#   01_front*.png  02_angle45*.png  03_profile*.png  04_occlusion*.png  05_smallface*.png
# use the locked evaluation targets (Luffy / Vegeta / Gojo / a realistic portrait /
# a game character). NEVER train on these — they are evaluation only.
```

**3b. Generate the hero-lane candidate per target, fixed seed.** GUI-first: in the
dashboard **Create** panel pick recipe **`me_as_character`**, set **Character**
(e.g. Gojo Satoru), add your identity LoRA in the **LoRA** field
(e.g. `carey_face_v2`), and set the **Seed** field to a fixed number you reuse for
every target (e.g. `42`). Or scripted, one fixed seed:

```powershell
$cfg    = Get-Content "$env:BYRDHOUSE_ROOT\byrdhouse.config.json" -Raw | ConvertFrom-Json
$router = $cfg.services.router; $token = $cfg.auth.admin_token
$body = @{
  type = 'image.generate'; project = 'careyrpg'
  required_mode = 'IMAGE'; required_caps = @('comfyui')
  payload = @{
    recipe = 'me_as_character'; project = 'careyrpg'
    purpose = 'WO-0 baseline (fixed seed 42)'
    slots = @{ character = 'Gojo Satoru' }
    lora = 'carey_face_v2'      # your trained identity LoRA
    seed = 42                   # SAME seed for every target = comparable baseline
  }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri "$router/jobs" -Headers @{ Authorization = "Bearer $token" } `
  -ContentType 'application/json' -Body $body
```

Repeat for each of the five (change `character`, keep `seed = 42`). The worker
runs IMAGE mode, generates, and **auto-judges** — the card now carries the
identity score if Phase 2's backend is live.

**3c. Read the baseline.** In the dashboard Library each card shows score + tags
(watch for the `recolor-only` tag). Per card on disk the sidecar `*.png.json` has
`identity` (`identity_score`, `identity_method_guess`, `identity_backend`). Paste
the five scores into `docs/identity-benchmark.md`. If the backend was not live,
score the five outputs by hand with the Phase-2 command.

> This is also exactly what `scripts\identity-benchmark.ps1 -TargetsDir <folder>`
> automates for the **swap** lanes (Branch A submits belt jobs the belt judges).
> Use it if you want the repeatable scorecard; `-Repeat 2+` before trusting.

---

## Phase 4 — Read the numbers, then decide

- **`recolor_only` / very low `identity_score`** → the LoRA/IP-Adapter isn't
  carrying identity; the win is in the identity stack (LoRA blocks, FaceID weight,
  mask), not a bigger model. This is the whole point of measuring first.
- **Decent identity but style pasted-on** → face-detailer / low-denoise harmonize
  pass, not a model swap.
- Only change **one** variable at a time and re-run the same five seeds. The gate
  tells you if it helped.

---

## Phase 5 — The SDXL hero lane (fits ~7GB) + Flux2 disposition

The hero lane is already in the repo — no new model needed:

- recipe **`me_as_character`** → workflow **`workflows\sdxl_ipadapter_face_api.json`**
  (SDXL checkpoint + IP-Adapter FaceID + your Carey LoRA + KSampler). Needs
  `ComfyUI_IPAdapter_plus` nodes + the FaceID SDXL models (`h94/IP-Adapter-FaceID`)
  — `facelab.ps1 preflight` and the inventory tell you if they're present.
- Add a **face-detailer** pass (Impact Pack, already used by the auto route) to
  fuse the face into the art style. ~7GB total on the 3070 with headroom.

**Free VRAM/perf that is NOT a GPU purchase** (from your PDF):
- Run the **display off the i9 iGPU** (UHD 630) — plug the monitor into the
  motherboard, let the 3070 go headless. Frees ~0.6–1.2GB permanently.
- **Text-encoder on CPU** (you have 32GB + an i9) frees several GB for the UNet.
- Push segmentation / face parsing / dedup to **BYRD-MINI** so the 3070 only
  diffuses.
- If you ever need a bigger model: **GGUF, not fp8** (fp8 has no Ampere speedup).
- **Rent a GPU by the hour for training only** (~$2 a LoRA); inference stays local.

**Flux2 Klein** — leave it as a clearly-labeled, **not-wired** cash-gated lane for
the day a bigger card is bought *in cash, after ByrdHouse has earned it*. The four
`workflows\flux2_klein\*.json` are UI exports that can't run; if you want them out
of the way, that's a one-line prune — say the word and I'll delete them on the
branch (git-reversible). I won't delete on my own.

---

## What "done with this phase" looks like

1. `docs\ASSET_INVENTORY.md` current, flags reviewed.
2. Identity backend proven (`verify_identity.py --selftest` passes; a real score printed).
3. Five WO-0 baseline cards archived, each with an `identity_score`, pasted into
   `docs\identity-benchmark.md`.
4. One measured hero-lane change made and re-scored against the same five seeds.

Then the coin-flip feeling is gone: every change is now a number that went up or down.
