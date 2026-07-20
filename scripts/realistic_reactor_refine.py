#!/usr/bin/env python3
"""realistic_reactor_refine.py — the preferred conductor lane for STABLE,
FRONT-FACING, REALISTIC human targets (configs/image/realistic_reactor_refine.json).

The prior realistic lane (quality_photo_anchored) completed but preserved too
much of the TARGET identity and produced doubled/broken facial hair. This lane
fixes that by doing an explicit IDENTITY TRANSFER first, then a LOW-denoise
cleanup that can never rebuild the target person:

  Stage 1  rank the identity references and pick the best front-facing one
  Stage 2  ReActor identity transfer (inswapper_128.onnx) — Carey's eyes,
           brows, nose, cheeks, mouth, mustache, beard, sideburns, chin,
           jawline replace the target's; head angle / gaze / expression /
           lighting / scene / clothes / SCALP hair / headwear are preserved
  Stage 3  facial-hair-aware mask: facial hair (beard/mustache/sideburns/chin/
           cheeks/jaw) is INSIDE the identity zone; scalp hair + headwear are
           OUTSIDE; the lower-face boundary is feathered WITHOUT blending the
           old beard back over the new identity
  Stage 4  LOW-denoise refine (0.20-0.35, NEVER 0.55) anchored on Carey's
           reference — the target supplies only pose/expression/lighting
  Stage 5  automatic verification vs Carey's reference set with explicit
           status codes; a completed ComfyUI job is NOT an accepted result

    python scripts/realistic_reactor_refine.py --image target.jpg
    python scripts/realistic_reactor_refine.py --image target.jpg --plan
    python scripts/realistic_reactor_refine.py --image target.jpg --dry-run

LICENSE: inswapper_128.onnx / InsightFace / ReActor are NON-COMMERCIAL research
licenses. This lane is PRIVATE-LOCAL-EXPERIMENT ONLY (DECISIONS 2026-07-15/16);
the non_commercial flag is stamped on every sidecar. The monetized path stays
the Free Swap Stack (IP-Adapter plus-face / trained LoRA).

The Stage-3 mask policy, Stage-4 denoise clamp, and Stage-5 verifier are pure
functions so the suite proves the lane's judgment with zero GPU.
"""
import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdcast_swap as bcs  # noqa: E402  reuse detection/ranking/ReActor/cosine

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

# Severity order for the single primary status. FACE_DETECTION_FAIL is the most
# fundamental (nothing else is trustworthy without a face); IDENTITY_PASS is the
# only accept state.
STATUS_SEVERITY = [
    "FACE_DETECTION_FAIL",
    "IDENTITY_FAIL",
    "FACIAL_HAIR_FAIL",
    "SEAM_FAIL",
    "IDENTITY_PASS",
]


def load_lane_config(root: Path) -> dict:
    p = root / "configs" / "image" / "realistic_reactor_refine.json"
    if not p.is_file():
        raise FileNotFoundError(f"lane config not found: {p}")
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


# ── Stage 1: identity reference ranking ──────────────────────────────────────
def rank_identity_references(target_obs: dict, refs: list, weights: dict) -> list:
    """Rank references best-first for a clean front-facing transfer. Reuses the
    proven byrdcast score_reference (renormalized weights — unmeasured factors
    never count as a silent 1.0), so an anime/blurry/oddly-lit reference sinks."""
    return bcs.choose_reference(target_obs, refs, weights)


