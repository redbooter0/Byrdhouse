"""
byrdimage.py — ByrdHouse image submit layer (Blueprint v2 §1.4 Action 3, §8, §9).

Recipe in -> ComfyUI job out -> archived images + sidecar metadata cards.

Fixes the four repetition causes at the submit layer:
  1. seed randomized per job (never the workflow's baked-in seed)
  2. unique filename_prefix per job (no stale-output confusion)
  3. prompt injected into EVERY CLIPTextEncode node, verified, or we abort
  4. actually-loaded checkpoint recorded on the metadata card

Stdlib only — no pip installs needed on the machines.

Usage (from any terminal with BYRDHOUSE_ROOT set):
  python byrdimage.py --recipe rpg_tier_list --project careyrpg \
      --purpose "tier list thumbnail test" \
      --set subject="armored paladin" --set game="Last Epoch"

  --recipe NAME     recipe id; picks the highest version in %ROOT%/recipes
  --set k=v         fill a template slot (repeatable). Unfilled slots that have
                    a "vary" list get a random pick; other unfilled slots abort.
  --project ID      project folder for the archive (default: sandbox)
  --purpose TEXT    required — no artifact without a purpose
  --batch N         override recipe batch
  --checkpoint X    override checkpoint
  --dry-run         build + validate the graph, print it, submit nothing
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import secrets
import string
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def die(msg: str) -> None:
    # SystemExit with a string: CLI prints it to stderr and exits nonzero;
    # the worker daemon catches it and records the message on the dead job.
    raise SystemExit(f"[byrdimage] {msg}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_original_target(root: Path, target: Path) -> Path:
    """Reject generated outputs as inputs to every target-edit retry.

    A retry is allowed to reuse the immutable uploaded/original target, never a
    ByrdHouse artifact or raw ComfyUI output from an earlier attempt.  That
    prevents accidental edit-on-edit drift and makes each result comparable.
    """
    root = root.resolve()
    target = target.resolve()
    immutable_upload_root = (root / "artifacts" / "_sources").resolve()
    forbidden_roots = (
        root / "artifacts",
        root / "Generators" / "ComfyUI" / "output",
    )
    for forbidden in forbidden_roots:
        try:
            target.relative_to(forbidden.resolve())
        except ValueError:
            continue
        try:
            target.relative_to(immutable_upload_root)
        except ValueError:
            pass
        else:
            continue
        die(
            "fresh-retry policy rejected a generated target: "
            f"{target}. Start from the original upload/target instead."
        )
    sidecar = target.with_suffix(target.suffix + ".json")
    if sidecar.is_file():
        try:
            metadata = load_json(sidecar)
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if metadata.get("artifact_id") or metadata.get("job_id"):
            die(
                "fresh-retry policy rejected an image with a generation card: "
                f"{target}. Start from the original upload/target instead."
            )
    return target


def load_json(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _png_size(path):
    """(width, height) from a PNG's IHDR header — stdlib only, no Pillow, so the
    refine layer can record output resolution without a pip dependency."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except Exception:
        pass
    return None


def new_id(prefix: str) -> str:
    ts = format(int(time.time() * 1000), "x")
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}_{ts}{rand}"


def find_recipe(root: Path, name: str) -> Path:
    # 'name@N' pins that exact version (the dashboard sends this so the
    # version you pick is the version that runs); bare 'name' = highest.
    m = re.fullmatch(r"([\w-]+)@(\d+)", name)
    if m:
        p = root / "recipes" / f"{m.group(1)}.v{m.group(2)}.json"
        if not p.exists():
            die(f"no recipe '{m.group(1)}' v{m.group(2)} in {root / 'recipes'}")
        return p
    candidates = sorted((root / "recipes").glob(f"{name}.v*.json"))
    if not candidates:
        die(f"no recipe '{name}' in {root / 'recipes'}")
    def version(p: Path) -> int:
        vm = re.search(r"\.v(\d+)\.json$", p.name)
        return int(vm.group(1)) if vm else 0
    return max(candidates, key=version)


def _comfy_checkpoints(comfy: str) -> list:
    """Ask ComfyUI itself what checkpoints it can load — works even when the
    install lives outside the ByrdHouse root."""
    try:
        with urllib.request.urlopen(f"{comfy}/object_info/CheckpointLoaderSimple",
                                    timeout=10) as r:
            info = json.loads(r.read().decode())
        return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
    except Exception:
        return []


