#!/usr/bin/env python3
"""byrdswap.py — the swap CONDUCTOR: one command from image to result.

This is the "app bot" behavior the routes were always missing (DECISIONS
2026-07-15: ladder auto-fallback conductor, staged): you give it ONE image,
it examines it, PICKS the lane itself from the geometry gate + what is
actually installed/available, runs the ladder top to bottom with automatic
fallback, and ends with either an inspectable result or the exact reason and
the exact next command. No route knowledge required from the founder.

    python scripts/byrdswap.py --image "E:\\path\\to\\target.png"
    python scripts/byrdswap.py --image target.png --lora <preview-lora>
    python scripts/byrdswap.py --image target.png --plan     # decide only

Ladder (free/license-clean first — docs/FREE_SWAP_STACK.md):
  stable geometry:
    1. quality_photo_anchored — zone redraw, identity from a REAL photo via
       IP-Adapter plus-face (Apache-2.0). Needs no LoRA. Free lane default.
    2. quality_lora_mesh — the v2 mesh-seed lane, only when a LoRA was
       explicitly passed (previews stay private; nothing auto-promotes).
    3. auto_facedetailer — Impact Pack redraw, only with an explicit LoRA.
  unstable geometry (gate refuses the mesh case):
    -> reviewed_zone: the conductor STOPS and prints the reviewed-mask
       commands — a human approves the mask; the bot never guesses.

Every attempt and its failure reason lands in the run report
(logs/byrdswap/run_<stamp>.json). The plan logic is a pure function
(plan_ladder) so the suite tests the bot's decisions with zero GPU.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdimage  # noqa: E402  (same stdlib-only module the worker uses)

PHOTO_ANCHOR_WORKFLOW = "workflows/sd15_face_zone_ipadapter_api.json"


def PHOTO_ANCHORED_ENGINE(identity_photo) -> dict:
    """Engine for the free/license-clean photo-anchored lane (runtime-proven,
    2026-07-20). no_identity_mesh=True because IP-Adapter supplies the identity
    and the CLEAN target crop (not a mesh warp) should start diffusion. The
    IP-Adapter graph has ONE KSampler, so exactly ONE GPU pass is resolved:
    steps 26 / cfg 5.5 / dpmpp_2m / karras / denoise 0.55."""
    return {
        "workflow": PHOTO_ANCHOR_WORKFLOW,
        "identity_photo": str(identity_photo),
        "no_identity_mesh": True,
        "gpu_passes": {"photo_cleanup": {
            "steps": 26, "cfg": 5.5, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 0.55}},
    }

# The GOJO AVENUE (founder-verified direction, 2026-07-14 outputs
# ..._fullidentity_fill_d28_m40...): identity fill at denoise 0.28 with mesh
# strength 0.40 — NOT the recipe default 0.38 the doc's run table already
# flagged for eye distortion. Target eyes hard-protected; GPU cleanup ON so
# the repair guards (outside-mask proof, eye restore, shard check) finish it.
GOJO_AVENUE_ENGINE = {
    "mesh_identity_strength": 0.40,
    "gpu_passes": {"identity_fill": {"steps": 16, "denoise": 0.28},
                   "line_harmonize": {"steps": 8, "denoise": 0.12}},
    "skip_gpu_cleanup": False,
    "eye_source": "target",
    "eye_protection": 1.0,
}

def finish_source(image: Path) -> dict:
    """FINISH never edits a processed image (belt law: generation is ALWAYS 1,
    no generated parents — _require_original_target enforces it). Instead it
    reads the output's card, recovers the immutable ORIGINAL target and the
    captured settings (reproduce block, same seed), and re-renders from
    scratch through the repaired pipeline. Raises ValueError when the image
    has no card (then it IS an original — run it directly)."""
    card_file = Path(str(image) + ".json")
    if not card_file.is_file():
        raise ValueError(
            "no generation card next to this image. If it is an ORIGINAL "
            "target, run it directly (facelab.ps1 run -Image <it>); finish "
            "only re-renders belt outputs from their immutable original.")
    card = json.loads(card_file.read_text(encoding="utf-8-sig"))
    rep = card.get("reproduce") or {}
    original = rep.get("target") or card.get("target")
    if not original:
        raise ValueError("card records no original target — cannot re-render safely")
    recipe = str(rep.get("recipe") or card.get("recipe") or "anime_face_zone_edit@2")
    rid, _, rver = recipe.partition("@")
    return {"original": original,
            "seed": rep.get("seed", card.get("seed")),
            "lora": rep.get("lora", card.get("lora")),
            "preset": rep.get("target_preset", card.get("target_preset") or "auto"),
            "engine": dict(rep.get("engine") or {}),
            "recipe": f"{rid}.v{rver}" if rver else rid,
            "from_job": card.get("job_id")}


def find_identity_photo(root: Path, profile: str = "me"):
    """First real reference photo from the identity profile (gitignored,
    on-machine only). Returns None when the profile has no photos."""
    refs = root / "profiles" / profile / "references"
    if not refs.is_dir():
        return None
    for pattern in ("me_photo_*.jpg", "*.jpg", "*.jpeg", "*.png"):
        hits = sorted(refs.glob(pattern))
        if hits:
            return hits[0]
    return None


def _reactor_available(root: Path) -> bool:
    """The realistic lane needs the ReActor node reachable in ComfyUI. Checked
    against the live server (like byrdcast); False when ComfyUI is down or the
    node is absent, so the conductor cleanly falls back instead of guessing."""
    try:
        import byrdcast_swap as bcs
        comfy = bcs.comfy_url(root)
        return bool(comfy) and bcs.comfy_has_node(comfy, "ReActorFaceSwap")
    except Exception:
        return False


def _first_face(face_report: dict, face_index: int = 0) -> dict:
    faces = {f.get("index"): f for f in face_report.get("faces", [])}
    return faces.get(face_index) or (face_report.get("faces") or [{}])[0]


def classify_realism(face_report: dict, face_index: int = 0) -> str:
    """'realistic' | 'stylized' | 'unknown' from the examiner's own signals.

    The examiner's semantic parser falls back to the eval-only anime parser on
    stylized art; when it stays on the real-photo selfie parser the target is a
    real/photoreal face. A recorded face embedding (insightface) is a second
    realistic signal (anime faces rarely embed). Unknown when neither is present
    — the conductor then does NOT claim a realistic target and keeps the safe
    (free) lane order.
    """
    face = _first_face(face_report, face_index)
    signals = byrdimage.collect_face_signals(face)
    parser = str(signals.get("parser") or "").lower()
    if "anime" in parser or "parsenet" in parser:
        return "stylized"
    if face.get("embedding") or signals.get("has_embedding"):
        return "realistic"
    if parser and "selfie" in parser:
        return "realistic"
    return "unknown"


def is_frontal(face_report: dict, face_index: int = 0, max_yaw: float = 0.28) -> bool:
    """Front-facing when the examiner's yaw proxy is low and no strong_profile
    flag is set. Fail-safe: unknown yaw -> not frontal (conductor won't claim it)."""
    face = _first_face(face_report, face_index)
    signals = byrdimage.collect_face_signals(face)
    if "strong_profile" in " ".join(face.get("flags") or []):
        return False
    yaw = signals.get("yaw_asymmetry")
    if yaw is None:
        return False
    return float(yaw) <= max_yaw


def plan_ladder(face_report: dict, face_index: int = 0, lora: str | None = None,
                identity_photo: str | None = None,
                ipadapter_graph_exists: bool = True,
                reactor_available: bool = False,
                has_references: bool = False) -> dict:
    """Pure decision function: examiner report -> ordered lane plan.
    Never touches the network/GPU, so the bot's judgment is unit-testable.

    For a STABLE, FRONT-FACING, REALISTIC human target the preferred lane is
    realistic_reactor_refine (explicit identity transfer + facial-hair mask +
    low-denoise cleanup + verification) — a stable realistic target must NOT be
    sent straight into the anime edit lane without an identity transfer. The
    free/license-clean quality_photo_anchored stays as the fallback below it.
    """
    gate = byrdimage.geometry_gate(face_report, face_index)
    lanes, skipped = [], []
    if not gate["mesh_case_allowed"]:
        return {"gate": gate, "lanes": [], "skipped": skipped,
                "stop_reason": "geometry gate: " + "; ".join(gate["reasons"]),
                "manual_next": [
                    "facelab.ps1 examine -Image <target>   (see the gate yourself)",
                    "dashboard -> Face Swap -> Preview     (archives overlay + soft mask)",
                    "approve the mask, then:",
                    "facelab.ps1 zone -Image <target> -Mask <approved_mask.png>"
                    + (f" -Lora {lora}" if lora else " -Lora <preview-lora>"),
                ]}
    realism = classify_realism(face_report, face_index)
    frontal = is_frontal(face_report, face_index)
    # Preferred realistic lane: stable + frontal + realistic + ReActor installed.
    if realism == "realistic" and frontal and reactor_available and has_references:
        lanes.append({"lane": "realistic_reactor_refine",
                      "why": "stable front-facing realistic target: ReActor identity "
                             "transfer, facial-hair mask, low-denoise cleanup, verified",
                      "engine": {"non_commercial": True}})
    elif realism == "realistic" and frontal and reactor_available and not has_references:
        skipped.append({"lane": "realistic_reactor_refine",
                        "why_skipped": "no reference photo in profiles/me/references"})
    elif realism == "realistic" and frontal and not reactor_available:
        skipped.append({"lane": "realistic_reactor_refine",
                        "why_skipped": "ReActor/inswapper not installed (Face Lab preflight)"})
    if realism == "realistic":
        skipped.append({"lane": "quality_photo_anchored",
                        "why_skipped": "realistic human targets must not use the anime face-zone recipe"})
    elif ipadapter_graph_exists and identity_photo:
        lanes.append({"lane": "quality_photo_anchored",
                      "why": "license-clean identity from a real photo; no LoRA needed",
                      "engine": PHOTO_ANCHORED_ENGINE(identity_photo)})
    elif ipadapter_graph_exists:
        skipped.append({"lane": "quality_photo_anchored",
                        "why_skipped": "no reference photo in profiles/me/references"})
    if lora:
        lanes.append({"lane": "quality_lora_mesh",
                      "why": "explicit preview LoRA on the proven gojo avenue "
                             "(identity_fill d0.28 / mesh 0.40, eyes protected)",
                      "engine": dict(GOJO_AVENUE_ENGINE)})
        lanes.append({"lane": "auto_facedetailer",
                      "why": "fast backup: detect->mask->redraw with the explicit LoRA",
                      "engine": {}})
    else:
        skipped.append({"lane": "quality_lora_mesh",
                        "why_skipped": "no deployed identity LoRA; pass --lora to use a private preview"})
        skipped.append({"lane": "auto_facedetailer", "why_skipped": "same — needs an explicit LoRA"})
    plan = {"gate": gate, "lanes": lanes, "skipped": skipped,
            "realism": realism, "frontal": frontal}
    if not lanes:
        plan["stop_reason"] = ("no runnable lane: add a reference photo to "
                               "profiles/me/references (free lane) or pass --lora")
    return plan


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="one-command swap conductor")
    ap.add_argument("--image", required=True)
    ap.add_argument("--lora", help="explicit private-preview identity LoRA")
    ap.add_argument("--recipe", default="anime_face_zone_edit@2")
    ap.add_argument("--preset", default="auto")
    ap.add_argument("--project", default="image_lab")
    ap.add_argument("--profile", default="me")
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    ap.add_argument("--plan", action="store_true", help="decide + print, run nothing")
    ap.add_argument("--finish", action="store_true",
                    help="polish an already-good composite: one low-denoise pass "
                         "over the face zone (speckle/seam removal), identity and "
                         "eyes untouched")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    target = Path(args.image)
    if not target.is_file():
        print(f"[byrdswap] image not found: {target}")
        return 2

    if args.finish:
        try:
            src = finish_source(target)
        except ValueError as exc:
            print(f"[byrdswap] finish refused: {exc}")
            return 1
        original = Path(src["original"])
        if not original.is_file():
            print(f"[byrdswap] the recorded immutable original is missing: {original}")
            return 1
        print("[byrdswap] FINISH: re-rendering GENERATION 1 from the immutable original")
        print(f"[byrdswap]   original: {original}")
        print(f"[byrdswap]   settings from job {src['from_job']} (same seed {src['seed']}) "
              "through the repaired pipeline (d0.28 + GPU finish + guards)")
        engine = dict(src["engine"])
        engine.pop("skip_gpu_cleanup", None)  # the promoted GPU finish completes it
        try:
            job_id, saved = byrdimage.edit_face_zone(
                root, src["recipe"], original, args.project,
                f"byrdswap finish: fresh re-render of job {src['from_job']} — no generated parent",
                identity_lora=args.lora or src["lora"], target_preset=src["preset"],
                seed=src["seed"], engine=engine)
        except SystemExit as exc:
            print(f"[byrdswap] finish refused: {exc}")
            return 1
        for f, card in saved:
            print(f"[byrdswap] finished: {f}  (status={card.get('status')}, generation 1, + .verify.json)")
        return 0

    # 1. examine (thorough) — the bot's eyes; runs under the ComfyUI venv
    comfy_python = root / "Generators" / "ComfyUI" / ".venv" / "Scripts" / "python.exe"
    if not comfy_python.is_file():
        comfy_python = Path(sys.executable)
    report = byrdimage._face_report(root, comfy_python,
                                    root / "scripts" / "byrdfacezone.py", target)

    # 2. decide
    photo = find_identity_photo(root, args.profile)
    refs_dir = root / "profiles" / args.profile / "references"
    has_refs = refs_dir.is_dir() and any(
        p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        for p in refs_dir.iterdir()) if refs_dir.is_dir() else False
    reactor_available = _reactor_available(root)
    plan = plan_ladder(report, lora=args.lora, identity_photo=photo,
                       ipadapter_graph_exists=(root / PHOTO_ANCHOR_WORKFLOW).is_file(),
                       reactor_available=reactor_available, has_references=has_refs)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log = {"target": str(target), "started": stamp, "plan": plan, "attempts": []}
    out_dir = root / "logs" / "byrdswap"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"run_{stamp}.json"

    def save():
        report_file.write_text(json.dumps(run_log, indent=2), encoding="utf-8")

    print(f"[byrdswap] gate: stable={plan['gate']['stable']} "
          f"stability={plan['gate']['geometry_stability']}")
    for lane in plan["lanes"]:
        print(f"[byrdswap] planned: {lane['lane']} — {lane['why']}")
    for s in plan["skipped"]:
        print(f"[byrdswap] skipped: {s['lane']} — {s['why_skipped']}")
    if "stop_reason" in plan:
        print(f"[byrdswap] STOP: {plan['stop_reason']}")
        for step in plan.get("manual_next", []):
            print(f"[byrdswap]   next: {step}")
        save()
        return 3
    if args.plan:
        save()
        print(f"[byrdswap] plan only — report: {report_file}")
        return 0

    # 3. run the ladder with automatic fallback
    for lane in plan["lanes"]:
        name = lane["lane"]
        print(f"[byrdswap] === attempting {name} ===")
        attempt = {"lane": name, "started": datetime.now().isoformat()}
        try:
            if name == "realistic_reactor_refine":
                import realistic_reactor_refine as rrr
                rc = rrr.run(["--image", str(target), "--profile", args.profile,
                              "--project", args.project, "--root", str(root)])
                # rc: 0 accepted, 1 verified-but-rejected, 2/3 could-not-run
                attempt.update({"result": "ok" if rc == 0 else "rejected", "exit": rc})
                run_log["attempts"].append(attempt)
                if rc == 0:
                    run_log["outcome"] = {"lane": name, "exit": rc}
                    save()
                    print(f"[byrdswap] DONE via {name} (verified identity)")
                    print(f"[byrdswap] report: {report_file}")
                    return 0
                print(f"[byrdswap] {name} did not pass verification (exit {rc}) — falling back")
                continue
            if name in ("quality_photo_anchored", "quality_lora_mesh"):
                job_id, saved = byrdimage.edit_face_zone(
                    root, args.recipe, target, args.project,
                    f"byrdswap conductor: {name}",
                    identity_lora=args.lora if name == "quality_lora_mesh" else None,
                    target_preset=args.preset, engine=dict(lane["engine"]))
            else:  # auto_facedetailer
                job_id, saved = byrdimage.facezone_auto(
                    root, target, args.project, f"byrdswap conductor: {name}",
                    lora=args.lora)
            finals = [str(f) for f, _ in saved]
            rejected = [c.get("status") == "rejected" for _, c in saved]
            attempt.update({"result": "ok", "job_id": job_id, "finals": finals,
                            "all_rejected": all(rejected) if rejected else False})
            run_log["attempts"].append(attempt)
            if rejected and all(rejected):
                print(f"[byrdswap] {name} produced only gate-rejected output — falling back")
                continue
            run_log["outcome"] = {"lane": name, "finals": finals}
            save()
            print(f"[byrdswap] DONE via {name}")
            for f in finals:
                print(f"[byrdswap]   {f}  (+ .verify.json + card)")
            print(f"[byrdswap] report: {report_file}")
            return 0
        except SystemExit as exc:  # byrdimage.die() — honest refusal, try next rung
            attempt.update({"result": "refused", "reason": str(exc)})
            run_log["attempts"].append(attempt)
            print(f"[byrdswap] {name} refused: {exc}")
        except Exception as exc:  # noqa: BLE001 — record and step down
            attempt.update({"result": "error", "reason": f"{type(exc).__name__}: {exc}"})
            run_log["attempts"].append(attempt)
            print(f"[byrdswap] {name} failed: {exc}")

    run_log["outcome"] = {"lane": None,
                          "reason": "every runnable lane refused or failed — see attempts"}
    save()
    print(f"[byrdswap] NO RESULT — every lane refused/failed honestly. Report: {report_file}")
    return 1


if __name__ == "__main__":
    sys.exit(run())
