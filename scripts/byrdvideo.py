"""
byrdvideo.py — the VIDEO lane (handoff 2026-07-25 §7).

    VIDEO RULE: do not ask a video model to rediscover Carey. The first frame
    must already be an APPROVED identity artifact. Video is an animation of a
    trusted still, followed by drift examination.

So this module animates a still; it never generates identity. The worker
(`video.i2v`) enforces the approval requirement before calling in here — a
still that the belt has not approved is refused, not animated.

Why this exists at all: `video.i2v` was a declared job type with no runner, and
every LTX graph in `Video/Workflows/` is a ComfyUI *UI* export ({nodes,links})
which cannot be POSTed to `/prompt`. So video could never have run. The
POST-able graph is `workflows/ltx_i2v_api.json`, converted node-for-node from
the UI baseline.

Stdlib only (reuses byrdimage's ComfyUI plumbing).

    animate(root, still_path, project, purpose, prompt=..., ...) -> (job_id, saved)
"""

import json
import secrets
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdimage  # noqa: E402  — upload_image / submit_and_wait / die / load_json

DEFAULT_WORKFLOW = "workflows/ltx_i2v_api.json"
# LTX wants (frames - 1) divisible by 8; 97 is the baseline graph's value.
DEFAULT_LENGTH = 97
DEFAULT_FPS = 24


def _video_cfg(cfg: dict) -> dict:
    return (cfg.get("video") or {})


def _collect_outputs(comfy: str, outputs: dict, dest_dir: Path):
    """Fetch every produced file. Video savers do not all report under the
    'images' key the way SaveImage does (SaveWEBM/VHS nodes use their own keys),
    so scan every list-of-dicts that carries a 'filename' rather than assuming a
    key name we have not verified on this ComfyUI build."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for value in node_output.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                q = urllib.parse.urlencode({
                    "filename": item["filename"],
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output"),
                })
                with urllib.request.urlopen(f"{comfy}/view?{q}", timeout=300) as r:
                    data = r.read()
                dest = dest_dir / item["filename"]
                dest.write_bytes(data)
                files.append(dest)
    return files


def animate(root, still_path, project, purpose, prompt="", negative=None,
            seed=None, width=None, height=None, length=None, fps=None,
            steps=None, cfg_scale=None, workflow=None, job_id=None,
            source_artifact=None, dry_run=False):
    """Animate ONE approved still into a short clip. Returns (job_id, [(path, card)])."""
    root = Path(root)
    still_path = Path(still_path)
    if not still_path.is_file():
        byrdimage.die(f"still not found: {still_path}")

    conf = byrdimage.load_json(root / "byrdhouse.config.json")
    comfy = conf["services"]["comfyui"].rstrip("/")
    vcfg = _video_cfg(conf)
    job_id = job_id or byrdimage.new_id("vid")

    wf_rel = workflow or vcfg.get("workflow") or DEFAULT_WORKFLOW
    graph_path = root / wf_rel
    if not graph_path.is_file():
        byrdimage.die(f"video workflow not found: {graph_path}")
    graph = byrdimage.load_json(graph_path)
    graph.pop("_comment", None)

    # A UI export can never be submitted — refuse loudly instead of letting
    # ComfyUI return a 400 that looks like a mysterious hang.
    if "nodes" in graph and "links" in graph:
        byrdimage.die(
            f"{wf_rel} is a ComfyUI UI export, not an API graph — it cannot be "
            f"POSTed to /prompt. Re-export via 'Export (API)' or use "
            f"{DEFAULT_WORKFLOW}.")

    # Random per job, or pinned for an exact rerun — same contract as byrdimage.
    seed = int(seed) if seed is not None else secrets.randbits(63)
    length = int(length or vcfg.get("length", DEFAULT_LENGTH))
    fps = int(fps or vcfg.get("fps", DEFAULT_FPS))

    # Find nodes by class_type so a re-exported graph with different ids works.
    def nodes_of(cls):
        return [n for n in graph.values()
                if isinstance(n, dict) and n.get("class_type") == cls]

    loaders = nodes_of("LoadImage")
    if not loaders:
        byrdimage.die(f"{wf_rel} has no LoadImage node to receive the still")
    stored = still_path.name if dry_run else byrdimage.upload_image(comfy, still_path)
    for n in loaders:
        n["inputs"]["image"] = stored

    encoders = nodes_of("CLIPTextEncode")
    # Title-based assignment keeps positive/negative straight (the graph labels
    # them); fall back to document order only if the titles are missing.
    pos = [n for n in encoders if "POS" in (n.get("_meta", {}).get("title", "").upper())]
    neg = [n for n in encoders if "NEG" in (n.get("_meta", {}).get("title", "").upper())]
    if not pos or not neg:
        if len(encoders) < 2:
            byrdimage.die(f"{wf_rel} needs two CLIPTextEncode nodes (positive/negative)")
        pos, neg = [encoders[0]], [encoders[1]]
    if prompt:
        for n in pos:
            n["inputs"]["text"] = prompt
    if negative:
        for n in neg:
            n["inputs"]["text"] = negative

    for n in nodes_of("LTXVImgToVideo"):
        if width:
            n["inputs"]["width"] = int(width)
        if height:
            n["inputs"]["height"] = int(height)
        n["inputs"]["length"] = length
    for n in nodes_of("LTXVConditioning"):
        n["inputs"]["frame_rate"] = fps
    for n in nodes_of("LTXVScheduler"):
        if steps:
            n["inputs"]["steps"] = int(steps)
    for n in nodes_of("SamplerCustom"):
        n["inputs"]["noise_seed"] = seed
        if cfg_scale is not None:
            n["inputs"]["cfg"] = float(cfg_scale)
    prefix = f"{datetime.now():%Y%m%d}_video_{job_id}"
    for cls in ("SaveWEBM", "SaveAnimatedWEBP", "SaveVideo", "VHS_VideoCombine"):
        for n in nodes_of(cls):
            key = "filename_prefix" if "filename_prefix" in n["inputs"] else None
            if key:
                n["inputs"][key] = prefix

    card_base = {
        "kind": "video",
        "purpose": purpose,
        "recipe": "video_i2v_ltx@1",
        "workflow": wf_rel,
        "prompt": prompt,
        "negative": (negative or ""),
        "seed": seed,
        "length_frames": length,
        "fps": fps,
        "duration_seconds": round(length / fps, 2) if fps else None,
        "source_still": str(still_path),
        "source_artifact": source_artifact,
        "engine": "ltx-video",
    }
    if dry_run:
        return job_id, [(graph_path, dict(card_base, dry_run=True))]

    print(f"[byrdvideo] animating {still_path.name} — {length} frames @ {fps}fps, seed {seed}")
    outputs = byrdimage.submit_and_wait(comfy, graph, job_id)
    month_dir = root / "artifacts" / project / f"{datetime.now():%Y-%m}"
    files = _collect_outputs(comfy, outputs, month_dir)
    if not files:
        byrdimage.die("video job finished but produced no output file")

    now_iso = datetime.now(timezone.utc).isoformat()
    saved = []
    for i, dest in enumerate(files):
        card = {"artifact_id": f"art.{job_id}.{i}", "job_id": job_id,
                "project": project, **card_base,
                "score": None, "tags": [], "caption": "",
                "status": "draft", "created_at": now_iso}
        dest.with_suffix(dest.suffix + ".json").write_text(
            json.dumps(card, indent=2), encoding="utf-8")
        saved.append((dest, card))
        print(f"[byrdvideo]   archived {dest} (+card)")
    return job_id, saved
