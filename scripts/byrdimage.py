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
    print(f"[byrdimage] ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def new_id(prefix: str) -> str:
    ts = format(int(time.time() * 1000), "x")
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}_{ts}{rand}"


def find_recipe(root: Path, name: str) -> Path:
    candidates = sorted((root / "recipes").glob(f"{name}.v*.json"))
    if not candidates:
        die(f"no recipe '{name}' in {root / 'recipes'}")
    def version(p: Path) -> int:
        m = re.search(r"\.v(\d+)\.json$", p.name)
        return int(m.group(1)) if m else 0
    return max(candidates, key=version)


def http_json(url: str, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


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
    root = Path(root)
    cfg = load_json(root / "byrdhouse.config.json")
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})

    recipe_path = find_recipe(root, args.recipe)
    recipe = load_json(recipe_path)
    recipe_tag = f"{recipe['id']}@{recipe['version']}"

    # ── Fill the template: explicit --set slots, then random picks from vary ──
    slots = {}
    for kv in args.set:
        if "=" not in kv:
            die(f"--set needs key=value, got '{kv}'")
        k, v = kv.split("=", 1)
        slots[k] = v
    vary_picks = {}
    for k, options in recipe.get("vary", {}).items():
        if k not in slots:
            vary_picks[k] = random.choice(options)
    slots.update(vary_picks)

    template = recipe["template"]
    missing = [k for k in re.findall(r"\{(\w+)\}", template) if k not in slots]
    if missing:
        die(f"unfilled slots {missing} — pass --set {missing[0]}=\"...\"")
    prompt = re.sub(r"\s+", " ", template.format(**slots)).strip()
    negative = recipe.get("negative", "")

    defaults = recipe.get("defaults", {})
    checkpoint = args.checkpoint or defaults.get("checkpoint") or die("no checkpoint")
    if not checkpoint.endswith(".safetensors"):
        checkpoint += ".safetensors"
    batch = args.batch or defaults.get("batch", 1)
    steps = defaults.get("steps", 30)

    # ── Build the graph ───────────────────────────────────────────────────────
    workflow_rel = img_cfg.get("workflow", "workflows/sdxl_base_api.json")
    graph = load_json(root / workflow_rel)
    graph.pop("_comment", None)

    job_id = new_id("job")
    seed = secrets.randbits(63)                      # fix 1: random per job
    prefix = f"{datetime.now():%Y%m%d}_{recipe['id']}_{job_id}"  # fix 2: unique

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
            inputs["cfg"] = img_cfg.get("cfg", 7.0)
            inputs["sampler_name"] = img_cfg.get("sampler", "dpmpp_2m")
            inputs["scheduler"] = img_cfg.get("scheduler", "karras")
        elif ct == "CheckpointLoaderSimple":
            inputs["ckpt_name"] = checkpoint          # fix 4 source of truth
        elif ct == "EmptyLatentImage":
            inputs["width"] = img_cfg.get("width", 1152)
            inputs["height"] = img_cfg.get("height", 768)
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

    print(f"[byrdimage] job {job_id}  recipe {recipe_tag}  seed {seed}")
    print(f"[byrdimage] prompt: {prompt}")
    print(f"[byrdimage] vary picks: {vary_picks or '(none)'}")
    if args.dry_run:
        print(json.dumps(graph, indent=2))
        print("[byrdimage] dry run — nothing submitted")
        return

    # ── Submit + poll ─────────────────────────────────────────────────────────
    resp = http_json(f"{comfy}/prompt", {"prompt": graph, "client_id": job_id})
    prompt_id = resp.get("prompt_id") or die(f"ComfyUI rejected the job: {resp}")
    print(f"[byrdimage] submitted, prompt_id {prompt_id} — waiting...")

    deadline = time.time() + 15 * 60
    outputs = None
    while time.time() < deadline:
        hist = http_json(f"{comfy}/history/{prompt_id}", timeout=15)
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                die(f"ComfyUI job failed: {json.dumps(status)[:500]}")
            if entry.get("outputs"):
                outputs = entry["outputs"]
                break
        time.sleep(3)
    if outputs is None:
        die("timed out after 15 min waiting for ComfyUI")

    # ── Archive + metadata cards (v2 §8: no artifact without a card) ─────────
    month_dir = root / "artifacts" / args.project / f"{datetime.now():%Y-%m}"
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
                "artifact_id": new_id("art"),
                "job_id": job_id,
                "project": args.project,
                "kind": "image",
                "recipe": recipe_tag,
                "purpose": args.purpose,
                "prompt": prompt,
                "negative": negative,
                "seed": seed,
                "checkpoint": checkpoint,
                "workflow": workflow_rel,
                "vary_picks": vary_picks,
                "score": None,
                "tags": [],
                "caption": "",
                "status": "draft",
                "created_at": now_iso,
            }
            dest.with_suffix(dest.suffix + ".json").write_text(
                json.dumps(card, indent=2), encoding="utf-8")
            saved.append(dest)
            print(f"[byrdimage]   archived {dest} (+card)")

    if not saved:
        die("job finished but produced no images")
    print(f"[byrdimage] done — {len(saved)} image(s) in {month_dir}")


if __name__ == "__main__":
    main()