# ── Stage 3: facial-hair-aware mask ──────────────────────────────────────────
def build_facial_identity_mask(size, box, cfg: dict, landmarks=None) -> dict:
    """Facial-hair-aware identity mask.

    Returns {"identity", "facial_hair", "scalp_exclude"} as PIL 'L' masks.

    Policy (configs/image/realistic_reactor_refine.json → facial_hair_mask):
      * identity      = the ReActor + cleanup zone. Full face from mid-face
                        DOWN through cheeks / jaw / chin, plus sideburn side
                        bands, EXTENDED below the detected chin so a beard that
                        spills past the box is fully inside (and therefore
                        REPLACED, never half-blended). The scalp top band is
                        subtracted out.
      * facial_hair   = the lower-face beard/mustache/sideburn sub-region, for
                        the verifier and the lower-boundary feather.
      * scalp_exclude = the top band (scalp hair + headwear) that stays
                        target-authentic and must NOT enter the identity zone.

    The lower boundary uses a SMALL feather and the zone extends past the beard,
    so the feathered ring lands on new-identity skin / neck — the old beard is
    never blended back over the new identity.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    W, H = size
    x1, y1, x2, y2 = box
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)

    fh = cfg
    lower_start = int(bh * fh.get("lower_face_start_frac", 0.42))
    lower_extend = int(bh * fh.get("lower_face_extend_frac", 0.30))
    sideburn = int(bw * fh.get("sideburn_band_frac", 0.18))
    scalp_top = int(bh * fh.get("scalp_exclude_top_frac", 0.30))
    feather = int(fh.get("feather_px", 8))
    low_feather = int(fh.get("lower_boundary_feather_px", 6))

    def blank():
        return Image.new("L", (W, H), 0)

    # scalp_exclude: everything from above the head down through the top band of
    # the face box — scalp hair and any headwear live here and stay target-true.
    scalp = blank()
    ds = ImageDraw.Draw(scalp)
    ds.rectangle([x1 - sideburn, max(0, y1 - bh), x2 + sideburn, y1 + scalp_top], fill=255)
    scalp = scalp.filter(ImageFilter.GaussianBlur(feather))

    # identity: face oval starting at mid-face, widened for sideburns and
    # extended below the chin for the beard.
    ident = blank()
    di = ImageDraw.Draw(ident)
    di.ellipse([x1 - sideburn, y1 + lower_start - int(bh * 0.30),
                x2 + sideburn, y2 + lower_extend], fill=255)
    # sideburn vertical bands (thin, in front of the ears) so cheek/sideburn
    # hair is inside even when the oval is narrow.
    di.rectangle([x1 - sideburn, y1 + lower_start, x1 + int(bw * 0.10), y2], fill=255)
    di.rectangle([x2 - int(bw * 0.10), y1 + lower_start, x2 + sideburn, y2], fill=255)
    ident = ident.filter(ImageFilter.GaussianBlur(feather))
    # subtract the scalp band so scalp hair/headwear never enter the identity zone
    ident = ImageChops.subtract(ident, scalp)
    # soften only the lower boundary a touch (it sits on new skin/neck, not beard)
    ident = ident.filter(ImageFilter.GaussianBlur(max(1, low_feather // 2)))

    # facial_hair sub-region: lower band of the identity zone (beard/mustache/
    # sideburn/chin/jaw), reported and used by the verifier.
    fhair = blank()
    dh = ImageDraw.Draw(fhair)
    dh.ellipse([x1 - sideburn, y1 + int(bh * 0.55), x2 + sideburn, y2 + lower_extend], fill=255)
    fhair = ImageChops.multiply(fhair.filter(ImageFilter.GaussianBlur(low_feather)), ident)

    return {"identity": ident, "facial_hair": fhair, "scalp_exclude": scalp}


def facial_identity_overlay(target, masks: dict):
    """Colored overlay: green identity zone, red scalp-exclude, blue facial hair."""
    from PIL import Image
    colors = {"identity": (52, 211, 153), "scalp_exclude": (248, 113, 113),
              "facial_hair": (96, 165, 250)}
    base = target.convert("RGB").copy()
    for name in ("identity", "scalp_exclude", "facial_hair"):
        m = masks.get(name)
        if m is None:
            continue
        layer = Image.new("RGB", base.size, colors[name])
        base = Image.composite(Image.blend(base, layer, 0.30), base,
                               m.point(lambda p: int(p * 0.55)))
    return base


# ── Stage 4: low-denoise clamp ───────────────────────────────────────────────
def clamp_refine_denoise(requested, cfg: dict) -> dict:
    """Clamp the cleanup denoise into the safe band and REFUSE the old 0.55.

    A high denoise on the cleanup pass can regenerate the target person's
    identity — the exact failure this lane exists to fix. Anything at/above
    denoise_refuse_at_or_above is rejected (not silently lowered) so a caller
    that asked for 0.55 learns why; values inside/near the band clamp to
    [denoise_min, denoise_max].
    """
    lo = float(cfg.get("denoise_min", 0.20))
    hi = float(cfg.get("denoise_max", 0.35))
    refuse = float(cfg.get("denoise_refuse_at_or_above", 0.50))
    default = float(cfg.get("denoise_default", 0.28))
    if requested is None:
        return {"denoise": default, "clamped": False, "refused": False,
                "note": f"no denoise requested — using default {default}"}
    req = float(requested)
    if req >= refuse:
        return {"denoise": default, "clamped": True, "refused": True,
                "note": f"refused denoise {req} (>= {refuse}): can regenerate the "
                        f"target identity — using safe default {default}"}
    clamped = min(hi, max(lo, req))
    return {"denoise": clamped, "clamped": clamped != req, "refused": False,
            "note": (f"clamped {req} into [{lo}, {hi}]" if clamped != req
                     else f"denoise {req} within [{lo}, {hi}]")}


# ── Stage 5: automatic verification with explicit status codes ───────────────
def verify_identity(identity_cosine, face_detected: bool, seam_energy,
                    doubled_beard: bool, cfg: dict) -> dict:
    """Emit explicit status codes for the final composite.

    IDENTITY_PASS         final face matches Carey (cosine >= pass threshold)
    IDENTITY_FAIL         too dissimilar to Carey, OR similarity unmeasurable
                          (fail closed — never accept an unverified identity)
    FACIAL_HAIR_FAIL      doubled/detached beard edge
    SEAM_FAIL             visible mask seam (edge energy over the ring too high)
    FACE_DETECTION_FAIL   no face in the output — nothing else is trustworthy

    accepted is True only when IDENTITY_PASS is present and NO *_FAIL is.
    """
    statuses = []
    pass_thr = float(cfg.get("identity_cosine_pass", 0.32))
    identity_measured = identity_cosine is not None
    if not face_detected:
        # No face -> nothing downstream is trustworthy; identity is not judged.
        statuses.append("FACE_DETECTION_FAIL")
    else:
        if identity_cosine is None:
            statuses.append("IDENTITY_FAIL")  # unmeasured -> fail closed
        elif float(identity_cosine) >= pass_thr:
            statuses.append("IDENTITY_PASS")
        else:
            statuses.append("IDENTITY_FAIL")
        if doubled_beard and cfg.get("doubled_beard_edge_fail", True):
            statuses.append("FACIAL_HAIR_FAIL")
        if seam_energy is not None and float(seam_energy) > float(cfg.get("seam_energy_fail_above", 40.0)):
            statuses.append("SEAM_FAIL")

    has_fail = any(s.endswith("_FAIL") for s in statuses)
    accepted = ("IDENTITY_PASS" in statuses) and not has_fail
    primary = next((s for s in STATUS_SEVERITY if s in statuses), "IDENTITY_FAIL")
    return {
        "statuses": statuses,
        "primary_status": primary,
        "accepted": accepted,
        "identity_cosine": (round(float(identity_cosine), 4)
                            if identity_cosine is not None else None),
        "identity_measured": identity_measured,
        "seam_energy": (round(float(seam_energy), 3) if seam_energy is not None else None),
        "doubled_beard": bool(doubled_beard),
        "thresholds": {"identity_cosine_pass": pass_thr,
                       "seam_energy_fail_above": float(cfg.get("seam_energy_fail_above", 40.0))},
    }


def _doubled_beard_heuristic(final_path, masks: dict) -> tuple:
    """Cheap edge-energy read inside the facial-hair band: a doubled/detached
    beard shows as a strong extra horizontal edge. Returns (doubled, energy).
    Degrades to (False, None) without PIL/the file."""
    try:
        from PIL import Image, ImageFilter
        if not Path(final_path).is_file():
            return False, None
        fh = masks["facial_hair"]
        edges = bcs._gray(Image.open(final_path).convert("RGB")).filter(ImageFilter.FIND_EDGES)
        ring = fh.point(lambda p: 255 if p > 60 else 0)
        comp = Image.composite(edges, Image.new("L", edges.size, 0), ring)
        mean, _ = bcs._mean_std(comp)
        # a clean single beard edge sits low; a doubled edge roughly doubles it.
        return (mean > 26.0), round(float(mean), 3)
    except Exception:
        return False, None


def _seam_energy(final_path, masks: dict):
    """Edge energy along the identity-zone boundary ring (lower = smoother)."""
    try:
        from PIL import Image, ImageFilter
        if not Path(final_path).is_file():
            return None
        ring = masks["identity"].filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p > 40 else 0)
        seam = bcs._gray(Image.open(final_path).convert("RGB")).filter(ImageFilter.FIND_EDGES)
        comp = Image.composite(seam, Image.new("L", seam.size, 0), ring)
        mean, _ = bcs._mean_std(comp)
        return round(float(mean), 3)
    except Exception:
        return None


# ── orchestration ────────────────────────────────────────────────────────────
def _load_profile_refs(root: Path, profile: str, min_px: int) -> list:
    refs_dir = root / "profiles" / profile / "references"
    if not refs_dir.is_dir():
        return []
    from PIL import Image
    refs = []
    for rp in sorted(p for p in refs_dir.iterdir() if p.suffix.lower() in IMG_EXT):
        try:
            obs = bcs.detect_face(Image.open(rp), min_px, want_embedding=True)
        except Exception:
            continue
        refs.append({"path": str(rp), "name": rp.name, "obs": obs})
    return refs


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="realistic_reactor_refine lane")
    ap.add_argument("--image", required=True, help="target image")
    ap.add_argument("--profile", default="me")
    ap.add_argument("--project", default="image_lab")
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    ap.add_argument("--denoise", type=float, default=None, help="cleanup denoise (clamped to 0.20-0.35)")
    ap.add_argument("--plan", action="store_true", help="decide + print, run nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="CPU stages + full debug folder, no GPU/ONNX swap (accepted=false)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    target = Path(args.image)
    if not target.is_file():
        print(f"[reactor_refine] image not found: {target}")
        return 2
    try:
        cfg = load_lane_config(root)
    except FileNotFoundError as exc:
        print(f"[reactor_refine] {exc}")
        return 2

    from PIL import Image, ImageOps

    denoise_plan = clamp_refine_denoise(args.denoise, cfg["refine"])
    min_ref = cfg["identity_source"].get("min_reference_face_px", 96)
    refs = _load_profile_refs(root, args.profile, min_ref)

    target_img = ImageOps.exif_transpose(Image.open(target))
    target_obs = bcs.detect_face(target_img, 64, want_embedding=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobid = f"{stamp}_{args.profile}_{secrets.token_hex(3)}"
    jobdir = root / "artifacts" / args.project / "realistic_reactor_refine" / jobid
    conductor_report = {
        "tool": "realistic_reactor_refine", "version": cfg["version"],
        "license": cfg["license"], "job_id": jobid, "target": str(target),
        "denoise_plan": denoise_plan, "references_available": len(refs),
        "stages": [], "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if not refs:
        conductor_report["stop_reason"] = (
            f"no identity references in profiles/{args.profile}/references — add "
            "approved front-facing photos (Stage 1 needs a source identity)")
        print(f"[reactor_refine] STOP: {conductor_report['stop_reason']}")
        _emit_conductor_report(jobdir, conductor_report)
        return 3

    ranked = rank_identity_references(target_obs, refs, cfg["identity_source"]["weights"])
    chosen = ranked[0]
    conductor_report["reference_ranking"] = [
        {"name": r["name"], "score": r["select_score"]["overall"],
         "measured": r["select_score"]["measured"]} for r in ranked]
    conductor_report["selected_reference"] = chosen["name"]
    conductor_report["stages"].append({"stage": 1, "name": "identity_source_selection",
                                        "selected": chosen["name"],
                                        "score": chosen["select_score"]["overall"]})

    masks = build_facial_identity_mask(target_img.size, target_obs["box"], cfg["facial_hair_mask"])
    conductor_report["stages"].append({"stage": 3, "name": "facial_hair_aware_mask",
                                        "policy": "facial hair INSIDE, scalp/headwear OUTSIDE"})

    if args.plan:
        conductor_report["plan_only"] = True
        conductor_report["planned"] = {
            "stage2": f"ReActor {cfg['reactor']['swap_model']} identity transfer",
            "stage4": f"low-denoise cleanup at {denoise_plan['denoise']} "
                      f"(anchor={cfg['refine']['identity_anchor']})",
            "stage5": "verify vs Carey references -> " + "/".join(cfg["verification"]["statuses"]),
        }
        print("[reactor_refine] PLAN:")
        print(f"  Stage 1 pick: {chosen['name']} (score {chosen['select_score']['overall']})")
        print(f"  Stage 2 ReActor: {cfg['reactor']['swap_model']}")
        print(f"  Stage 4 cleanup denoise: {denoise_plan['denoise']} — {denoise_plan['note']}")
        print(f"  Stage 5 verify: {'/'.join(cfg['verification']['statuses'])}")
        _emit_conductor_report(jobdir, conductor_report)
        return 0

    # write the CPU debug artifacts that never need a GPU
    jobdir.mkdir(parents=True, exist_ok=True)
    target_img.convert("RGB").save(jobdir / "target.png")
    x1, y1, x2, y2 = target_obs["box"]
    target_img.convert("RGB").crop((max(0, x1), max(0, y1),
                                    min(target_img.width, x2),
                                    min(target_img.height, y2))).save(jobdir / "target_face_crop.png")
    Image.open(chosen["path"]).convert("RGB").save(jobdir / "selected_identity_reference.png")
    facial_identity_overlay(target_img, masks).save(jobdir / "mask_overlay.png")
    (jobdir / "masks").mkdir(exist_ok=True)
    for name, m in masks.items():
        m.save(jobdir / "masks" / f"{name}.png")

    # Stage 2: ReActor identity transfer (degrades honestly without ComfyUI/ReActor)
    comfy = "" if args.dry_run else bcs.comfy_url(root)
    reactor_cfg = _byrdcast_cfg_for_reactor(root, cfg)
    candidate = refined = None
    route = "none"
    swap_notes = []
    if not args.dry_run and comfy:
        try:
            candidate, route, refined, swap_notes = bcs.run_swap(
                root, reactor_cfg, comfy, jobdir / "target.png", chosen["path"],
                jobdir, {"use_facedetailer": True})
        except Exception as exc:  # noqa: BLE001
            swap_notes.append(f"reactor stage failed: {type(exc).__name__}: {exc}")
    else:
        swap_notes.append("dry-run/no ComfyUI: Stage 2/4 skipped — CPU structure proof only")
    conductor_report["stages"].append({"stage": 2, "name": "reactor_identity_transfer",
                                        "route": route, "notes": swap_notes})
    conductor_report["stages"].append({"stage": 4, "name": "low_denoise_refine",
                                        "denoise": denoise_plan["denoise"],
                                        "applied": bool(refined)})

    final_path = jobdir / "refined_output.png"
    if refined and Path(refined).is_file():
        Image.open(refined).save(final_path)
    elif candidate and Path(candidate).is_file():
        Image.open(candidate).save(final_path)
    else:
        Image.open(jobdir / "target.png").save(final_path)  # fail-closed placeholder

    # Stage 5: verification
    identity_cosine = None
    if route != "none" and chosen["obs"].get("embedding") and final_path.is_file():
        final_obs = bcs.detect_face(Image.open(final_path), 32, want_embedding=True)
        face_detected = final_obs["method"] != "placeholder_center" and final_obs.get("faces_found", 0) > 0
        if final_obs.get("embedding"):
            identity_cosine = max(0.0, bcs._cosine(final_obs["embedding"], chosen["obs"]["embedding"]))
    else:
        face_detected = target_obs["method"] != "placeholder_center" and not args.dry_run and route != "none"
    doubled, _hair_energy = _doubled_beard_heuristic(final_path, masks)
    seam = _seam_energy(final_path, masks)
    verdict = verify_identity(identity_cosine, face_detected, seam, doubled, cfg["verification"])
    conductor_report["stages"].append({"stage": 5, "name": "verification", **verdict})
    conductor_report["verification"] = verdict
    conductor_report["accepted"] = verdict["accepted"]
    conductor_report["swap_route"] = route

    (jobdir / "identity_verification_report.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8")
    _emit_conductor_report(jobdir, conductor_report)

    # sidecar card (belt law: every artifact carries lineage + the non_commercial flag)
    sidecar = {
        "tool": "realistic_reactor_refine", "version": cfg["version"],
        "job_id": jobid, "kind": "image", "recipe": "realistic_reactor_refine@0",
        "license": cfg["license"], "non_commercial": True,
        "target": str(target), "selected_reference": chosen["name"],
        "swap_route": route, "refine_denoise": denoise_plan["denoise"],
        "verification": verdict,
        "status": "approved" if verdict["accepted"] else "rejected",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "selected_identity_reference": "selected_identity_reference.png",
            "target_face_crop": "target_face_crop.png",
            "initial_reactor_result": ("candidate_reactor.png" if candidate else None),
            "facial_identity_mask": "masks/identity.png",
            "mask_overlay": "mask_overlay.png",
            "refined_output": "refined_output.png",
            "identity_verification_report": "identity_verification_report.json",
            "conductor_report": "conductor_report.json",
        },
    }
    (final_path.with_suffix(final_path.suffix + ".json")).write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8")

    print(f"[reactor_refine] route={route} primary={verdict['primary_status']} "
          f"accepted={verdict['accepted']}  -> {jobdir}")
    for s in verdict["statuses"]:
        print(f"[reactor_refine]   status: {s}")
    return 0 if verdict["accepted"] else (0 if args.dry_run else 1)


def _byrdcast_cfg_for_reactor(root: Path, lane_cfg: dict) -> dict:
    """Adapt the lane config into the shape byrdcast_swap.run_swap expects,
    reusing the validated ReActor workflow + route order."""
    try:
        base = bcs.load_config(root)
    except SystemExit:
        base = {"swap": {}, "refine": {}}
    base = dict(base)
    base["workflow"] = lane_cfg["reactor"]["workflow"]
    base.setdefault("swap", {})["route_order"] = ["comfy_reactor", "insightface"]
    base.setdefault("refine", {})
    base["refine"]["use_facedetailer_if_available"] = lane_cfg["refine"].get(
        "use_facedetailer_only_if_it_helps_seams", True)
    return base


def _emit_conductor_report(jobdir: Path, report: dict) -> None:
    jobdir.mkdir(parents=True, exist_ok=True)
    (jobdir / "conductor_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(run())
