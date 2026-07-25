# Image + Video State — the single current-truth page

**Last updated:** 2026-07-25 · **Rule:** update this after every real GAMING run.
Supersedes scattered status prose. Companion runbook: `docs/GAMING_RUNBOOK_image_lane.md`.

| | Status |
|---|---|
| **Likeness route (promoted)** | `identity_sdxl_t2i@1` — **code complete, UNPROVEN on hardware** |
| **Identity acceptance gate** | **live** — recolours are auto-rejected |
| **Video route** | `video.i2v` (LTX) — **code complete, UNPROVEN on hardware** |
| **Blocking next step** | WO-0 baseline + a promoted Carey **SDXL** LoRA |

---

## 1. Why the images failed — root cause, verified in code

The 2026-07-22 outputs (Vegeta at "25% / 40% / 55% identity", the Link edit) were
not a tuning problem. **The face-zone mesh-seed lane cannot produce a likeness,
by construction.**

`scripts/byrdfacezone.py::_build_identity_mesh_seed` — *"Warp a Carey anime
reference through the same 478-point target grid."* The warp runs
`source_mesh → target_crop_mesh`. So the output's facial **geometry is always the
target's**; only Carey's colour and texture survive the warp.

Identity lives mostly in geometry — interocular distance, nose shape, jaw width,
brow ridge. Warp those onto Vegeta's grid and you have Vegeta with different
skin. That is exactly what every sample shows, and why "identity %" climbed as
the skin got darker: the metrics being optimised were *complexion pixels moved*
(98.63%) and *edge retention* (99.65%) — pixel-coverage proxies that are not
identity at all.

**Correction:** the zone lane is a *surgical editor*, not the likeness engine.
Likeness must come from a route where geometry is generated **from the identity**,
not inherited from a target.

## 2. What now prevents that failure from being called success

`scripts/byrdidentity.py` — the **acceptance gate** (handoff §4.2 "fail closed").
The belt already measured identity; it still shipped recolours, because a number
next to a bad image changes nothing. The gate acts:

| Signal | Authority | Action |
|---|---|---|
| **Recolour guard** — output >92% identical to target AND identity at the floor | authoritative, backend-independent (behavioural proof) | **REJECT** |
| `arcface` score | authoritative (a real face-embedding metric) | reject <0.28 · accept ≥0.40 · else review |
| `clip` score | **advisory only** — whole-image similarity is not identity | flag, **never** reject alone |
| no backend installed | — | **review** (never auto-approve, never auto-reject) |

Rejections carry their reason onto the card, so a rejection is evidence rather
than a dead end. Thresholds live in `byrdhouse.config.json → identity`.

## 3. The likeness route: `identity_sdxl_t2i@1`

SDXL builds the person from scratch; the Carey **SDXL** LoRA plus IP-Adapter
FaceID supply identity. Geometry comes from the identity — the structural fix.

- Graph: `workflows/sdxl_ipadapter_face_api.json` (already API-format).
- The recipe **carries its own model pack** (`identity.lora`), so the identity
  lane can never silently run unconditioned because nobody typed a filename.
- `reference_policy.source: ground_truth` — conditioning resolves
  `profiles/me/profile.json → references.ground_truth` (**real camera photos**)
  and **refuses** if there are none. Previously `default_set` led with
  `ai_identity_front_v1.png`, i.e. the likeness was being conditioned on an
  AI-generated face, compounding drift. Fixed (handoff §5.1).

> **Blocking dependency:** `carey_sdxl_identity_v1` does not exist yet. Today's
> LoRA is SD1.5 (`carey_meina_sd15_v1`) and **an SD1.5 LoRA does not work on
> SDXL** — different model family. Until the SDXL pack is trained and promoted
> (§11.1 scorecard, ≥80/100), this route runs with FaceID conditioning only, and
> the gate will honestly mark most results `review`.

## 4. The video route: `video.i2v`

**VIDEO RULE (handoff §7):** never ask the video model to rediscover Carey. The
first frame must already be an **approved** identity artifact.

- `video.i2v` **refuses** a source still that is not `approved`, with a message
  saying so. A rejected recolour can no longer become a rejected video 20 minutes
  of VIDEO mode later.
- **Why video never ran before:** `video.i2v` was a declared job type with *no
  runner*, and every graph in `Video/Workflows/` is a ComfyUI **UI export**
  (`{nodes, links}`) which cannot be POSTed to `/prompt` — the same trap as the
  `flux2_klein` graphs. `workflows/ltx_i2v_api.json` is the API conversion,
  node-for-node from the UI baseline's links and widget values.
- `VIDEO` GPU mode now exists in the worker: it wins the queue outright when a
  clip is pending and runs the same verified-VRAM unload ritual as IMAGE
  (handoff §6). Baseline 768×512 @ 97 frames; LTX needs `(length-1) % 8 == 0`.
- Video artifacts are **not** auto-judged — the image judge scores stills. Frame
  drift examination (`video.examine`, §7.3) is the next rung.

## 5. Honest status — what is proven and what is not

**Proven here (zero GPU, 196-check belt suite green):** the gate's decisions on
the real failure numbers; the identity recipe's contract; the LTX graph's node
contract and wiring; `video.i2v` refusing an unapproved still and animating an
approved one into a carded artifact.

**NOT proven — needs BYRD-GAMING:** that any of this produces a good picture. No
image in this change set was generated on a GPU. Per the handoff's own rule, a
successful test is *a visually reviewed artifact on the real RTX 3070*, not a
green unit test.

## 6. Next actions, in order

1. **WO-0 baseline** — five locked targets, fixed seeds, archived
   (`docs/GAMING_RUNBOOK_image_lane.md` Phase 3). Nothing can be proven to help
   without it.
2. **Install the arcface backend** so the gate is authoritative instead of
   advisory (runbook Phase 2). One `insightface` install also powers FaceID.
3. **Train the Carey SDXL pack** — real-photo-dominant dataset, 400/800/1200
   checkpoints, promote only on the §11.1 scorecard (≥80/100). Rentable by the
   hour (~$2) if 8GB training is painful; inference stays local.
4. **Prove the three image routes** (t2i, img2img, target edit) through one
   subject profile.
5. **Then** LTX from an approved still, add `video.examine`, and only then
   benchmark Wan 2.2 Q4.

Do not skip 1–3 to get to video faster. Video of a face that isn't Carey is a
more expensive version of the same failure.