def resolve_checkpoint(root: Path, requested: str, comfy: str = "") -> str:
    """Interchangeable by design: match the request against what is actually
    installed (disk first, ComfyUI API as fallback); if nothing matches but
    checkpoints exist, use the first installed one rather than failing."""
    requested = requested.strip()
    if not requested:
        die("no checkpoint")

    stem = requested[:-len(".safetensors")] if requested.lower().endswith(".safetensors") else requested

    installed = [p.name for p in sorted(
        (root / "Generators" / "ComfyUI" / "models" / "checkpoints").glob("*.safetensors"))]
    if not installed and comfy:
        installed = _comfy_checkpoints(comfy)
    if not installed:
        return requested if requested.lower().endswith(".safetensors") else f"{requested}.safetensors"

    def norm(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    requested_norm, stem_norm = norm(requested), norm(stem)
    exact = [n for n in installed if norm(n) == requested_norm or norm(Path(n).stem) == stem_norm]
    if exact:
        return exact[0]
    partial = [n for n in installed if requested_norm in norm(n) or stem_norm in norm(Path(n).stem)]
    if partial:
        return min(partial, key=len)
    print(f"[byrdimage] no checkpoint matches '{requested}' — FALLBACK to installed '{installed[0]}'")
    return installed[0]


def resolve_checkpoint_info(root: Path, requested: str, comfy: str = "") -> tuple:
    """Like resolve_checkpoint but also reports whether a fallback happened, so
    the card can record requested-vs-resolved honestly (a silent wrong model
    makes a job look successful while producing the wrong art)."""
    resolved = resolve_checkpoint(root, requested, comfy)
    req = requested.strip()
    req_full = req if req.lower().endswith(".safetensors") else f"{req}.safetensors"
    matched = resolved.lower() in (req.lower(), req_full.lower()) or \
        re.sub(r"[^a-z0-9]+", "", req.lower()) in re.sub(r"[^a-z0-9]+", "", resolved.lower())
    return resolved, matched


# SDXL-native resolutions per aspect — off-grid sizes degrade SDXL badly,
# so requests snap to these. 16:9 stays the thumbnail default.
ASPECTS = {
    "16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024),
    "4:3": (1152, 896), "3:4": (896, 1152), "3:2": (1216, 832),
    "2:3": (832, 1216), "21:9": (1536, 640),
}


def pick_dims(aspect=None, width=None, height=None, img_cfg=None):
    """Explicit width/height wins; else an aspect preset; else config default."""
    if width and height:
        return int(width), int(height)
    if aspect:
        if aspect not in ASPECTS:
            die(f"unknown aspect '{aspect}' — pick one of {', '.join(ASPECTS)}")
        return ASPECTS[aspect]
    img_cfg = img_cfg or {}
    return img_cfg.get("width", 1152), img_cfg.get("height", 768)


def resolve_lora(root: Path, requested: str) -> str:
    """Match a requested LoRA against models/loras the same loose way
    checkpoints resolve — game-style LoRAs are the 'any game, accurately' key."""
    loras = sorted((root / "Generators" / "ComfyUI" / "models" / "loras").glob("*.safetensors"))
    def norm(t): return re.sub(r"[^a-z0-9]+", "", t.lower())
    want = norm(requested)
    exact = [p for p in loras if norm(p.stem) == want or norm(p.name) == want]
    if exact:
        return exact[0].name
    partial = [p for p in loras if want in norm(p.name)]
    if partial:
        return min(partial, key=lambda p: len(p.name)).name
    if loras:
        die(f"no LoRA matching '{requested}' — installed: {', '.join(p.name for p in loras)}")
    return requested if requested.lower().endswith(".safetensors") else f"{requested}.safetensors"


def select_identity_lora(root: Path, identity: dict, override: str | None) -> tuple[str, str]:
    """Honest identity-LoRA selection (repair G, 2026-07-16).

    Order: an explicit job -Lora ALWAYS wins and resolves normally. A
    recipe-declared LoRA must exist EXACTLY (normalized name) — a stale
    recipe value never partial-matches its way onto an unapproved preview
    candidate. When neither yields a real file, say so plainly.
    Returns (resolved_name, lora_status). Raises ValueError with the exact
    reason otherwise.
    """
    def norm(t):
        return re.sub(r"[^a-z0-9]+", "", str(t).lower())
    loras_dir = root / "Generators" / "ComfyUI" / "models" / "loras"
    installed = sorted(loras_dir.glob("*.safetensors")) if loras_dir.is_dir() else []
    if override:
        exact = [p for p in installed if norm(p.stem) == norm(override) or norm(p.name) == norm(override)]
        partial = [p for p in installed if norm(override) in norm(p.name)]
        chosen = exact[0] if exact else (min(partial, key=lambda p: len(p.name)) if partial else None)
        if chosen is None:
            raise ValueError(
                f"-Lora '{override}' is not installed in models/loras — installed: "
                + (", ".join(p.name for p in installed) or "none"))
        return chosen.name, "explicit-override (preview/private until a candidate is promoted)"
    declared = identity.get("lora")
    if declared:
        exact = [p for p in installed if norm(p.stem) == norm(declared) or norm(p.name) == norm(declared)]
        if exact:
            return exact[0].name, "recipe-deployed"
        raise ValueError(
            f"recipe requests identity LoRA '{declared}' but it is not installed and "
            "NO identity LoRA has been deployed/approved. Pass -Lora <installed file> "
            "explicitly to run with a private preview candidate (it stays a preview — "
            "this never promotes it). Installed: "
            + (", ".join(p.name for p in installed) or "none"))
    raise ValueError(
        "no deployed identity LoRA exists: the recipe declares none and no -Lora was "
        "provided. Every current candidate is a private preview "
        "(docs/IMAGE_GENERATION_STATE.md) — pass -Lora explicitly to use one.")


def validate_graph_classes(graph: dict, node_catalog) -> list:
    """Return the class_types a graph needs that the ComfyUI catalog lacks.
    node_catalog is the /object_info response (dict of class_type -> spec) or
    any iterable of known class names. Used by preflight for live schema
    validation and by the suite for honest-workflow checks (repair E)."""
    known = set(node_catalog.keys() if isinstance(node_catalog, dict) else node_catalog)
    needed = {node.get("class_type") for node in graph.values()
              if isinstance(node, dict) and node.get("class_type")}
    return sorted(needed - known)


def require_workflow_models(root: Path, graph: dict, workflow_rel: str) -> None:
    """Refuse BEFORE submit when a graph needs a model file that is not
    installed (repair E: the combined diffdiff+canny graph must state the
    missing ControlNet instead of dying as an HTTP 400)."""
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "ControlNetLoader":
            name = str(node.get("inputs", {}).get("control_net_name", ""))
            model = root / "Generators" / "ComfyUI" / "models" / "controlnet" / name
            if not model.is_file():
                raise ValueError(
                    f"workflow {workflow_rel} needs ControlNet model '{name}' "
                    f"(node {node_id}) which is NOT installed in models/controlnet. "
                    "Install it per docs/MODELS.md, or use the TRUE "
                    "DifferentialDiffusion workflow "
                    "(workflows/sd15_face_zone_diffdiff_api.json) which requires "
                    "no ControlNet model.")


def geometry_gate(face_report: dict, face_index: int = 0,
                  stability_threshold: float = 0.35,
                  profile_threshold: float = 0.6) -> dict:
    """Fail-closed geometry gate (repair A, 2026-07-16 — hard Vegeta).

    Decides, from the examiner's thorough checks, whether this face may be
    treated as a normal mesh-warp case and whether a CPU-only warp result may
    ever be founder-facing. Unstable geometry (low/missing stability score,
    cross-scale landmark disagreement, or a strong profile without solid
    stability) blocks both — those targets go to the reviewed-mask route.
    The decision dict rides the artifact card either way.
    """
    faces = {f.get("index"): f for f in face_report.get("faces", [])}
    face = faces.get(face_index) or (face_report.get("faces") or [{}])[0]
    checks = dict(face.get("checks") or {})
    flags = list(face.get("flags") or [])
    stability = checks.get("geometry_stability")
    warning = checks.get("geometry_warning")
    reasons = []
    if stability is None:
        reasons.append("geometry stability could not be measured (rescale re-detect failed)")
    elif stability < stability_threshold:
        reasons.append(f"geometry_stability {stability} is below the {stability_threshold} floor")
    if warning:
        reasons.append(str(warning))
    if "strong_profile" in " ".join(flags) and (stability is None or stability < profile_threshold):
        reasons.append(f"strong_profile with unstable geometry "
                       f"(stability {stability} < {profile_threshold})")
    stable = not reasons
    return {
        "geometry_stability": stability,
        "flags": flags,
        "stable": stable,
        "mesh_case_allowed": stable,
        "cpu_final_allowed": stable,
        "reasons": reasons,
        "fallback": ("reviewed-mask route: facelab preview -> founder approves the "
                     "semantic mask -> facelab zone (no mesh warp, no detector guess)"
                     if not stable else None),
        "thresholds": {"stability": stability_threshold, "strong_profile": profile_threshold},
    }


def insert_lora(graph: dict, lora_name: str, strength: float = 0.9,
                lora_id: str = "byrd_lora", source_id: str | None = None,
                clip_strength: float | None = None) -> None:
    """Splice a LoRA after a checkpoint or another LoRA.

    The normal image lane calls this once. The compact anime lane calls it twice
    when a quality identity LoRA and the optional LCM draft LoRA are both active,
    so the second loader must follow the first instead of replacing it.
    """
    source_id = source_id or next((nid for nid, n in graph.items()
                                   if n.get("class_type") == "CheckpointLoaderSimple"), None)
    if not source_id:
        die("workflow has no CheckpointLoaderSimple — cannot attach a LoRA")
    if lora_id in graph:
        die(f"workflow already contains LoRA node '{lora_id}'")
    for nid, node in graph.items():
        if nid == lora_id:
            continue
        for key, ref in node.get("inputs", {}).items():
            if isinstance(ref, list) and len(ref) == 2 and str(ref[0]) == str(source_id) and ref[1] in (0, 1):
                node["inputs"][key] = [lora_id, ref[1]]
    clip_weight = strength if clip_strength is None else float(clip_strength)
    graph[lora_id] = {"class_type": "LoraLoader",
                      "inputs": {"lora_name": lora_name,
                                 "strength_model": strength, "strength_clip": clip_weight,
                                 "model": [source_id, 0], "clip": [source_id, 1]}}


def upload_image(comfy: str, path: Path) -> str:
    """Push an image into ComfyUI's input store (multipart, stdlib only) so
    img2img graphs can LoadImage it. Returns the stored name."""
    boundary = f"----byrd{secrets.token_hex(8)}"
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
        f"filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{comfy}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode()).get("name", path.name)


def _format_comfy_http_error(status: int, body: str) -> str:
    """Turn a ComfyUI HTTP error into a diagnosable message: status, error
    text, prompt-validation details, and every offending node id/class_type
    from node_errors. Never just 'HTTP Error 400: Bad Request' (repair F,
    2026-07-16 — the diffdiff 400 was undiagnosable without the body)."""
    lines = [f"ComfyUI returned HTTP {status}"]
    body = (body or "").strip()
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        if body:
            lines.append(f"response body: {body[:1500]}")
        return "\n".join(lines)
    err = payload.get("error")
    if isinstance(err, dict):
        lines.append(f"error: {err.get('type', '?')} — {err.get('message', '')}"
                     + (f" ({err.get('details')})" if err.get("details") else ""))
    elif err:
        lines.append(f"error: {err}")
    node_errors = payload.get("node_errors") or {}
    for node_id, node_err in node_errors.items():
        class_type = (node_err or {}).get("class_type", "?")
        for detail in (node_err or {}).get("errors", []):
            lines.append(f"node {node_id} ({class_type}): "
                         f"{detail.get('type', '?')} — {detail.get('message', '')}"
                         + (f" [{detail.get('details')}]" if detail.get("details") else ""))
        if not (node_err or {}).get("errors"):
            lines.append(f"node {node_id} ({class_type}): {node_err}")
    if len(lines) == 1 and body:
        lines.append(f"response body: {body[:1500]}")
    return "\n".join(lines)


def http_json(url: str, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        die(_format_comfy_http_error(exc.code, body))


def generate(root, recipe_name, slots, project, purpose,
             batch=None, checkpoint=None, dry_run=False, job_id=None,
             aspect=None, width=None, height=None, negative_extra=None,
             lora=None, lora_strength=0.9, lora_clip_strength=None,
             seed=None, reference=None,
             engine=None):
    """Run one image.generate: recipe -> ComfyUI -> archived PNGs + cards.
    Returns (job_id, [(png_path, card_dict), ...]). Raises SystemExit on
    validation errors (via die) — callers that need exceptions can catch it."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    recipe_path = find_recipe(root, recipe_name)
    recipe = load_json(recipe_path)
    recipe_tag = f"{recipe['id']}@{recipe['version']}"

    # ── Fill the template: explicit slots, then random picks from vary ───────
    slots = dict(slots)
    user_slots = dict(slots)  # what the founder actually asked for, kept on the card
    vary_picks = {}
    for k, options in recipe.get("vary", {}).items():
        if not options:
            die(f"recipe vary slot '{k}' has no options to pick from")
        # a vary slot is the belt's to fill: pick when the founder left it
        # missing OR blank, so a vary slot can never reach the template unfilled
        if not str(slots.get(k, "")).strip():
            vary_picks[k] = random.choice(options)
    slots.update(vary_picks)

    template = recipe["template"]
    missing = [k for k in re.findall(r"\{(\w+)\}", template) if k not in slots]
    if missing:
        die(f"unfilled slots {missing} — pass --set {missing[0]}=\"...\"")
    prompt = re.sub(r"\s+", " ", template.format(**slots)).strip()
    negative = recipe.get("negative", "")
    if negative_extra:
        negative = f"{negative}, {negative_extra}" if negative else str(negative_extra)

    defaults = recipe.get("defaults", {})
    engine = engine or {}
    ckpt_requested = checkpoint or engine.get("checkpoint") or defaults.get("checkpoint") or die("no checkpoint")
    checkpoint, ckpt_matched = resolve_checkpoint_info(root, ckpt_requested, comfy=comfy)
    batch = batch or defaults.get("batch", 1)
    steps = int(engine.get("steps") or defaults.get("steps", 30))

    # ── Build the graph ───────────────────────────────────────────────────────
    # Recipe can specify its own workflow graph; falls back to config defaults.
    workflow_rel = recipe.get("workflow")
    if not workflow_rel:
        if reference:
            workflow_rel = img_cfg.get("reference_workflow", "workflows/sdxl_ipadapter_api.json")
        else:
            workflow_rel = img_cfg.get("workflow", "workflows/sdxl_base_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)

    job_id = job_id or new_id("job")
    seed = int(seed) if seed else secrets.randbits(63)  # fix 1: random per job (or pinned for reruns)
    prefix = f"{datetime.now():%Y%m%d}_{recipe['id']}_{job_id}"  # fix 2: unique
    gen_w, gen_h = pick_dims(aspect, width, height, img_cfg)

    # Hires workflows generate at a smaller base size and upscale within the
    # graph (LatentUpscaleBy). base_scale > 1 means EmptyLatentImage is set to
    # target / scale, and the workflow's upscale node recovers target res.
    base_scale = float(defaults.get("base_scale", 1.0))
    base_w = round(gen_w / base_scale / 8) * 8 if base_scale > 1.0 else gen_w
    base_h = round(gen_h / base_scale / 8) * 8 if base_scale > 1.0 else gen_h

    clip_nodes = sampler_nodes = 0
    for node in graph.values():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "CLIPTextEncode":
            clip_nodes += 1
            # fix 3: every text node gets fresh text. Positive vs negative is
            # decided by which KSampler socket points at it, resolved below.
        elif ct == "KSampler":
            sampler_nodes += 1
            inputs["seed"] = seed
            inputs["steps"] = steps
            inputs["cfg"] = float(engine.get("cfg") or img_cfg.get("cfg", 7.0))
            inputs["sampler_name"] = engine.get("sampler_name") or img_cfg.get("sampler", "dpmpp_2m")
            inputs["scheduler"] = engine.get("scheduler") or img_cfg.get("scheduler", "karras")
        elif ct == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = checkpoint          # fix 4 source of truth
        elif ct == "EmptyLatentImage":
            inputs["width"] = base_w
            inputs["height"] = base_h
            inputs["batch_size"] = batch
        elif ct == "SaveImage":
            inputs["filename_prefix"] = prefix

    # Wire positive/negative from the sampler's own sockets so renamed node ids
    # can't silently leave a CLIPTextEncode stale.
    injected = set()
    for node in graph.values():
        if node.get("class_type") != "KSampler":
            continue
        for socket, text in (("positive", prompt), ("negative", negative)):
            ref = node["inputs"].get(socket)
            if not (isinstance(ref, list) and ref):
                die(f"KSampler {socket} socket is not wired to a node")
            target = graph.get(str(ref[0]))
            if not target or target.get("class_type") != "CLIPTextEncode":
                die(f"KSampler {socket} does not point at a CLIPTextEncode node")
            target["inputs"]["text"] = text
            injected.add(str(ref[0]))
    if clip_nodes != len(injected):
        die(f"{clip_nodes} CLIPTextEncode nodes but only {len(injected)} reachable "
            f"from samplers — orphan text node would go stale, aborting")
    if sampler_nodes == 0:
        die("workflow has no KSampler node")

    if lora:
        insert_lora(
            graph,
            resolve_lora(root, lora),
            lora_strength,
            clip_strength=lora_clip_strength,
        )
        clip_note = lora_strength if lora_clip_strength is None else lora_clip_strength
        print(f"[byrdimage] LoRA attached: {lora} @ model {lora_strength}, CLIP {clip_note}")

    if reference and not dry_run:
        ref_name = upload_image(comfy, Path(reference))
        wired = False
        for node in graph.values():
            if node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = ref_name
                wired = True
        if not wired:
            die("reference given but the workflow has no LoadImage node")
        print(f"[byrdimage] reference wired: {Path(reference).name} -> IP-Adapter")

    print(f"[byrdimage] job {job_id}  recipe {recipe_tag}  seed {seed}  {gen_w}x{gen_h}")
    print(f"[byrdimage] prompt: {prompt}")
    print(f"[byrdimage] vary picks: {vary_picks or '(none)'}")
    if dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return job_id, []

    # ── Submit + poll ─────────────────────────────────────────────────────────
    card_base = {
        "recipe": recipe_tag, "purpose": purpose, "prompt": prompt,
        "negative": negative, "seed": seed, "checkpoint": checkpoint,
        "workflow": workflow_rel, "slots": user_slots, "vary_picks": vary_picks,
        "size": f"{gen_w}x{gen_h}",
        "steps": steps,
        "cfg": float(engine.get("cfg") or img_cfg.get("cfg", 7.0)),
        "sampler": engine.get("sampler_name") or img_cfg.get("sampler", "dpmpp_2m"),
        "scheduler": engine.get("scheduler") or img_cfg.get("scheduler", "karras"),
        **({"lora": lora, "lora_model_strength": lora_strength,
            "lora_clip_strength": (lora_strength if lora_clip_strength is None else lora_clip_strength)}
           if lora else {}),
        **({"reference": str(reference)} if reference else {}),
        **({"subject_profile": recipe.get("subject_profile")} if recipe.get("subject_profile") else {}),
        **({"category": recipe.get("category")} if recipe.get("category") else {}),
        **({"checkpoint_requested": ckpt_requested, "checkpoint_fallback": True}
           if not ckpt_matched else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def _named_node(graph: dict, class_type: str, title: str) -> tuple[str, dict]:
    """Find one intentionally titled API node and fail rather than guess.

    Target-edit graphs have two LoadImage inputs in the UI version over time, so
    matching by class alone would eventually upload the target into the wrong
    socket. The compact graph keeps titles as a stable adapter contract.
    """
    matches = [(node_id, node) for node_id, node in graph.items()
               if node.get("class_type") == class_type
               and str(node.get("_meta", {}).get("title", "")).strip() == title]
    if len(matches) != 1:
        die(f"expected one {class_type} titled '{title}', found {len(matches)}")
    return matches[0]


def _target_size(path: Path) -> tuple[int, int]:
    """Read a target image's pixels for 8-pixel VAE-safe normalization.

    Pillow is already a ByrdHouse dependency for thumbnail composition. Import
    it here so the normal generate path remains stdlib-only at import time.
    """
    try:
        from PIL import Image
        with Image.open(path) as image:
            return image.size
    except Exception as exc:
        die(f"could not read target image '{path}': {exc}")


def _render_recipe_prompt(recipe: dict, slots: dict) -> tuple[str, dict]:
    """Fill a recipe exactly as generate() does, including deterministic cards."""
    slots = dict(slots or {})
    vary_picks = {}
    for key, options in recipe.get("vary", {}).items():
        if not options:
            die(f"recipe vary slot '{key}' has no options to pick from")
        if not str(slots.get(key, "")).strip():
            vary_picks[key] = random.choice(options)
    slots.update(vary_picks)
    template = recipe.get("template", "")
    missing = [key for key in re.findall(r"\{(\w+)\}", template) if key not in slots]
    if missing:
        die(f"unfilled slots {missing} — pass the requested value before generating")
    return re.sub(r"\s+", " ", template.format(**slots)).strip(), vary_picks


def edit_target_identity(root, recipe_name, target_path, project, purpose,
                         slots=None, checkpoint=None, identity_lora=None,
                         identity_strength=None, target_preset=None,
                         target_mask=None, subject_profile=None, seed=None,
                         engine=None, job_id=None, allow_unconditioned=False):
    """Run the compact SD1.5 anime target-edit lane.

    This is deliberately not a raw face swap. It keeps the supplied target's
    pose/outfit/background in latent space and samples only a feathered face
    rectangle. A user-owned identity LoRA supplies likeness; without it, public
    belt jobs fail loudly rather than silently returning a generic anime face.
    """
    root = Path(root).resolve()
    target = _require_original_target(root, Path(target_path))
    if not target.is_file():
        die(f"target image not found: {target}")
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    recipe = load_json(find_recipe(root, recipe_name))
    if recipe.get("runner") != "target_identity_edit":
        die(f"recipe '{recipe.get('id', recipe_name)}' is not a target identity-edit recipe")

    identity = dict(recipe.get("identity") or {})
    trigger = str(identity.get("trigger") or "").strip()
    rendered_slots = dict(slots or {})
    if trigger:
        rendered_slots.setdefault("identity_token", trigger)
    prompt, vary_picks = _render_recipe_prompt(recipe, rendered_slots)
    negative = recipe.get("negative", "")

    presets = recipe.get("target_presets") or {}
    preset = dict(presets.get(target_preset) or {}) if target_preset else {}
    if target_preset and not preset:
        die(f"unknown target preset '{target_preset}' for recipe '{recipe.get('id')}'")
    context = str(preset.get("prompt_context") or "").strip()
    if context:
        prompt = f"{prompt}, {context}"
    mask_spec = dict(preset.get("mask") or recipe.get("mask") or {})
    if target_mask:
        mask_spec.update(target_mask)
    for key in ("x", "y", "width", "height"):
        if key not in mask_spec:
            die(f"target identity-edit recipe needs mask.{key}")

    engine = dict(engine or {})
    defaults = dict(recipe.get("defaults") or {})
    draft_cfg = dict(recipe.get("draft") or {})
    draft = bool(engine.get("draft", False))
    run_cfg = draft_cfg if draft else defaults
    checkpoint_requested = (checkpoint or engine.get("checkpoint") or
                            defaults.get("checkpoint") or die("no compact checkpoint configured"))
    checkpoint_name, checkpoint_matched = resolve_checkpoint_info(root, checkpoint_requested, comfy=comfy)
    if not checkpoint_matched:
        die(f"compact anime lane requires '{checkpoint_requested}', not fallback '{checkpoint_name}'")

    # ``None`` means use the recipe's deployed identity LoRA. An explicit empty
    # string is reserved for a local, unconditioned smoke test of the graph.
    selected_identity_lora = identity.get("lora") if identity_lora is None else identity_lora
    if not selected_identity_lora and not allow_unconditioned:
        die("identity LoRA is not installed/configured; refusing a generic face result")
    if selected_identity_lora:
        selected_identity_lora = resolve_lora(root, selected_identity_lora)
    if draft:
        speed_lora = resolve_lora(root, draft_cfg.get("lora") or die("draft LoRA is not configured"))
    else:
        speed_lora = None

    graph = load_json(root / recipe.get("workflow", "workflows/sd15_anime_target_identity_api.json"))
    graph.pop("_comment", None)
    _, target_node = _named_node(graph, "LoadImage", "TARGET IMAGE")
    _, scale_node = _named_node(graph, "ImageScale", "NORMALIZE TARGET")
    _, canvas_mask = _named_node(graph, "SolidMask", "CANVAS MASK")
    _, face_mask = _named_node(graph, "SolidMask", "FACE MASK")
    _, feather_mask = _named_node(graph, "FeatherMask", "FEATHER FACE MASK")
    _, composite_mask = _named_node(graph, "MaskComposite", "PLACE FACE MASK")

    original_w, original_h = _target_size(target)
    max_side = int(defaults.get("max_target_side", 768))
    scale = min(1.0, max_side / max(original_w, original_h))
    width = max(8, round(original_w * scale / 8) * 8)
    height = max(8, round(original_h * scale / 8) * 8)
    x_ratio, y_ratio = width / original_w, height / original_h
    face_x = max(0, min(width - 1, round(float(mask_spec["x"]) * x_ratio)))
    face_y = max(0, min(height - 1, round(float(mask_spec["y"]) * y_ratio)))
    face_w = max(8, min(width - face_x, round(float(mask_spec["width"]) * x_ratio)))
    face_h = max(8, min(height - face_y, round(float(mask_spec["height"]) * y_ratio)))
    feather = max(0, int(round(float(mask_spec.get("feather", 24)) * min(x_ratio, y_ratio))))

    target_node["inputs"]["image"] = upload_image(comfy, target)
    scale_node["inputs"].update({"width": width, "height": height, "crop": "disabled"})
    canvas_mask["inputs"].update({"width": width, "height": height})
    face_mask["inputs"].update({"width": face_w, "height": face_h})
    feather_mask["inputs"].update({"left": feather, "top": feather,
                                   "right": feather, "bottom": feather})
    composite_mask["inputs"].update({"x": face_x, "y": face_y})

    steps = int(engine.get("steps") or run_cfg.get("steps", 18))
    sample_cfg = float(engine.get("cfg") or run_cfg.get("cfg", 6.0))
    sampler = engine.get("sampler_name") or run_cfg.get("sampler", "dpmpp_2m")
    scheduler = engine.get("scheduler") or run_cfg.get("scheduler", "karras")
    denoise = float(engine.get("denoise") or defaults.get("denoise", 0.48))
    resolved_job_id = job_id or new_id("job")
    run_seed = int(seed) if seed is not None else secrets.randbits(63)
    for node in graph.values():
        class_type, inputs = node.get("class_type"), node.get("inputs", {})
        if class_type == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = checkpoint_name
        elif class_type == "KSampler":
            inputs.update({"seed": run_seed,
                           "steps": steps, "cfg": sample_cfg, "sampler_name": sampler,
                           "scheduler": scheduler, "denoise": denoise})
        elif class_type == "SaveImage":
            inputs["filename_prefix"] = f"{datetime.now():%Y%m%d}_{recipe['id']}_{resolved_job_id}"

    injected = set()
    for node in graph.values():
        if node.get("class_type") != "KSampler":
            continue
        for socket, text in (("positive", prompt), ("negative", negative)):
            ref = node["inputs"].get(socket)
            target_text = graph.get(str(ref[0])) if isinstance(ref, list) and ref else None
            if not target_text or target_text.get("class_type") != "CLIPTextEncode":
                die(f"target-edit KSampler {socket} does not point to CLIPTextEncode")
            target_text["inputs"]["text"] = text
            injected.add(str(ref[0]))
    clip_nodes = [node_id for node_id, node in graph.items()
                  if node.get("class_type") == "CLIPTextEncode"]
    if set(clip_nodes) != injected:
        die("target-edit workflow has an unreachable CLIPTextEncode node")

    lora_source = None
    identity_clip_weight = None
    if selected_identity_lora:
        identity_weight = float(identity_strength or engine.get("identity_strength") or
                                identity.get("strength", 0.8))
        identity_clip_weight = float(engine.get("identity_clip_strength") or
                                     identity.get("clip_strength") or identity_weight)
        insert_lora(graph, selected_identity_lora, identity_weight,
                    lora_id="byrd_identity_lora", clip_strength=identity_clip_weight)
        lora_source = "byrd_identity_lora"
    if speed_lora:
        insert_lora(graph, speed_lora, float(draft_cfg.get("strength", 1.0)),
                    lora_id="byrd_speed_lora", source_id=lora_source)

    card_base = {
        "recipe": f"{recipe['id']}@{recipe['version']}", "purpose": purpose,
        "prompt": prompt, "negative": negative, "checkpoint": checkpoint_name,
        "workflow": recipe.get("workflow", "workflows/sd15_anime_target_identity_api.json"),
        "slots": dict(slots or {}), "vary_picks": vary_picks, "seed": run_seed,
        "size": f"{width}x{height}", "steps": steps, "cfg": sample_cfg,
        "sampler": sampler, "scheduler": scheduler, "denoise": denoise,
        "target": str(target), "target_preset": target_preset,
        "target_sha256": _file_sha256(target),
        "retry_policy": "fresh-from-immutable-original; no generated parent",
        "generated_parent": None,
        "target_original_size": f"{original_w}x{original_h}",
        "target_mask": {"x": face_x, "y": face_y, "width": face_w,
                        "height": face_h, "feather": feather},
        "engine": "anime_sd15_compact",
        "identity_mode": "lora" if selected_identity_lora else "unconditioned_smoke",
        **({"identity_model_strength": identity_weight,
            "identity_clip_strength": identity_clip_weight}
           if selected_identity_lora else {}),
        **({"lora": selected_identity_lora} if selected_identity_lora else {}),
        **({"speed_lora": speed_lora} if speed_lora else {}),
        **({"subject_profile": subject_profile} if subject_profile else {}),
    }
    return resolved_job_id, run_graph(root, comfy, graph, resolved_job_id, project, card_base)


def _resolve_face_zone_gpu_passes(engine: dict, defaults: dict, run_seed: int) -> dict[str, dict]:
    """Resolve one to four named, masked GPU cleanup passes for a face zone."""
    default_steps = int(engine.get("steps") or defaults.get("steps", 24))
    default_cfg = float(engine.get("cfg") or defaults.get("cfg", 5.0))
    default_sampler = engine.get("sampler_name") or defaults.get("sampler", "dpmpp_2m")
    default_scheduler = engine.get("scheduler") or defaults.get("scheduler", "karras")
    default_denoise = float(engine.get("denoise") or defaults.get("denoise", 0.38))
    default_passes = defaults.get("gpu_passes")
    requested = engine.get("gpu_passes")
    if requested is None:
        requested = default_passes
    elif isinstance(requested, dict) and isinstance(default_passes, dict):
        merged = {}
        for default_pass_id, default_pass in default_passes.items():
            override = requested.get(default_pass_id)
            if override is None:
                merged[default_pass_id] = dict(default_pass)
            elif isinstance(default_pass, dict) and isinstance(override, dict):
                merged[default_pass_id] = {**default_pass, **override}
            else:
                die(f"face-zone GPU pass '{default_pass_id}' override must be an object")
        for pass_id, override in requested.items():
            if pass_id not in merged:
                merged[pass_id] = override
        requested = merged
    if requested is None:
        requested = {"default": {}}
    if isinstance(requested, list):
        requested = {f"pass_{index + 1}": value for index, value in enumerate(requested)}
    if not isinstance(requested, dict) or not 1 <= len(requested) <= 4:
        die("face-zone gpu_passes must be a map of one to four named pass objects")

    resolved = {}
    for index, (raw_id, requested_pass) in enumerate(requested.items()):
        pass_id = str(raw_id).strip()
        if not pass_id or not isinstance(requested_pass, dict):
            die("each face-zone GPU pass needs a non-empty name and an object value")
        steps = int(requested_pass.get("steps", default_steps))
        cfg = float(requested_pass.get("cfg", default_cfg))
        denoise = float(requested_pass.get("denoise", default_denoise))
        sampler = requested_pass.get("sampler_name") or requested_pass.get("sampler") or default_sampler
        scheduler = requested_pass.get("scheduler") or default_scheduler
        if not 2 <= steps <= 60:
            die(f"face-zone GPU pass '{pass_id}' steps must be between 2 and 60")
        if not 1.0 <= cfg <= 20.0:
            die(f"face-zone GPU pass '{pass_id}' cfg must be between 1 and 20")
        if not 0.0 < denoise <= 1.0:
            die(f"face-zone GPU pass '{pass_id}' denoise must be in (0, 1]")
        seed_offset = int(requested_pass.get("seed_offset", index))
        resolved[pass_id] = {
            "id": pass_id,
            "seed": int(requested_pass.get("seed", run_seed + seed_offset)),
            "steps": steps,
            "cfg": cfg,
            "sampler_name": str(sampler),
            "scheduler": str(scheduler),
            "denoise": denoise,
        }
    return resolved
def _face_report(root, comfy_python, zone_script, target, min_confidence=0.35,
                 thorough=True):
    """Run the CPU examiner (byrdfacezone analyze) and gate on its verdict.
    Returns the parsed report dict; dies with the examiner's own reasons when
    the image has no operable face — the belt never guesses where to edit.
    thorough is the founder default: real scrutiny (scale-stability, occlusion
    truth, lane recommendation) is spent BEFORE any GPU effort."""
    cmd = [str(comfy_python), str(zone_script), "--root", str(root), "analyze",
           "--input", str(target), "--min-confidence", str(min_confidence)]
    if thorough:
        cmd.append("--thorough")
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode == 3:
        try:
            report = json.loads(result.stdout)
            reason = report.get("reason") or "no operable face"
            flags = [f for face in report.get("faces", []) for f in face.get("flags", [])]
        except Exception:
            reason, flags = "no operable face", []
        die("face report: cannot operate on this image — " + reason
            + (f" (flags: {'; '.join(flags)})" if flags else ""))
    if result.returncode != 0:
        die(f"face examiner failed: {(result.stderr or result.stdout).strip()[-500:]}")
    try:
        return json.loads(result.stdout)
    except Exception:
        die("face examiner returned unreadable output")


def facezone_examine(root, target_path, project, purpose, min_confidence=0.35,
                     thorough=True, job_id=None):
    """Standalone examiner job (route 'examine'): run the CPU face report on an
    upload and archive the clean overview + the JSON verdict as an artifact —
    no editing, any GPU mode. This is how the founder sees where the belt can
    and can't operate BEFORE spending anything."""
    root = Path(root)
    target = Path(target_path)
    if not target.exists():
        die(f"examine target not found: {target}")
    comfy_python = root / "Generators" / "ComfyUI" / ".venv" / "Scripts" / "python.exe"
    zone_script = root / "scripts" / "byrdfacezone.py"
    job_id = job_id or new_id("job")
    month_dir = root / "artifacts" / project / f"{datetime.now():%Y-%m}"
    month_dir.mkdir(parents=True, exist_ok=True)
    overview = month_dir / f"{datetime.now():%Y%m%d}_face_report_{job_id}.png"
    report_path = overview.with_suffix(".json.txt")  # .png.json is the card's name
    cmd = [str(comfy_python), str(zone_script), "--root", str(root), "analyze",
           "--input", str(target), "--min-confidence", str(min_confidence),
           "--report", str(report_path), "--overview", str(overview)]
    if thorough:
        cmd.append("--thorough")
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode not in (0, 3):
        die(f"face examiner failed: {(result.stderr or result.stdout).strip()[-500:]}")
    try:
        report = json.loads(result.stdout)
    except Exception:
        die("face examiner returned unreadable output")
    card = {
        "artifact_id": f"art.{job_id}.0", "job_id": job_id, "project": project,
        "kind": "image", "recipe": "face_report@1", "purpose": purpose,
        "prompt": "", "negative": "", "seed": None,
        "workflow": "byrdfacezone analyze (CPU examiner)",
        "slots": {}, "vary_picks": {},
        "swap_target": str(target),
        "face_report": report,
        "report_file": str(report_path),
        "score": None, "tags": ["face-report", report.get("verdict", "unknown")],
        "caption": f"{report.get('operable_faces', 0)} operable face(s); "
                   f"verdict {report.get('verdict')}",
        "status": "draft", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    overview.with_suffix(overview.suffix + ".json").write_text(
        json.dumps(card, indent=2), encoding="utf-8")
    print(f"[byrdimage] face report: {report.get('verdict')} "
          f"({report.get('operable_faces', 0)} operable) -> {overview}")
    return job_id, [(overview, card)]


def edit_face_zone(root, recipe_name, target_path, project, purpose,
                   slots=None, checkpoint=None, identity_lora=None,
                   identity_strength=None, target_preset=None,
                   subject_profile=None, seed=None, engine=None, job_id=None):
    """CPU face outline -> 512px graded inpaint -> exact soft-zone composite.

    This is the default architecture for uploaded face edits.  It keeps face
    detection/mesh work on CPU, gives the GPU a face-sized crop, and restores
    the uploaded source outside the saved skin-match ring pixel-for-pixel.
    """
    root = Path(root).resolve()
    target = _require_original_target(root, Path(target_path))
    if not target.is_file():
        die(f"target image not found: {target}")
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    recipe = load_json(find_recipe(root, recipe_name))
    if recipe.get("runner") != "face_zone_identity_edit":
        die(f"recipe '{recipe.get('id', recipe_name)}' is not a face-zone identity-edit recipe")

    identity = dict(recipe.get("identity") or {})
    try:
        selected_identity_lora, lora_status = select_identity_lora(root, identity, identity_lora)
    except ValueError as exc:
        die(str(exc))

    prompt, vary_picks = _render_recipe_prompt(recipe, dict(slots or {}))
    preset_key = target_preset or "auto"
    target_presets = dict(recipe.get("target_presets") or {})
    if preset_key not in target_presets:
        die(f"unknown face-zone target preset '{preset_key}'")
    preset = dict(target_presets[preset_key] or {})
    context = str(preset.get("prompt_context") or "").strip()
    if context:
        prompt = f"{prompt}, {context}"
    negative = recipe.get("negative", "")
    defaults = dict(recipe.get("defaults") or {})
    engine = dict(engine or {})
    resolved_job_id = job_id or new_id("job")
    run_seed = int(seed) if seed is not None else secrets.randbits(63)
    identity_reference = engine.get("identity_reference")
    if not identity_reference:
        identity_references = dict(recipe.get("identity_references") or {})
        identity_reference = identity_references.get(preset_key) or identity_references.get("auto")
    identity_reference_path = None
    if identity_reference:
        identity_reference_path = Path(identity_reference)
        if not identity_reference_path.is_absolute():
            identity_reference_path = root / identity_reference_path
        if not identity_reference_path.is_file():
            die(f"identity mesh reference not found: {identity_reference_path}")

    # Founder rule: extra avenues ride as PARAMETERS, never as new defaults —
    # a job may pick any staged face-zone graph (diffdiff, ipadapter, controlnet)
    # while the recipe's proven default stays the recipe's default.
    workflow_rel = (engine or {}).get("workflow") or recipe.get(
        "workflow", "workflows/sd15_face_zone_inpaint_api.json")
    if (engine or {}).get("workflow") and not (root / workflow_rel).is_file():
        die(f"engine.workflow does not exist: {workflow_rel}")
    if "mesh_seed" in workflow_rel and identity_reference_path is None:
        die("face-zone mesh workflow requires a reviewed identity reference; refusing generic inpaint fallback")

    # This command is deliberately separate from ComfyUI: face outlining uses
    # CPU PyTorch even while the image server remains on the RTX 3070.
    comfy_python = root / "Generators" / "ComfyUI" / ".venv" / "Scripts" / "python.exe"
    zone_script = root / "scripts" / "byrdfacezone.py"

    # Founder contract: FIRST understand where the belt can and can't operate
    # on THIS image. The examiner reports every face, its verdict, risk flags
    # (extreme expression, strong profile, too small) and the per-feature
    # likeness plan; a refuse verdict stops the job before any zone/GPU work,
    # and the report rides the card so every edit is explainable.
    face_report = _face_report(root, comfy_python, zone_script, target,
                               engine.get("min_face_confidence",
                                          defaults.get("min_face_confidence", 0.35)),
                               thorough=not engine.get("quick_report", False))

    # Repair A (2026-07-16, hard Vegeta): fail-closed geometry gate. Unstable
    # geometry (low stability, cross-scale landmark disagreement, strong
    # profile without solid stability) may never be treated as a normal mesh
    # case and may never ship a CPU-only warp — route to the reviewed-mask
    # path or refuse with the exact reason. The decision rides the card.
    gate = geometry_gate(face_report, int(engine.get("face_index", 0)),
                         float(engine.get("gate_stability_threshold", 0.35)))
    if identity_reference_path is not None and not gate["mesh_case_allowed"]:
        die("geometry gate: this target may not use the mesh-warp lane — "
            + "; ".join(gate["reasons"])
            + f". Use the reviewed-mask fallback instead: {gate['fallback']}")

    # Flow fix (founder, 2026-07-15): work at the face's native detail. The
    # examiner already measured every face — pick the crop canvas from the
    # operated face's size instead of forcing 512 (large faces were being
    # downscaled into softness on the way in and stretched back on composite).
    canvas = int(engine.get("crop_size", 0) or 0)
    if canvas not in (512, 640, 768):
        face_entries = {f.get("index"): f for f in face_report.get("faces", [])}
        side_px = float(face_entries.get(int(engine.get("face_index", 0)), {}).get("side_px", 0))
        canvas = 512 if side_px < 420 else 640 if side_px < 560 else 768

    zone_cmd = [
        str(comfy_python), str(zone_script), "--root", str(root), "prepare",
        "--input", str(target), "--job-id", resolved_job_id,
        "--min-confidence", str(engine.get("min_face_confidence", defaults.get("min_face_confidence", 0.35))),
        "--crop-factor", str(engine.get("crop_factor", defaults.get("crop_factor", 1.65))),
        "--face-index", str(int(engine.get("face_index", 0))),
        "--zone-expand", str(engine.get("zone_expand", defaults.get("zone_expand", 1.10))),
        "--canvas-size", str(canvas),
    ]
    if identity_reference_path is not None:
        zone_cmd += ["--identity-reference", str(identity_reference_path)]
        mesh_identity_strength = engine.get("mesh_identity_strength")
        if mesh_identity_strength is None:
            mesh_identity_strength = preset.get("mesh_identity_strength")
        if mesh_identity_strength is not None:
            zone_cmd += ["--mesh-identity-strength", str(mesh_identity_strength)]
        eye_protection = engine.get("eye_protection")
        if eye_protection is None:
            eye_protection = preset.get("eye_protection")
        if eye_protection is not None:
            zone_cmd += ["--eye-protection", str(eye_protection)]
        eye_source = engine.get("eye_source") or preset.get("eye_source")
        if eye_source:
            zone_cmd += ["--eye-source", str(eye_source)]
    manual = engine.get("manual_face_box") or preset.get("manual_face_box")
    if manual:
        if isinstance(manual, dict):
            manual = ",".join(str(manual[key]) for key in ("x", "y", "width", "height"))
        zone_cmd += ["--manual-box", str(manual)]
    for box in preset.get("exclude_boxes", []):
        if isinstance(box, dict):
            box = ",".join(str(box[key]) for key in ("x", "y", "width", "height"))
        zone_cmd += ["--exclude-box", str(box)]
    for accessory in preset.get("absent_accessories", []):
        zone_cmd += ["--absent-accessory", str(accessory)]
    prepared = subprocess.run(zone_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if prepared.returncode != 0:
        die(f"CPU face outline failed: {(prepared.stderr or prepared.stdout).strip()[-800:]}")
    try:
        zone = json.loads(prepared.stdout)
    except json.JSONDecodeError as exc:
        die(f"CPU face outline returned invalid JSON: {exc}")

    upload_analysis = dict(zone.get("upload_analysis") or {})
    crop_preflight = dict(zone.get("crop_preflight") or {})
    if identity_reference_path is not None and int(recipe.get("version", 1)) >= 2:
        expected_upload_stages = [
            "face-detection-and-478-point-mesh",
            "neck-anchor",
            "neck-left-to-top-to-right-to-neck-closed-loop",
            "whole-face-head-and-ears",
            "hair-headwear-accessory-and-clothing-classification",
            "visible-eyes-mouth-and-identity-pose-map",
            "target-theme-overlay-ready",
        ]
        actual_upload_stages = list(upload_analysis.get("ordered_pipeline") or [])
        failed_upload_stages = [
            str(stage.get("id") or "unknown")
            for stage in upload_analysis.get("stages") or []
            if not stage.get("passed")
        ]
        if (
            upload_analysis.get("version") != 1
            or actual_upload_stages != expected_upload_stages
            or not upload_analysis.get("all_passed")
            or failed_upload_stages
        ):
            detail = ", ".join(failed_upload_stages) or "missing or out-of-order analysis"
            die(
                "CPU upload analysis did not pass every ordered body-part stage "
                f"({detail}); refusing GPU work"
            )
        if (
            crop_preflight.get("passed") is False
            or crop_preflight.get("expandable_contacts")
        ):
            contacts = ", ".join(crop_preflight.get("expandable_contacts") or []) or "unknown"
            die(
                "CPU crop preflight did not contain the full head/neck before GPU work "
                f"({contacts}); refusing GPU work"
            )

    requested_minimum_coverage = engine.get("min_mesh_coverage")
    if requested_minimum_coverage is None:
        requested_minimum_coverage = defaults.get("min_mesh_coverage", 0.0)
    try:
        minimum_mesh_coverage = float(requested_minimum_coverage)
    except (TypeError, ValueError):
        die("min_mesh_coverage must be a number between 0 and 1")
    if not 0.0 <= minimum_mesh_coverage <= 1.0:
        die("min_mesh_coverage must be a number between 0 and 1")
    mesh_coverage = None
    whole_zone_mesh_coverage = None
    if identity_reference_path is not None:
        identity_mesh = zone.get("identity_mesh") or {}
        try:
            whole_zone_mesh_coverage = float(identity_mesh["coverage_ratio"])
            mesh_coverage = float(identity_mesh.get("core_coverage_ratio", whole_zone_mesh_coverage))
        except (KeyError, TypeError, ValueError):
            die("CPU face outline returned no valid identity-mesh coverage; refusing GPU cleanup")
        if not math.isfinite(mesh_coverage):
            die("CPU face outline returned non-finite identity-mesh coverage; refusing GPU cleanup")
        if minimum_mesh_coverage > 0.0 and mesh_coverage < minimum_mesh_coverage:
            die(
                f"identity mesh coverage {mesh_coverage:.1%} is below the "
                f"required {minimum_mesh_coverage:.1%}; refusing GPU cleanup"
            )

    checkpoint_requested = checkpoint or engine.get("checkpoint") or defaults.get("checkpoint")
    checkpoint_name, checkpoint_matched = resolve_checkpoint_info(root, checkpoint_requested, comfy=comfy)
    if not checkpoint_matched:
        die(f"face-zone lane requires '{checkpoint_requested}', not fallback '{checkpoint_name}'")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)
    # Repair E (2026-07-16): a graph that needs an uninstalled model refuses
    # HERE with the model's name, instead of dying later as a bare HTTP 400.
    try:
        require_workflow_models(root, graph, workflow_rel)
    except ValueError as exc:
        die(str(exc))
    crop_title = "IDENTITY MESH SEED" if identity_reference_path is not None else "FACE CROP"
    _, crop_node = _named_node(graph, "LoadImage", crop_title)
    _, mask_node = _named_node(graph, "LoadImage", "EDIT ZONE MASK")
    crop_artifact = (
        zone["artifacts"]["identity_mesh_seed"]
        if identity_reference_path is not None
        else zone["artifacts"]["face_crop"]
    )
    crop_node["inputs"]["image"] = upload_image(comfy, Path(crop_artifact))
    mask_node["inputs"]["image"] = upload_image(comfy, Path(zone["artifacts"]["graded_mask"]))
    edge_mask_node = next(
        (
            node for node in graph.values()
            if node.get("class_type") == "LoadImage"
            and node.get("_meta", {}).get("title") == "EDGE HARMONIZE MASK"
        ),
        None,
    )
    if edge_mask_node is not None:
        edge_mask_artifact = zone["artifacts"].get("skin_match_ring")
        if not edge_mask_artifact:
            die("face-zone workflow requires a saved skin-match ring")
        edge_mask_node["inputs"]["image"] = upload_image(comfy, Path(edge_mask_artifact))
    identity_photo_node = next(
        (
            node for node in graph.values()
            if node.get("class_type") == "LoadImage"
            and node.get("_meta", {}).get("title") == "IDENTITY PHOTO"
        ),
        None,
    )
    if identity_photo_node is not None:
        # the IP-Adapter avenue anchors identity to a REAL photo embedding —
        # prefer an explicit engine.identity_photo, fall back to the reviewed
        # identity reference; never run the avenue without an anchor image
        identity_photo = engine.get("identity_photo") or (
            str(identity_reference_path) if identity_reference_path else None)
        if not identity_photo or not Path(identity_photo).is_file():
            die("this face-zone workflow needs an identity photo: pass "
                "engine.identity_photo (a real photo of the founder) or use a "
                "preset with a reviewed identity reference")
        identity_photo_node["inputs"]["image"] = upload_image(comfy, Path(identity_photo))

    identity_model_weight = float(
        identity_strength or engine.get("identity_strength") or identity.get("strength", 1.0)
    )
    identity_clip_weight = float(
        engine.get("identity_clip_strength") or identity.get("clip_strength") or identity_model_weight
    )
    gpu_passes = _resolve_face_zone_gpu_passes(engine, defaults, run_seed)
    skip_gpu_cleanup = bool(
        engine.get("skip_gpu_cleanup")
        if "skip_gpu_cleanup" in engine
        else defaults.get("skip_gpu_cleanup", False)
    )
    if skip_gpu_cleanup:
        zone_dir = Path(zone["zone_file"]).parent
        generated_crop = Path(zone["artifacts"]["identity_mesh_seed"])
        month_dir = root / "artifacts" / project / f"{datetime.now():%Y-%m}"
        month_dir.mkdir(parents=True, exist_ok=True)
        final = month_dir / f"{datetime.now():%Y%m%d}_{recipe['id']}_{resolved_job_id}_00001_.png"
        composited = subprocess.run(
            [str(comfy_python), str(zone_script), "--root", str(root), "composite",
             "--zone", zone["zone_file"], "--generated-crop", str(generated_crop),
             "--output", str(final)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if composited.returncode != 0 or not final.is_file():
            die(f"CPU face-zone composite failed: {(composited.stderr or composited.stdout).strip()[-800:]}")
        zone_record = load_json(Path(zone["zone_file"]))
        zone_record["status"] = "CPU identity mesh seed used without GPU cleanup"
        zone_record["generated_crop"] = str(generated_crop)
        zone_record["final"] = str(final)
        Path(zone["zone_file"]).write_text(json.dumps(zone_record, indent=2) + "\n", encoding="utf-8")
        # Repair D (2026-07-16): a raw CPU triangle warp may be conditioning or
        # an intermediate, never a founder-facing final unless it PROVES smooth.
        # The composite wrote a verification card; the shard heuristic or the
        # geometry gate failing marks this artifact rejected — saved as
        # evidence, never published as a normal draft.
        verify_file = Path(str(final) + ".verify.json")
        composite_verification = load_json(verify_file) if verify_file.is_file() else {}
        shard = dict(composite_verification.get("shard_check") or {})
        cpu_publish_blockers = list(gate["reasons"]) if not gate["cpu_final_allowed"] else []
        if shard.get("shards_detected"):
            cpu_publish_blockers.append(
                "triangle-shard heuristic tripped on the CPU seed "
                f"(straight_edge_fraction {shard.get('straight_edge_fraction')}, "
                f"edge_density {shard.get('edge_density')}) — raw warp must not ship")
        cpu_status = "rejected" if cpu_publish_blockers else "draft"
        card = {
            "artifact_id": f"art.{resolved_job_id}.0",
            "job_id": resolved_job_id,
            "project": project,
            "kind": "image",
            "recipe": f"{recipe['id']}@{recipe['version']}",
            "purpose": purpose,
            "prompt": prompt,
            "negative": negative,
            "checkpoint": checkpoint_name,
            "workflow": workflow_rel,
            "seed": run_seed,
            "size": f"{_target_size(target)[0]}x{_target_size(target)[1]}",
            "steps": 0,
            "cfg": 0,
            "sampler": "cpu-only",
            "scheduler": "cpu-only",
            "denoise": 0,
            "target": str(target),
            "target_sha256": _file_sha256(target),
            "retry_policy": "fresh-from-immutable-original; no generated parent",
            "generated_parent": None,
            "target_preset": target_preset or "auto",
            "engine": "cpu_face_zone_sd15_seed_only",
            "gpu_passes": [],
            "identity_mode": "lora",
            "identity_model_strength": identity_model_weight,
            "identity_clip_strength": identity_clip_weight,
            "lora": selected_identity_lora,
            "lora_status": lora_status,
            "geometry_gate": gate,
            "composite_verification": composite_verification,
            "gate_failures": cpu_publish_blockers,
            "face_zone": zone_record,
            "upload_analysis": upload_analysis,
            "face_report": face_report,
            "crop_preflight": crop_preflight,
            **({"identity_reference": str(identity_reference_path)} if identity_reference_path else {}),
            **({"face_swap_preflight": {
                "identity_mesh_coverage": mesh_coverage,
                "facial_core_mesh_coverage": mesh_coverage,
                "whole_zone_mesh_coverage": whole_zone_mesh_coverage,
                "minimum_mesh_coverage": minimum_mesh_coverage,
                "passed": True,
            }} if identity_reference_path is not None else {}),
            "skin_match": "generated mean preserved; target contrast harmonized 35%; soft boundary ring composite",
            **({"subject_profile": subject_profile} if subject_profile else {}),
            "score": None,
            "tags": ["cpu-face-outline", "graded-mask", "skin-match", "cpu-only-seed"]
            + (["gate-blocked-cpu-final"] if cpu_publish_blockers else []),
            "caption": "",
            "status": cpu_status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        final.with_suffix(final.suffix + ".json").write_text(
            json.dumps(card, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[byrdimage] CPU face outline: {zone['artifacts']['outline_preview']}")
        print(f"[byrdimage] skin-match zone: {zone['artifacts']['skin_match_ring']}")
        if cpu_publish_blockers:
            print("[byrdimage] REJECTED (fail-closed, saved as evidence only):")
            for blocker in cpu_publish_blockers:
                print(f"[byrdimage]   - {blocker}")
        print(f"[byrdimage] archived {final} (+card, status={cpu_status})")
        return resolved_job_id, [(final, card)]
    sampler_nodes = []
    for node in graph.values():
        class_type, inputs = node.get("class_type"), node.get("inputs", {})
        if class_type == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = checkpoint_name
        elif class_type == "KSampler":
            sampler_nodes.append(node)
        elif class_type == "CLIPTextEncode":
            inputs["text"] = prompt if "POSITIVE" in node.get("_meta", {}).get("title", "") else negative
        elif class_type == "RepeatLatentBatch":
            # candidates per submit: encode once, sample N — clamp for the 8GB card
            inputs["amount"] = max(1, min(4, int(engine.get("batch", defaults.get("batch", 1)))))
        elif class_type == "SaveImage":
            inputs["filename_prefix"] = f"{datetime.now():%Y%m%d}_{recipe['id']}_{resolved_job_id}_crop"
    if len(sampler_nodes) != len(gpu_passes):
        die(
            f"face-zone workflow has {len(sampler_nodes)} KSampler nodes but "
            f"the recipe resolved {len(gpu_passes)} GPU passes"
        )
    assigned_passes = set()
    for sampler_node in sampler_nodes:
        pass_id = str(sampler_node.get("_meta", {}).get("byrd_pass", "")).strip()
        if not pass_id and len(sampler_nodes) == len(gpu_passes) == 1:
            pass_id = next(iter(gpu_passes))
        pass_config = gpu_passes.get(pass_id)
        if pass_config is None or pass_id in assigned_passes:
            die(f"face-zone workflow has an unconfigured or duplicate GPU pass '{pass_id}'")
        sampler_node["inputs"].update(pass_config)
        sampler_node["inputs"].pop("id", None)
        assigned_passes.add(pass_id)
    if assigned_passes != set(gpu_passes):
        die("face-zone workflow did not assign every configured GPU pass")
    pass_plan = list(gpu_passes.values())
    steps = sum(pass_config["steps"] for pass_config in pass_plan)
    sample_cfg = pass_plan[0]["cfg"]
    sampler = pass_plan[0]["sampler_name"]
    scheduler = pass_plan[0]["scheduler"]
    denoise = pass_plan[0]["denoise"]

    identity_model_weight = float(
        identity_strength or engine.get("identity_strength") or identity.get("strength", 1.0)
    )
    identity_clip_weight = float(
        engine.get("identity_clip_strength") or identity.get("clip_strength") or identity_model_weight
    )
    insert_lora(graph, selected_identity_lora, identity_model_weight,
                lora_id="byrd_identity_lora", clip_strength=identity_clip_weight)

    outputs = submit_and_wait(comfy, graph, resolved_job_id)
    zone_dir = Path(zone["zone_file"]).parent
    crop_images = [image for node_output in outputs.values()
                   for image in node_output.get("images", [])]
    if not crop_images:
        die("face-zone workflow returned no generated crop")

    month_dir = root / "artifacts" / project / f"{datetime.now():%Y-%m}"
    month_dir.mkdir(parents=True, exist_ok=True)
    zone_record = load_json(Path(zone["zone_file"]))
    zone_record["status"] = "GPU edit executed and skin-match composite completed"
    zone_record["candidates"] = len(crop_images)
    saved_candidates = []
    for crop_index, image in enumerate(crop_images):
        query = urllib.parse.urlencode({
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        })
        generated_crop = zone_dir / f"generated_face_crop_{crop_index:02d}.png"
        with urllib.request.urlopen(f"{comfy}/view?{query}", timeout=60) as response:
            generated_crop.write_bytes(response.read())
        final = month_dir / (f"{datetime.now():%Y%m%d}_{recipe['id']}_"
                             f"{resolved_job_id}_{crop_index + 1:05d}_.png")
        composited = subprocess.run(
            [str(comfy_python), str(zone_script), "--root", str(root), "composite",
             "--zone", zone["zone_file"], "--generated-crop", str(generated_crop),
             "--output", str(final)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if composited.returncode != 0 or not final.is_file():
            die(f"CPU face-zone composite failed: {(composited.stderr or composited.stdout).strip()[-800:]}")
        saved_candidates.append((generated_crop, final))
    zone_record["generated_crops"] = [str(c) for c, _ in saved_candidates]
    zone_record["finals"] = [str(f) for _, f in saved_candidates]
    Path(zone["zone_file"]).write_text(json.dumps(zone_record, indent=2) + "\n", encoding="utf-8")

    saved = []
    for crop_index, (generated_crop, final) in enumerate(saved_candidates):
        card = {
        "artifact_id": f"art.{resolved_job_id}.{crop_index}",
        "job_id": resolved_job_id,
        "project": project,
        "kind": "image",
        "recipe": f"{recipe['id']}@{recipe['version']}",
        "purpose": purpose,
        "prompt": prompt,
        "negative": negative,
        "checkpoint": checkpoint_name,
        "workflow": workflow_rel,
        "seed": run_seed,
        "size": f"{_target_size(target)[0]}x{_target_size(target)[1]}",
        "steps": steps,
        "cfg": sample_cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "denoise": denoise,
        "target": str(target),
        "target_sha256": _file_sha256(target),
        "retry_policy": "fresh-from-immutable-original; no generated parent",
        "generated_parent": None,
        "target_preset": target_preset or "auto",
        "engine": "cpu_face_zone_sd15_multipass" if len(gpu_passes) > 1 else "cpu_face_zone_sd15",
        "gpu_passes": list(gpu_passes.values()),
        "identity_mode": "lora",
        "identity_model_strength": identity_model_weight,
        "identity_clip_strength": identity_clip_weight,
        "lora": selected_identity_lora,
        "lora_status": lora_status,
        "geometry_gate": gate,
        "face_report": face_report,
        "face_zone": zone_record,
        "upload_analysis": upload_analysis,
        "crop_preflight": crop_preflight,
        **({"identity_reference": str(identity_reference_path)} if identity_reference_path else {}),
        **({"face_swap_preflight": {
            "identity_mesh_coverage": mesh_coverage,
            "facial_core_mesh_coverage": mesh_coverage,
            "whole_zone_mesh_coverage": whole_zone_mesh_coverage,
            "minimum_mesh_coverage": minimum_mesh_coverage,
            "passed": True,
        }} if identity_reference_path is not None else {}),
        "skin_match": "generated mean preserved; target contrast harmonized 35%; soft boundary ring composite",
        **({"subject_profile": subject_profile} if subject_profile else {}),
        "score": None,
        "tags": ["cpu-face-outline", "graded-mask", "skin-match"]
        + (["multi-pass-gpu-cleanup"] if len(gpu_passes) > 1 else []),
        "caption": "",
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
        card["candidate"] = crop_index + 1
        card["candidates"] = len(saved_candidates)
        card["canvas"] = canvas
        candidate_verify = Path(str(final) + ".verify.json")
        if candidate_verify.is_file():
            card["composite_verification"] = load_json(candidate_verify)
        final.with_suffix(final.suffix + ".json").write_text(
            json.dumps(card, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[byrdimage] archived {final} (+card)")
        saved.append((final, card))
    print(f"[byrdimage] CPU face outline: {zone['artifacts']['outline_preview']}")
    print(f"[byrdimage] skin-match zone: {zone['artifacts']['skin_match_ring']}")
    print(f"[byrdimage] face-zone candidates: {len(saved)} at canvas {canvas}px")
    return resolved_job_id, saved


def submit_and_wait(comfy: str, graph: dict, job_id: str) -> dict:
    resp = http_json(f"{comfy}/prompt", {"prompt": graph, "client_id": job_id})
    prompt_id = resp.get("prompt_id") or die(f"ComfyUI rejected the job: {resp}")
    print(f"[byrdimage] submitted, prompt_id {prompt_id} — waiting...")
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        hist = http_json(f"{comfy}/history/{prompt_id}", timeout=15)
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                die(f"ComfyUI job failed: {json.dumps(status)[:500]}")
            if entry.get("outputs"):
                return entry["outputs"]
        time.sleep(3)
    die("timed out after 15 min waiting for ComfyUI")


def run_graph(root: Path, comfy: str, graph: dict, job_id: str, project: str,
              card_base: dict):
    """Submit a graph, archive every output PNG with its metadata card
    (v2 §8: no artifact without a card). Shared by generate() and refine()."""
    outputs = submit_and_wait(comfy, graph, job_id)
    month_dir = root / "artifacts" / project / f"{datetime.now():%Y-%m}"
    month_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    saved = []
    for node_output in outputs.values():
        for img in node_output.get("images", []):
            q = urllib.parse.urlencode({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            })
            with urllib.request.urlopen(f"{comfy}/view?{q}", timeout=60) as r:
                data = r.read()
            dest = month_dir / img["filename"]
            dest.write_bytes(data)
            card = {
                # Deterministic per (job, output file): a retried job re-registers
                # the same card instead of minting a duplicate row.
                "artifact_id": f"art.{job_id}.{len(saved)}",
                "job_id": job_id,
                "project": project,
                "kind": "image",
                **card_base,
                "score": None, "tags": [], "caption": "",
                "status": "draft", "created_at": now_iso,
            }
            dest.with_suffix(dest.suffix + ".json").write_text(
                json.dumps(card, indent=2), encoding="utf-8")
            saved.append((dest, card))
            print(f"[byrdimage]   archived {dest} (+card)")

    if not saved:
        die("job finished but produced no images")
    print(f"[byrdimage] done — {len(saved)} image(s) in {month_dir}")
    return saved


def refine(root, source_path, project, purpose, prompt=None, negative=None,
           strength=0.4, scale=1.6, checkpoint=None, lora=None,
           lora_strength=0.9, batch=1, job_id=None):
    """img2img pass over an existing image: low strength = hi-res polish
    (upscale), higher strength = variations that stay 'near what's asked'.
    Prompt defaults to the source's own card so refinement keeps its intent."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})
    source = Path(source_path)
    if not source.exists():
        die(f"source image not found: {source}")

    src_card = {}
    card_path = source.with_suffix(source.suffix + ".json")
    if card_path.exists():
        src_card = load_json(card_path)
    prompt = prompt or src_card.get("prompt") or "high quality, sharp, detailed"
    negative = negative if negative is not None else src_card.get(
        "negative", "text, letters, watermark, blurry, low contrast")
    checkpoint = resolve_checkpoint(
        root, checkpoint or src_card.get("checkpoint") or "juggernautXL_v9", comfy=comfy)

    job_id = job_id or new_id("job")
    seed = secrets.randbits(63)
    prefix = f"{datetime.now():%Y%m%d}_refine_{job_id}"
    uploaded = upload_image(comfy, source)

    workflow_rel = "workflows/sdxl_img2img_api.json"
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)
    steps_used = 30
    for node in graph.values():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "LoadImage":
            inputs["image"] = uploaded
        elif ct == "LatentUpscaleBy":
            inputs["scale_by"] = float(scale)
        elif ct == "RepeatLatentBatch":
            inputs["amount"] = int(batch)
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["denoise"] = max(0.05, min(0.95, float(strength)))
            inputs["cfg"] = img_cfg.get("cfg", 7.0)
            inputs["sampler_name"] = img_cfg.get("sampler", "dpmpp_2m")
            inputs["scheduler"] = img_cfg.get("scheduler", "karras")
            steps_used = int(inputs.get("steps", 30))
        elif ct == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = checkpoint
        elif ct == "SaveImage":
            inputs["filename_prefix"] = prefix
    for node in graph.values():
        if node.get("class_type") != "KSampler":
            continue
        for socket, text in (("positive", prompt), ("negative", negative)):
            ref = node["inputs"].get(socket)
            target = graph.get(str(ref[0])) if isinstance(ref, list) and ref else None
            if not target or target.get("class_type") != "CLIPTextEncode":
                die(f"img2img KSampler {socket} not wired to CLIPTextEncode")
            target["inputs"]["text"] = text
    if lora:
        insert_lora(graph, resolve_lora(root, lora), lora_strength)

    # Record the resolution change so the dashboard can SHOW that an upscale did
    # something (a 1.5× on a gallery thumbnail is otherwise invisible) and so the
    # card honestly carries the pixels that ran.
    in_wh = _png_size(source)
    size_fields = {}
    if in_wh:
        size_fields["in_size"] = f"{in_wh[0]}x{in_wh[1]}"
        size_fields["out_size"] = f"{round(in_wh[0] * scale)}x{round(in_wh[1] * scale)}"
    print(f"[byrdimage] refine {source.name}  strength {strength}  scale {scale}"
          + (f"  {size_fields['in_size']} -> {size_fields['out_size']}" if size_fields else ""))
    card_base = {
        "recipe": src_card.get("recipe", "refine"), "purpose": purpose,
        "prompt": prompt, "negative": negative, "seed": seed,
        "checkpoint": checkpoint, "workflow": workflow_rel,
        "slots": src_card.get("slots", {}), "vary_picks": {},
        "refined_from": str(source), "strength": strength, "scale": scale,
        "steps": steps_used, "cfg": img_cfg.get("cfg", 7.0),
        "sampler": img_cfg.get("sampler", "dpmpp_2m"),
        "scheduler": img_cfg.get("scheduler", "karras"),
        **size_fields,
        **({"lora": lora} if lora else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def faceswap(root, target_path, face_path, project, purpose,
             style_blend=0.0, prompt=None, negative=None, checkpoint=None,
             lora=None, lora_strength=0.9, restore=None, seed=None,
             job_id=None, dry_run=False):
    """Put the face from face_path onto the image at target_path via ReActor.

    style_blend == 0: direct swap (photoreal targets — fast, exact).
    style_blend  > 0: swap, then a low-denoise img2img pass at that strength so
    the swapped face melts into stylized/anime art (0.3–0.45 sweet spot) instead
    of looking pasted on. The blend pass takes a character prompt, a checkpoint
    (anime targets want an anime checkpoint) and optionally the identity LoRA.
    Returns (job_id, [(png_path, card_dict), ...]) like generate()."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    target = Path(target_path)
    face = Path(face_path)
    if not target.exists():
        die(f"faceswap target not found: {target}")
    if not face.exists():
        die(f"faceswap face photo not found: {face}")

    blend = max(0.0, min(0.65, float(style_blend or 0)))
    if blend > 0:
        workflow_rel = img_cfg.get("faceswap_blend_workflow",
                                   "workflows/reactor_faceswap_blend_api.json")
    else:
        workflow_rel = img_cfg.get("faceswap_workflow",
                                   "workflows/reactor_faceswap_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)

    job_id = job_id or new_id("job")
    prefix = f"{datetime.now():%Y%m%d}_swap_{job_id}"
    restore = restore or img_cfg.get("faceswap_restore", "GFPGANv1.4.pth")

    # The swap graph names its image inputs: 'target' is the picture being
    # swapped onto, 'face' is the identity source. Explicit ids, loud failure —
    # a swapped pair would put the target's face onto the founder's photo.
    if "target" not in graph or "face" not in graph or not any(
            n.get("class_type") == "ReActorFaceSwap" for n in graph.values()):
        die(f"{workflow_rel} must have 'target'/'face' LoadImage nodes and a "
            "ReActorFaceSwap node")
    for node in graph.values():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "ReActorFaceSwap":
            inputs["enabled"] = True
            inputs["face_restore_model"] = restore
        elif ct == "SaveImage":
            inputs["filename_prefix"] = prefix

    ckpt_requested = ckpt_used = None
    ckpt_matched = True
    if blend > 0:
        prompt = prompt or ("portrait, keep the original character art style, "
                            "seamless natural face, high quality, sharp detail")
        negative = negative or ("deformed face, extra faces, disfigured, blurry, "
                                "low quality, watermark, text")
        ckpt_requested = (checkpoint or img_cfg.get("faceswap_blend_checkpoint")
                          or "animagine-xl-4.0")
        ckpt_used, ckpt_matched = resolve_checkpoint_info(root, ckpt_requested, comfy=comfy)
        seed = int(seed) if seed else secrets.randbits(63)
        for node in graph.values():
            ct, inputs = node.get("class_type"), node.get("inputs", {})
            if ct == "KSampler":
                inputs["seed"] = seed
                inputs["denoise"] = blend
                inputs["cfg"] = img_cfg.get("cfg", 7.0)
                inputs["sampler_name"] = img_cfg.get("sampler", "dpmpp_2m")
                inputs["scheduler"] = img_cfg.get("scheduler", "karras")
            elif ct == "CheckpointLoaderSimple":
                inputs["ckpt_name"] = ckpt_used
        # same stale-text guard as generate(): wire prompt/negative through the
        # sampler's own sockets, never by node id
        for node in graph.values():
            if node.get("class_type") != "KSampler":
                continue
            for socket, text in (("positive", prompt), ("negative", negative)):
                ref = node["inputs"].get(socket)
                tgt = graph.get(str(ref[0])) if isinstance(ref, list) and ref else None
                if not tgt or tgt.get("class_type") != "CLIPTextEncode":
                    die(f"blend KSampler {socket} not wired to CLIPTextEncode")
                tgt["inputs"]["text"] = text
        if lora:
            insert_lora(graph, resolve_lora(root, lora), lora_strength)
            print(f"[byrdimage] identity LoRA attached to blend pass: {lora} @ {lora_strength}")
    else:
        seed = None  # no diffusion in a direct swap — an honest card has no seed

    print(f"[byrdimage] faceswap {job_id}  target {target.name}  face {face.name}"
          f"  blend {blend}" + (f"  ckpt {ckpt_used}" if ckpt_used else ""))
    if dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return job_id, []

    graph["target"]["inputs"]["image"] = upload_image(comfy, target)
    graph["face"]["inputs"]["image"] = upload_image(comfy, face)

    card_base = {
        "recipe": "faceswap@1", "purpose": purpose,
        "prompt": prompt or "", "negative": negative or "",
        "seed": seed, "workflow": workflow_rel,
        "slots": {}, "vary_picks": {},
        "swap_target": str(target), "face_source": str(face),
        "style_blend": blend, "restore": restore,
        **({"checkpoint": ckpt_used} if ckpt_used else {}),
        **({"lora": lora} if lora and blend > 0 else {}),
        **({"checkpoint_requested": ckpt_requested, "checkpoint_fallback": True}
           if ckpt_used and not ckpt_matched else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def faceswap_inpaint(root, target_path, mask_path, project, purpose,
                     prompt=None, negative=None, denoise=None, checkpoint=None,
                     lora=None, lora_strength=0.9, seed=None,
                     job_id=None, dry_run=False):
    """The founder lane's GPU step: edit ONLY inside an approved zone.

    target_path is the picture; mask_path is the edit-zone image (WHITE = change
    here, black = keep target-authentic — hair, blindfold, ear ink, collar stay
    untouched). Identity comes from the trained LoRA + prompt, not from warping
    a photo, so this is also the cleanup/harmonization pass over a CPU mesh seed
    (byrdfacezone). denoise is the control: too low suppresses the LoRA, ~0.9
    takes over with artifacts — clamped to the usable corridor, default 0.7."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    target = Path(target_path)
    mask = Path(mask_path)
    if not target.exists():
        die(f"facezone target not found: {target}")
    if not mask.exists():
        die(f"facezone mask not found: {mask}")

    workflow_rel = img_cfg.get("faceswap_inpaint_workflow",
                               "workflows/faceswap_inpaint_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)
    if "target" not in graph or "maskimg" not in graph or not any(
            n.get("class_type") == "VAEEncodeForInpaint" for n in graph.values()):
        die(f"{workflow_rel} must have 'target'/'maskimg' LoadImage nodes and a "
            "VAEEncodeForInpaint node")

    job_id = job_id or new_id("job")
    prefix = f"{datetime.now():%Y%m%d}_facezone_{job_id}"
    denoise = max(0.3, min(0.9, float(
        denoise or img_cfg.get("faceswap_inpaint_denoise", 0.7))))
    prompt = prompt or ("the same man's face, natural skin tone, matching the "
                        "surrounding art style exactly, seamless flat cel shading, "
                        "clean linework, high quality")
    negative = negative or ("photorealistic skin on anime body, mismatched art "
                            "styles, seam, hard edge, deformed face, text, "
                            "watermark, low quality")
    ckpt_requested = (checkpoint or img_cfg.get("faceswap_blend_checkpoint")
                      or "animagine-xl-4.0")
    ckpt_used, ckpt_matched = resolve_checkpoint_info(root, ckpt_requested, comfy=comfy)
    seed = int(seed) if seed else secrets.randbits(63)

    for node in graph.values():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "KSampler":
            inputs["seed"] = seed
            inputs["denoise"] = denoise
            inputs["cfg"] = img_cfg.get("cfg", 7.0)
            inputs["sampler_name"] = img_cfg.get("sampler", "dpmpp_2m")
            inputs["scheduler"] = img_cfg.get("scheduler", "karras")
        elif ct == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = ckpt_used
        elif ct == "SaveImage":
            inputs["filename_prefix"] = prefix
    for node in graph.values():
        if node.get("class_type") != "KSampler":
            continue
        for socket, text in (("positive", prompt), ("negative", negative)):
            ref = node["inputs"].get(socket)
            tgt = graph.get(str(ref[0])) if isinstance(ref, list) and ref else None
            if not tgt or tgt.get("class_type") != "CLIPTextEncode":
                die(f"facezone KSampler {socket} not wired to CLIPTextEncode")
            tgt["inputs"]["text"] = text
    if lora:
        insert_lora(graph, resolve_lora(root, lora), lora_strength)
        print(f"[byrdimage] identity LoRA attached to zone edit: {lora} @ {lora_strength}")

    print(f"[byrdimage] facezone {job_id}  target {target.name}  mask {mask.name}"
          f"  denoise {denoise}  ckpt {ckpt_used}")
    if dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return job_id, []

    graph["target"]["inputs"]["image"] = upload_image(comfy, target)
    graph["maskimg"]["inputs"]["image"] = upload_image(comfy, mask)

    card_base = {
        "recipe": "facezone@1", "purpose": purpose,
        "prompt": prompt, "negative": negative,
        "seed": seed, "checkpoint": ckpt_used, "workflow": workflow_rel,
        "slots": {}, "vary_picks": {},
        "swap_target": str(target), "mask_source": str(mask),
        "denoise": denoise,
        **({"lora": lora} if lora else {}),
        **({"checkpoint_requested": ckpt_requested, "checkpoint_fallback": True}
           if not ckpt_matched else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def facezone_auto(root, target_path, project, purpose,
                  prompt=None, negative=None, denoise=None, checkpoint=None,
                  lora=None, lora_strength=0.9, detector=None, seed=None,
                  job_id=None, dry_run=False):
    """The daily driver: upload any character picture -> the detector finds the
    face, masks it, redraws it as YOU (identity LoRA + prompt) in the target's
    own art style, composites it back. No hand mask, no face photo — one step.
    Uses Impact Pack's FaceDetailer (detect->mask->inpaint->composite) with a
    YOLO face detector that handles anime faces. Same denoise corridor as the
    zone route. Returns (job_id, [(png_path, card_dict), ...])."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    target = Path(target_path)
    if not target.exists():
        die(f"facezone target not found: {target}")

    workflow_rel = img_cfg.get("faceswap_auto_workflow",
                               "workflows/facezone_auto_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)
    fd_nodes = [n for n in graph.values() if n.get("class_type") == "FaceDetailer"]
    if "target" not in graph or not fd_nodes:
        die(f"{workflow_rel} must have a 'target' LoadImage node and a FaceDetailer node")

    job_id = job_id or new_id("job")
    prefix = f"{datetime.now():%Y%m%d}_facezone_{job_id}"
    denoise = max(0.3, min(0.9, float(
        denoise or img_cfg.get("faceswap_inpaint_denoise", 0.7))))
    detector = detector or img_cfg.get("faceswap_detector", "bbox/face_yolov8m.pt")
    prompt = prompt or ("the same man's face, natural skin tone, matching the "
                        "surrounding art style exactly, seamless flat cel shading, "
                        "clean linework, high quality")
    negative = negative or ("photorealistic skin on anime body, mismatched art "
                            "styles, seam, hard edge, deformed face, text, "
                            "watermark, low quality")
    ckpt_requested = (checkpoint or img_cfg.get("faceswap_blend_checkpoint")
                      or "animagine-xl-4.0")
    ckpt_used, ckpt_matched = resolve_checkpoint_info(root, ckpt_requested, comfy=comfy)
    seed = int(seed) if seed else secrets.randbits(63)

    for node in graph.values():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "FaceDetailer":
            inputs["seed"] = seed
            inputs["denoise"] = denoise
            inputs["cfg"] = img_cfg.get("cfg", 7.0)
            inputs["sampler_name"] = img_cfg.get("sampler", "dpmpp_2m")
            inputs["scheduler"] = img_cfg.get("scheduler", "karras")
        elif ct == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = ckpt_used
        elif ct == "UltralyticsDetectorProvider":
            inputs["model_name"] = detector
        elif ct == "SaveImage":
            inputs["filename_prefix"] = prefix
    # wire prompt/negative through the FaceDetailer's own sockets — same
    # stale-text guard as generate(), just a different sampler-bearing node
    for node in fd_nodes:
        for socket, text in (("positive", prompt), ("negative", negative)):
            ref = node["inputs"].get(socket)
            tgt = graph.get(str(ref[0])) if isinstance(ref, list) and ref else None
            if not tgt or tgt.get("class_type") != "CLIPTextEncode":
                die(f"FaceDetailer {socket} not wired to CLIPTextEncode")
            tgt["inputs"]["text"] = text
    if lora:
        insert_lora(graph, resolve_lora(root, lora), lora_strength)
        print(f"[byrdimage] identity LoRA attached to auto zone: {lora} @ {lora_strength}")

    print(f"[byrdimage] facezone-auto {job_id}  target {target.name}  "
          f"detector {detector}  denoise {denoise}  ckpt {ckpt_used}")
    if dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return job_id, []

    graph["target"]["inputs"]["image"] = upload_image(comfy, target)

    card_base = {
        "recipe": "facezone_auto@1", "purpose": purpose,
        "prompt": prompt, "negative": negative,
        "seed": seed, "checkpoint": ckpt_used, "workflow": workflow_rel,
        "slots": {}, "vary_picks": {},
        "swap_target": str(target), "detector": detector,
        "denoise": denoise,
        **({"lora": lora} if lora else {}),
        **({"checkpoint_requested": ckpt_requested, "checkpoint_fallback": True}
           if not ckpt_matched else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def facezone_preview(root, target_path, project, purpose,
                     detector=None, threshold=None, job_id=None, dry_run=False):
    """The CPU pre-step, inspectable (Codex's rule: the GPU must not decide the
    mask). Runs ONLY detection on the target — no checkpoint, no diffusion —
    and archives TWO artifacts: a diagnostic overlay (the zone glowing on the
    character) and the soft mask itself. The founder approves the zone, then
    the swap runs with exactly that mask (image.faceswap mask_artifact).
    Returns (job_id, [(png_path, card_dict), ...])."""
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    target = Path(target_path)
    if not target.exists():
        die(f"zone preview target not found: {target}")

    workflow_rel = img_cfg.get("faceswap_preview_workflow",
                               "workflows/facezone_preview_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)
    if "target" not in graph or not any(
            n.get("class_type") == "BboxDetectorSEGS" for n in graph.values()):
        die(f"{workflow_rel} must have a 'target' LoadImage node and a "
            "BboxDetectorSEGS node")

    job_id = job_id or new_id("job")
    prefix = f"{datetime.now():%Y%m%d}_zone_{job_id}"
    detector = detector or img_cfg.get("faceswap_detector", "bbox/face_yolov8m.pt")
    threshold = float(threshold or 0.5)

    for nid, node in graph.items():
        ct, inputs = node.get("class_type"), node.get("inputs", {})
        if ct == "UltralyticsDetectorProvider":
            inputs["model_name"] = detector
        elif ct == "BboxDetectorSEGS":
            inputs["threshold"] = threshold
        elif ct == "SaveImage":
            # keep the two outputs tellable apart in the archive: _overlay/_mask
            tag = "mask" if "mask" in str(nid) else "overlay"
            inputs["filename_prefix"] = f"{prefix}_{tag}"

    print(f"[byrdimage] zone-preview {job_id}  target {target.name}  "
          f"detector {detector}  threshold {threshold}  (CPU only, no diffusion)")
    if dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return job_id, []

    graph["target"]["inputs"]["image"] = upload_image(comfy, target)

    card_base = {
        "recipe": "facezone_preview@1", "purpose": purpose,
        "prompt": "", "negative": "", "seed": None,
        "workflow": workflow_rel, "slots": {}, "vary_picks": {},
        "swap_target": str(target), "detector": detector,
        "threshold": threshold,
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe")
    ap.add_argument("--set", action="append", default=[], metavar="key=value")
    ap.add_argument("--project", default="sandbox")
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--batch", type=int)
    ap.add_argument("--checkpoint")
    ap.add_argument("--swap-target", help="face swap: image to put the face onto (instead of --recipe)")
    ap.add_argument("--swap-face", help="face swap: face photo (e.g. profiles/me/references/front.jpg)")
    ap.add_argument("--swap-mask", help="zone edit: mask image (WHITE = change zone) — uses the "
                                        "inpaint route; identity from --lora + --prompt")
    ap.add_argument("--auto", action="store_true",
                    help="auto route: detector finds the face, masks and redraws it "
                         "as you (--lora + --prompt) — no mask, no face photo")
    ap.add_argument("--preview", action="store_true",
                    help="CPU zone preview: detection only — saves the zone overlay "
                         "+ mask for approval, no checkpoint, no diffusion")
    ap.add_argument("--edit-face-zone", metavar="TARGET_IMAGE",
                    help="QUALITY lane by hand: examiner gate -> CPU mesh seed -> "
                         "cleanup -> composite (recipe anime_face_zone_edit)")
    ap.add_argument("--face-preset", default="auto",
                    help="quality lane preset: auto|gojo|vegeta|luffy_close|luffy_full")
    ap.add_argument("--face-index", type=int, default=0,
                    help="which face when the examiner reports several (0 = largest)")
    ap.add_argument("--face-recipe", default="anime_face_zone_edit",
                    help="quality-lane recipe (pin a version with name@N)")
    ap.add_argument("--workflow",
                    help="quality-lane avenue override: a workflows/ path or a "
                         "shorthand — controlnet | diffdiff | ipadapter")
    ap.add_argument("--denoise", type=float, help="zone edit denoise (default 0.7)")
    ap.add_argument("--blend", type=float, default=0.0,
                    help="face swap style blend 0-0.65 (0.3-0.45 for anime targets)")
    ap.add_argument("--lora")
    ap.add_argument("--prompt")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = os.environ.get("BYRDHOUSE_ROOT")
    if not root:
        die("BYRDHOUSE_ROOT not set — run the setup script first")

    if args.edit_face_zone:
        engine = {"face_index": args.face_index}
        shorthand = {
            "controlnet": "workflows/sd15_face_zone_controlnet_api.json",
            "diffdiff": "workflows/sd15_face_zone_diffdiff_api.json",
            "ipadapter": "workflows/sd15_face_zone_ipadapter_api.json",
        }
        if args.workflow:
            engine["workflow"] = shorthand.get(args.workflow, args.workflow)
        edit_face_zone(root, args.face_recipe, args.edit_face_zone,
                       args.project, args.purpose,
                       identity_lora=args.lora, target_preset=args.face_preset,
                       engine=engine)
        return
    if args.swap_target:
        if args.preview:
            facezone_preview(root, args.swap_target, args.project, args.purpose,
                             dry_run=args.dry_run)
            return
        if args.auto:
            facezone_auto(root, args.swap_target, args.project, args.purpose,
                          prompt=args.prompt, denoise=args.denoise,
                          checkpoint=args.checkpoint, lora=args.lora,
                          dry_run=args.dry_run)
            return
        if args.swap_mask:
            faceswap_inpaint(root, args.swap_target, args.swap_mask, args.project,
                             args.purpose, prompt=args.prompt, denoise=args.denoise,
                             checkpoint=args.checkpoint, lora=args.lora,
                             dry_run=args.dry_run)
            return
        if not args.swap_face:
            die("--swap-target needs --swap-face, --swap-mask (zone) or --auto")
        faceswap(root, args.swap_target, args.swap_face, args.project,
                 args.purpose, style_blend=args.blend, prompt=args.prompt,
                 checkpoint=args.checkpoint, lora=args.lora, dry_run=args.dry_run)
        return
    if not args.recipe:
        die("--recipe is required (or use --swap-target for a face swap)")

    slots = {}
    for kv in args.set:
        if "=" not in kv:
            die(f"--set needs key=value, got '{kv}'")
        k, v = kv.split("=", 1)
        slots[k] = v

    generate(root, args.recipe, slots, args.project, args.purpose,
             batch=args.batch, checkpoint=args.checkpoint, dry_run=args.dry_run)


if __name__ == "__main__":
    main()



