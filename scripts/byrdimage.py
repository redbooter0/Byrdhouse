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
import json
import os
import random
import re
import secrets
import string
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


def load_json(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


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


def insert_lora(graph: dict, lora_name: str, strength: float = 0.9) -> None:
    """Splice a LoraLoader between the checkpoint and everything that consumes
    its model/clip outputs. Pure graph surgery — works on any of our workflows."""
    ckpt_id = next((nid for nid, n in graph.items()
                    if n.get("class_type") == "CheckpointLoaderSimple"), None)
    if not ckpt_id:
        die("workflow has no CheckpointLoaderSimple — cannot attach a LoRA")
    lora_id = "byrd_lora"
    for nid, node in graph.items():
        if nid == lora_id:
            continue
        for key, ref in node.get("inputs", {}).items():
            if isinstance(ref, list) and len(ref) == 2 and str(ref[0]) == str(ckpt_id) and ref[1] in (0, 1):
                node["inputs"][key] = [lora_id, ref[1]]
    graph[lora_id] = {"class_type": "LoraLoader",
                      "inputs": {"lora_name": lora_name,
                                 "strength_model": strength, "strength_clip": strength,
                                 "model": [ckpt_id, 0], "clip": [ckpt_id, 1]}}


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


def http_json(url: str, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def generate(root, recipe_name, slots, project, purpose,
             batch=None, checkpoint=None, dry_run=False, job_id=None,
             aspect=None, width=None, height=None, negative_extra=None,
             lora=None, lora_strength=0.9, seed=None, reference=None,
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
        insert_lora(graph, resolve_lora(root, lora), lora_strength)
        print(f"[byrdimage] LoRA attached: {lora} @ {lora_strength}")

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
        **({"lora": lora} if lora else {}),
        **({"reference": str(reference)} if reference else {}),
        **({"checkpoint_requested": ckpt_requested, "checkpoint_fallback": True}
           if not ckpt_matched else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


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

    print(f"[byrdimage] refine {source.name}  strength {strength}  scale {scale}")
    card_base = {
        "recipe": src_card.get("recipe", "refine"), "purpose": purpose,
        "prompt": prompt, "negative": negative, "seed": seed,
        "checkpoint": checkpoint, "workflow": workflow_rel,
        "slots": src_card.get("slots", {}), "vary_picks": {},
        "refined_from": str(source), "strength": strength, "scale": scale,
        **({"lora": lora} if lora else {}),
    }
    return job_id, run_graph(root, comfy, graph, job_id, project, card_base)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--set", action="append", default=[], metavar="key=value")
    ap.add_argument("--project", default="sandbox")
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--batch", type=int)
    ap.add_argument("--checkpoint")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = os.environ.get("BYRDHOUSE_ROOT")
    if not root:
        die("BYRDHOUSE_ROOT not set — run the setup script first")

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
