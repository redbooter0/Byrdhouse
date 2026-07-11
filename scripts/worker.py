"""
worker.py — BYRD-GAMING worker daemon (Blueprint v2 §7: the factory shift).

Pulls jobs from the router (never pushed to), heartbeats, and runs the GPU
mode ritual: batch all IMAGE work, verify VRAM, then switch back to OPERATOR
and judge what was produced. Every artifact is registered with the router;
every image.generate auto-enqueues an image.judge (v2 §7.1 step 5).

Stdlib only. Run:  python scripts/worker.py [--no-gpu] [--once]
  --no-gpu   skip lms/nvidia-smi rituals (dev machines, CI, BYRD-MINI)
  --once     drain the queue once and exit (good for testing)
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdimage  # noqa: E402
import byrdjudge  # noqa: E402
import compose_thumbnail  # noqa: E402

ROOT = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
CFG = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
ROUTER = CFG["services"]["router"].rstrip("/")
TOKEN = CFG["auth"]["admin_token"]
WORKER_ID = f"worker-{socket.gethostname().lower()}"
CAPS = ["comfyui", "lmstudio"]
GPU_ENABLED = True


def api(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ROUTER}{path}", data=data, method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def upload_preview(artifact_id, path):
    """Push the image bytes to the router so the dashboard can preview it —
    artifact files live on this machine's disk, not the router's."""
    try:
        req = urllib.request.Request(
            f"{ROUTER}/artifacts/{artifact_id}/file", data=Path(path).read_bytes(),
            method="POST",
            headers={"Content-Type": "image/png",
                     "Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    except Exception as e:
        log(f"preview upload failed for {artifact_id}: {e}")  # non-fatal: card still registers


def log(msg):
    print(f"[worker {datetime.now():%H:%M:%S}] {msg}", flush=True)


def _lms_unload_all():
    if GPU_ENABLED:
        subprocess.run(["lms", "unload", "--all"], timeout=120)


def _lms_load(model: str):
    if GPU_ENABLED and model and not model.startswith("CHANGE_ME"):
        subprocess.run(["lms", "load", model], timeout=600)


class Gpu:
    """The mode ritual (v2 §7.1). With --no-gpu every switch is a no-op."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.mode = CFG["gpu"].get("default_mode", "OPERATOR")

    def _vram(self):
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
        used, total = out.strip().splitlines()[0].split(",")
        return int(used.strip()), int(total.strip())

    def switch(self, target: str):
        if target == self.mode:
            return
        log(f"mode {self.mode} -> {target}")
        if self.enabled:
            if target == "IMAGE":
                subprocess.run(["lms", "unload", "--all"], timeout=120)
                threshold = int(CFG["gpu"].get("vram_free_threshold_mb", 1024))
                deadline = time.time() + 180
                while time.time() < deadline:
                    used, total = self._vram()
                    free = total - used
                    if free >= threshold:
                        break
                    log(f"  waiting for VRAM: {free}MB free ({used}MB used)")
                    time.sleep(5)
                else:
                    raise RuntimeError("VRAM did not free — aborting mode switch")
            elif target == "OPERATOR":
                model = CFG["gpu"].get("operator_model", "")
                if model and not model.startswith("CHANGE_ME"):
                    subprocess.run(["lms", "load", model], timeout=600)
        self.mode = target
        api("/workers/heartbeat", {"id": WORKER_ID, "host": socket.gethostname(),
                                   "caps": CAPS, "mode": self.mode})


def register_cards(job, cards):
    """One path for every generated image: register the cards, upload preview
    bytes for the dashboard, auto-enqueue the judge pass (v2 §7.1 step 5)."""
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": cards})
    for card in cards:
        upload_preview(card["artifact_id"], card["path"])
        api("/jobs", {"type": "image.judge", "project": card["project"],
                      "required_mode": "OPERATOR", "required_caps": ["lmstudio"],
                      "payload": {"artifact_id": card["artifact_id"],
                                  "path": card["path"]}})


