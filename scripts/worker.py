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

ROOT = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
CFG = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8"))
ROUTER = CFG["services"]["router"].rstrip("/")
TOKEN = CFG["auth"]["admin_token"]
WORKER_ID = f"worker-{socket.gethostname().lower()}"
CAPS = ["comfyui", "lmstudio"]


def api(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ROUTER}{path}", data=data, method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}", "X-Actor": WORKER_ID})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def log(msg):
    print(f"[worker {datetime.now():%H:%M:%S}] {msg}", flush=True)


class Gpu:
    """The mode ritual (v2 §7.1). With --no-gpu every switch is a no-op."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.mode = CFG["gpu"].get("default_mode", "OPERATOR")

    def _vram_used(self) -> int:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
        return int(out.strip().splitlines()[0])

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
                    used = self._vram_used()
                    if used < threshold:
                        break
                    log(f"  waiting for VRAM: {used}MB used")
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
    api(f"/jobs/{job['id']}/artifacts", {"artifacts": cards})
    for card in cards:  # v2 §7.1 step 5: auto-enqueue the judge pass
        api("/jobs", {"type": "image.judge", "project": card["project"],
                      "required_mode": "OPERATOR", "required_caps": ["lmstudio"],
                      "payload": {"artifact_id": card["artifact_id"],
                                  "path": card["path"]}})


def run_judge(job) -> None:
    p = json.loads(job["payload"])
    image_path = Path(p["path"])
    card_path = image_path.with_suffix(image_path.suffix + ".json")
    card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.exists() else dict(p)
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


RUNNERS = {"image.generate": run_generate, "image.judge": run_judge,
           "report.daily": run_report}


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

    gpu = Gpu(enabled=not args.no_gpu)
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
