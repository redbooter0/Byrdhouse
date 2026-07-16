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


def plan_ladder(face_report: dict, face_index: int = 0, lora: str | None = None,
                identity_photo: str | None = None,
                ipadapter_graph_exists: bool = True) -> dict:
    """Pure decision function: examiner report -> ordered lane plan.
    Never touches the network/GPU, so the bot's judgment is unit-testable."""
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
    if ipadapter_graph_exists and identity_photo:
        lanes.append({"lane": "quality_photo_anchored",
                      "why": "license-clean identity from a real photo; no LoRA needed",
                      "engine": {"workflow": PHOTO_ANCHOR_WORKFLOW,
                                 "identity_photo": str(identity_photo)}})
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
    plan = {"gate": gate, "lanes": lanes, "skipped": skipped}
    if not lanes:
        plan["stop_reason"] = ("no runnable lane: add a reference photo to "
                               "profiles/me/references (free lane) or pass --lora")
    return plan


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="one-command swap conductor")
    ap.add_argument("--image", required=True)
    ap.add_argument("--lora", help="explicit private-preview identity LoRA")
    ap.add_argument("--recipe", default="anime_face_zone_edit.v2")
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
    plan = plan_ladder(report, lora=args.lora, identity_photo=photo,
                       ipadapter_graph_exists=(root / PHOTO_ANCHOR_WORKFLOW).is_file())
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