def run_generate(job) -> None:
    p = json.loads(job["payload"])
    job_id, saved = byrdimage.generate(
        ROOT, p["recipe"], p.get("slots", {}), p.get("project", "sandbox"),
        p.get("purpose", "unspecified"), batch=p.get("batch"),
        checkpoint=p.get("checkpoint"), job_id=job["id"])
    cards = []
    for png, card in saved:
        card["path"] = str(png)
        cards.append(card)
    register_cards(job, cards)


def run_judge(job) -> None:
    p = json.loads(job["payload"])
    image_path = Path(p["path"])
    card_path = image_path.with_suffix(image_path.suffix + ".json")
    card = json.loads(card_path.read_text(encoding="utf-8-sig")) if card_path.exists() else dict(p)
    _lms_unload_all()
    _lms_load(CFG["gpu"].get("judge_model", ""))
    verdict = byrdjudge.judge_card(ROOT, card, image_path)
    card.update(score=verdict["score"], tags=verdict["tags"], caption=verdict["caption"])
    card["rubric_scores"] = verdict["scores"]
    if card_path.exists():
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    api(f"/artifacts/{p['artifact_id']}/review",
        {"action": "judge", "score": verdict["score"], "tags": verdict["tags"],
         "caption": verdict["caption"]})


def run_report(job) -> None:
    report = api("/reports/daily")
    out_dir = ROOT / "artifacts" / "reports" / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"daily_{datetime.now():%Y%m%d}_{job['id']}.md"
    dest.write_text(report["markdown"], encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": "byrdhouse", "kind": "report",
        "path": str(dest), "purpose": "daily report", "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_content_thumbnail(job) -> None:
    """v3.1 §3 two-pass: generate the ART (no text), then composite REAL text.
    payload.image_path skips pass 1 entirely — real screenshots and box art
    beat diffused lookalikes for virality, so bring-your-own-image is first-class."""
    p = json.loads(job["payload"])
    title = p.get("title") or ""
    if not title:
        raise RuntimeError("content.thumbnail needs payload.title")

    src = p.get("image_path")
    if src:
        png = Path(src)
        if not png.exists():
            raise RuntimeError(f"image_path not found on this worker: {png}")
        month_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
        final = month_dir / f"{png.stem}_{job['id']}_final.png"
        compose_thumbnail.compose(
            png, title, final, zone=p.get("zone", "bottom"),
            palette=p.get("palette", "black-gold"), style=p.get("style", "banner"))
        card = {"artifact_id": f"art.{job['id']}.0", "job_id": job["id"],
                "project": p.get("project", "careyrpg"), "kind": "thumbnail",
                "path": str(final), "title": title, "source_image": str(png),
                "purpose": p.get("purpose", "thumbnail"), "prompt": "",
                "slots": {}, "score": None, "tags": [], "caption": "",
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat()}
        final.with_suffix(".png.json").write_text(json.dumps(card, indent=2),
                                                  encoding="utf-8")
        register_cards(job, [card])
        return

    recipe_spec = byrdimage.load_json(byrdimage.find_recipe(ROOT, p["recipe"]))
    _, saved = byrdimage.generate(
        ROOT, p["recipe"], p.get("slots", {}), p.get("project", "careyrpg"),
        p.get("purpose", "thumbnail"), batch=p.get("batch"),
        checkpoint=p.get("checkpoint"), job_id=job["id"])
    compose_cfg = recipe_spec.get("compose", {})
    cards = []
    for png, card in saved:
        final = png.with_name(png.stem + "_final.png")
        compose_thumbnail.compose(
            png, title, final,
            zone=compose_cfg.get("text_zone", "upper-left"),
            palette=card.get("vary_picks", {}).get("palette", "default"),
            max_words=compose_cfg.get("max_words", 5),
            style=compose_cfg.get("style", "accent"))
        card = dict(card, kind="thumbnail", path=str(final), title=title,
                    artifact_id=card["artifact_id"] + "f")
        final.with_suffix(".png.json").write_text(json.dumps(card, indent=2),
                                                  encoding="utf-8")
        cards.append(card)
    register_cards(job, cards)


def _lms_chat(prompt: str, max_tokens=900) -> str:
    model = CFG["gpu"].get("operator_model", "")
    if not model or model.startswith("CHANGE_ME"):
        raise RuntimeError("gpu.operator_model not set in byrdhouse.config.json")
    _lms_unload_all()
    _lms_load(model)
    lms = CFG["services"]["lmstudio"].rstrip("/")
    req = urllib.request.Request(
        f"{lms}/chat/completions",
        data=json.dumps({"model": model, "temperature": 0.7, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def run_content_package(job) -> None:
    """v3.1 §2: transcript -> titles/tags/description/pinned comment in YOUR voice."""
    import re as _re
    p = json.loads(job["payload"])
    transcript = p.get("transcript_text") or Path(p["transcript_path"]).read_text(encoding="utf-8-sig")
    voice_path = ROOT / "recipes" / "voice_carey.json"
    voice = json.loads(voice_path.read_text(encoding="utf-8-sig")) if voice_path.exists() else {}
    prompt = (
        "You write YouTube packaging for the channel "
        f"{voice.get('channel', 'CareyRPG')} ({voice.get('niche', 'gaming')}). "
        f"Write EXACTLY in the voice of these real examples: {json.dumps(voice.get('examples', {}))}. "
        f"Rules: {json.dumps(voice.get('rules', []))}.\n\n"
        f"Video transcript (may be truncated):\n{transcript[:6000]}\n\n"
        "Reply with ONLY a JSON object: {\"titles\": [5 options], \"tags\": [12-18 tags], "
        "\"description\": \"2 short paragraphs + timestamps placeholder\", "
        "\"pinned_comment\": \"one comment\"}")
    content = _lms_chat(prompt)
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if not m:
        raise RuntimeError(f"packager returned no JSON: {content[:200]}")
    package = json.loads(m.group(0))
    out_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"package_{job['id']}.json"
    dest.write_text(json.dumps(package, indent=2), encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": p.get("project", "careyrpg"),
        "kind": "package", "path": str(dest),
        "purpose": p.get("purpose", "video packaging"), "status": "draft",
        "titles": package.get("titles", []),
        "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_content_research(job) -> None:
    """v3.1 §2: outlier CSV (manual export) -> ranked video ideas artifact."""
    import csv
    p = json.loads(job["payload"])
    rows = []
    with open(p["csv_path"], newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            norm = {k.lower().strip(): (v or "").strip() for k, v in row.items()}
            def num(*keys):
                for k in keys:
                    try:
                        return float(norm.get(k, "").replace("x", "").replace(",", ""))
                    except ValueError:
                        continue
                return 0.0
            rows.append({"title": norm.get("title") or norm.get("video") or "?",
                         "multiplier": num("multiplier", "outlier", "x"),
                         "vph": num("vph", "views per hour", "viewsperhour")})
    rows.sort(key=lambda r: (r["multiplier"], r["vph"]), reverse=True)
    top = rows[: int(p.get("top", 5))]
    md = [f"# This week's video ideas — {datetime.now():%Y-%m-%d}",
          "", "Ranked by outlier multiplier, then views/hour:", ""]
    md += [f"{i+1}. **{r['title']}** — {r['multiplier']:g}x, {r['vph']:g} VPH"
           for i, r in enumerate(top)]
    out_dir = ROOT / "artifacts" / p.get("project", "careyrpg") / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"ideas_{job['id']}.md"
    dest.write_text("\n".join(md), encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": p.get("project", "careyrpg"),
        "kind": "ideas", "path": str(dest), "purpose": "weekly topic research",
        "status": "draft", "created_at": datetime.now(timezone.utc).isoformat()}]})


def run_export_csv(job) -> None:
    """Exports Room: dump artifacts (or jobs) to a CSV artifact."""
    import csv
    p = json.loads(job["payload"])
    what = p.get("what", "artifacts")
    if what not in ("artifacts", "jobs"):
        raise RuntimeError("export.csv payload.what must be artifacts|jobs")
    rows = api(f"/{what}?limit={int(p.get('limit', 1000))}")
    out_dir = ROOT / "artifacts" / "exports" / f"{datetime.now():%Y-%m}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{what}_{datetime.now():%Y%m%d}_{job['id']}.csv"
    if rows:
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    else:
        dest.write_text("", encoding="utf-8")
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": [{
        "job_id": job["id"], "project": "byrdhouse", "kind": "export",
        "path": str(dest), "purpose": f"{what} export", "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat()}]})


RUNNERS = {"image.generate": run_generate, "image.judge": run_judge,
           "report.daily": run_report,
           "content.thumbnail": run_content_thumbnail,
           "content.package": run_content_package,
           "content.research": run_content_research,
           "export.csv": run_export_csv}


def desired_mode(gpu: Gpu) -> str:
    """v2 §7: enter IMAGE when >=3 image jobs queued OR oldest older than 10 min;
    otherwise OPERATOR (judging happens there)."""
    queued = api("/jobs?status=queued&limit=100")
    image_jobs = [j for j in queued if j["required_mode"] == "IMAGE"]
    operator_jobs = [j for j in queued if j["required_mode"] in ("OPERATOR", "ANY")]
    if image_jobs:
        oldest = min(j["created_at"] for j in image_jobs)
        age_min = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(oldest)).total_seconds() / 60
        if len(image_jobs) >= 3 or age_min > 10 or not operator_jobs:
            return "IMAGE"
    if operator_jobs:
        return "OPERATOR"
    return gpu.mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=5.0)
    args = ap.parse_args()
    global GPU_ENABLED
    GPU_ENABLED = not args.no_gpu

    gpu = Gpu(enabled=GPU_ENABLED)
    log(f"{WORKER_ID} starting — router {ROUTER}, mode {gpu.mode}, gpu={'on' if gpu.enabled else 'off'}")
    last_beat = 0.0
    idle_streak = 0

    while True:
        try:
            if time.time() - last_beat > 30:
                beat = api("/workers/heartbeat", {"id": WORKER_ID, "host": socket.gethostname(),
                                                  "caps": CAPS, "mode": gpu.mode})
                last_beat = time.time()
                req = beat.get("requested_mode")
                if req and req != gpu.mode:  # dashboard/manual mode request
                    gpu.switch(req)
                    api("/mode", {"mode": ""})  # clear the request

            gpu.switch(desired_mode(gpu))
            job = api("/jobs/claim", {"worker_id": WORKER_ID, "caps": CAPS, "mode": gpu.mode})
            if not job or not job.get("id"):
                idle_streak += 1
                if args.once and idle_streak >= 2:
                    log("queue drained — exiting (--once)")
                    return
                time.sleep(args.poll)
                continue
            idle_streak = 0

            log(f"claimed {job['id']} ({job['type']})")
            api(f"/jobs/{job['id']}/status", {"status": "running"})
            runner = RUNNERS.get(job["type"])
            try:
                if runner is None:
                    raise RuntimeError(f"no runner for job type {job['type']}")
                runner(job)
                api(f"/jobs/{job['id']}/status", {"status": "done"})
                log(f"done {job['id']}")
            except SystemExit as e:  # byrdimage.die()
                api(f"/jobs/{job['id']}/status", {"status": "failed", "error": str(e.code)})
                log(f"FAILED {job['id']}: {e.code}")
            except Exception as e:
                api(f"/jobs/{job['id']}/status", {"status": "failed", "error": str(e)})
                log(f"FAILED {job['id']}: {e}")
        except KeyboardInterrupt:
            log("stopping")
            return
        except Exception as e:
            log(f"loop error ({e}) — retrying in 10s")
            time.sleep(10)


if __name__ == "__main__":
    main()
