"""
ByrdHouse Router API v1 (Blueprint v2 §5 + §6).

The belt: one SQLite database (jobs, artifacts, recipes, projects, workers,
events) behind a small, boring HTTP API. Workers PULL; nothing pushes into a
worker. Every state change writes an event. Also serves the dashboard.

Blueprint v2 names FastAPI; this implements the same contract with only the
Python standard library so neither machine needs a pip install (decision
logged in docs/DECISIONS.md). Swap frameworks later without changing routes.

Run:  python router/router.py          (reads BYRDHOUSE_ROOT)
Port: from services.router in byrdhouse.config.json (default 8787).

Endpoints (v2 §6):                                          access
  GET  /health                                              open
  GET  /status              status.json + live queue counts open
  POST /jobs                create job {idempotency_key?}    token
  GET  /jobs?status=&project=&type=                         open
  POST /jobs/claim          {worker_id,caps,mode}           token
  POST /jobs/<id>/status    {status:running|done|failed}    token
  POST /jobs/<id>/requeue   retry dead/cancelled/stuck job  token
  POST /jobs/<id>/cancel    cancel a queued job             token
  POST /jobs/<id>/artifacts {artifacts:[card,...]}          token
  GET  /artifacts?project=&status=&id=&limit=               open
  GET  /artifacts/<id>/file image bytes (local or preview)  open
  POST /artifacts/<id>/file upload preview bytes (worker)   token
  POST /artifacts/<id>/review {action:approve|reject|judge} token
  POST /artifacts/<id>/refine {strength,scale,prompt,lora}   token
  GET  /recipes             list recipe files               open
  POST /chat                {messages:[...]} -> operator    token
  POST /workers/heartbeat   {id,caps,mode,vram}             token
  GET  /mode                requested + worker modes        open
  POST /mode                {mode} request a shift          token
  GET  /learn?by=recipe|checkpoint|palette|lighting         open
  GET  /events?limit=                                       open
  GET  /reports/daily                                       open
"""

import json
import os
import re
import secrets
import sqlite3
import string
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
CFG = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
TOKEN = CFG["auth"]["admin_token"]
DB_PATH = ROOT / "db" / "byrdhouse.db"
DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
PREVIEWS = ROOT / "artifacts" / "_previews"  # worker-uploaded copies for the dashboard
REFERENCES = ROOT / "references"  # founder-loved thumbnails the judge scores against
SOURCES = ROOT / "artifacts" / "_sources"  # dashboard-uploaded real source images

JOB_TYPES = {
    "image.generate", "image.judge", "image.refine", "image.upscale", "image.faceswap",
    "video.i2v",
    "memory.save", "memory.import", "report.daily",
    "export.csv", "export.zip", "backup.nightly",
    "game.godot_task", "code.task",
}
REVIEW_TYPES = {"image.generate", "image.refine", "image.upscale", "image.faceswap",
                "video.i2v"}  # done -> needs_review

# The worker heartbeats from a dedicated thread (worker.py) every ~30s even
# while a long generation runs, so silence now genuinely means a dead process
# and the thresholds can be tight without reaping healthy long jobs.
WORKER_OFFLINE_SEC = 120    # no heartbeat for 2 min (4 missed beats) -> offline
JOB_REAP_SEC = 300          # claimed/running 5 min past last heartbeat -> failure path

# Router build identity — the belt's answer to "are my machines on the same
# code?". API_VERSION is the wire contract; build_sha is the exact commit. Both
# ride every heartbeat/health response so drift between MINI, GAMING and the
# dashboard is visible instead of silent (they all sync from one git repo).
API_VERSION = "1"


def repo_build(start=None):
    """Best-effort git build id (short SHA + branch), stdlib-only, no subprocess
    and no network — reads .git directly so it works on both machines exactly as
    they are synced. Returns {'sha','branch'}; unknowns off a git tree."""
    try:
        p = Path(start or __file__).resolve()
        for d in [p] + list(p.parents):
            gitdir = d / ".git"
            if not gitdir.is_dir():
                continue
            head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
            if not head.startswith("ref:"):
                return {"sha": head[:12], "branch": "detached"}
            ref = head[4:].strip()
            branch = ref.rsplit("/", 1)[-1]
            reffile = gitdir / ref
            if reffile.exists():
                return {"sha": reffile.read_text(encoding="utf-8").strip()[:12], "branch": branch}
            packed = gitdir / "packed-refs"
            if packed.exists():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")) and line.endswith(ref):
                        return {"sha": line.split()[0][:12], "branch": branch}
            return {"sha": "unknown", "branch": branch}
    except Exception:
        pass
    return {"sha": "unknown", "branch": "unknown"}


BUILD = repo_build()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, project_id TEXT,
  recipe_id TEXT, recipe_version INTEGER,
  payload JSON NOT NULL, priority INTEGER DEFAULT 5,
  required_mode TEXT DEFAULT 'ANY', required_caps TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  worker_id TEXT, attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 2,
  created_at TEXT, claimed_at TEXT, finished_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS artifacts(
  id TEXT PRIMARY KEY, job_id TEXT, project_id TEXT,
  kind TEXT, path TEXT, sha256 TEXT,
  meta JSON, score REAL, judge_notes TEXT, tags TEXT,
  status TEXT DEFAULT 'draft', created_at TEXT);
CREATE TABLE IF NOT EXISTS recipes(
  id TEXT, version INTEGER, kind TEXT,
  spec JSON, rubric JSON, notes TEXT, created_at TEXT,
  PRIMARY KEY(id, version));
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT, bible_path TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS workers(
  id TEXT PRIMARY KEY, host TEXT, caps TEXT, mode TEXT,
  last_heartbeat TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT,
  action TEXT, subject TEXT, detail JSON, ok INTEGER);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
"""

_local = threading.local()


# Additive migrations for DBs that already exist on the machines. Each entry is
# idempotent (guarded by a column/index check) so re-running is a no-op — the
# belt can evolve its schema without a wipe. New columns/indexes go here.
MIGRATIONS = [
    ("jobs", "idempotency_key", "ALTER TABLE jobs ADD COLUMN idempotency_key TEXT"),
    ("jobs", "parent_id",       "ALTER TABLE jobs ADD COLUMN parent_id TEXT"),
    ("jobs", "run_after",       "ALTER TABLE jobs ADD COLUMN run_after TEXT"),
    ("workers", "build_sha",    "ALTER TABLE workers ADD COLUMN build_sha TEXT"),
    ("workers", "api_version",  "ALTER TABLE workers ADD COLUMN api_version TEXT"),
    ("workers", "gpu",          "ALTER TABLE workers ADD COLUMN gpu TEXT"),
]
INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idem ON jobs(idempotency_key)"
    " WHERE idempotency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_art_job ON artifacts(job_id)",
]


def migrate(conn):
    for table, col, ddl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(ddl)
    for ddl in INDEXES:
        conn.execute(ddl)
    conn.commit()


def db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        migrate(conn)
        _local.conn = conn
    return _local.conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    ts = format(int(time.time() * 1000), "x")
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}_{ts}{rand}"


def live_workers(cols="*"):
    """Worker rows with status computed from heartbeat age (the dashboard has
    no logic — liveness is decided here)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=WORKER_OFFLINE_SEC)).isoformat()
    out = []
    for r in db().execute(f"SELECT {cols} FROM workers"):
        w = dict(r)
        if "last_heartbeat" in w:
            w["status"] = "online" if (w["last_heartbeat"] or "") > cutoff else "offline"
        out.append(w)
    return out


def worker_online(worker_id):
    """True if this specific worker has heartbeated within the liveness window.
    The fence for requeue: a live worker still owns its job."""
    if not worker_id:
        return False
    row = db().execute("SELECT last_heartbeat FROM workers WHERE id=?", (worker_id,)).fetchone()
    if not row or not row["last_heartbeat"]:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=WORKER_OFFLINE_SEC)).isoformat()
    return row["last_heartbeat"] > cutoff


def fail_job(job, err, actor):
    """The one retry->dead path (v2 §3): requeue while attempts remain, else dead."""
    if job["attempts"] < job["max_attempts"]:
        db().execute("UPDATE jobs SET status='queued', worker_id=NULL, error=? WHERE id=?",
                     (err, job["id"]))
    else:
        db().execute("UPDATE jobs SET status='dead', finished_at=?, error=? WHERE id=?",
                     (now(), err, job["id"]))
    db().commit()
    event(actor, "job.failed", job["id"], {"error": err}, ok=False)


def reaper():
    """Requeue jobs stuck on a dead worker. A job is stuck when it is
    claimed/running but its worker has not heartbeated for JOB_REAP_SEC —
    long enough that a slow generation can't be mistaken for a crash."""
    while True:
        time.sleep(60)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=JOB_REAP_SEC)).isoformat()
            stuck = db().execute(
                "SELECT j.* FROM jobs j LEFT JOIN workers w ON w.id=j.worker_id"
                " WHERE j.status IN ('claimed','running')"
                " AND j.claimed_at < ? AND COALESCE(w.last_heartbeat,'') < ?",
                (cutoff, cutoff)).fetchall()
            for job in stuck:
                fail_job(job, f"reaped: worker {job['worker_id']} silent > {JOB_REAP_SEC}s", "reaper")
        except Exception as e:
            print(f"[router] reaper error: {e}")


def job_row(jid):
    return db().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()


# ── ComfyUI proxy: live node info + installed models for dashboard controls ──
_comfy_cache = {}
_comfy_cache_ts = 0
COMFY_CACHE_SEC = 300  # re-fetch every 5 min

def _comfy_fetch(endpoint):
    comfy = CFG["services"]["comfyui"].rstrip("/")
    try:
        with urllib.request.urlopen(f"{comfy}{endpoint}", timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def _comfy_nodes():
    global _comfy_cache, _comfy_cache_ts
    if time.time() - _comfy_cache_ts < COMFY_CACHE_SEC and _comfy_cache:
        return _comfy_cache
    raw = _comfy_fetch("/object_info")
    if not raw:
        return {"error": "ComfyUI unreachable", "nodes": {}}
    nodes = {}
    for cls in ("KSampler", "KSamplerAdvanced", "CheckpointLoaderSimple",
                "LoraLoader", "EmptyLatentImage", "CLIPTextEncode",
                "IPAdapterAdvanced", "IPAdapterUnifiedLoader"):
        info = raw.get(cls)
        if not info:
            continue
        inputs = {}
        for name, spec in info.get("input", {}).get("required", {}).items():
            if isinstance(spec, list) and len(spec) >= 1:
                if isinstance(spec[0], list):
                    inputs[name] = {"type": "enum", "options": spec[0]}
                    if len(spec) > 1 and isinstance(spec[1], dict):
                        inputs[name]["default"] = spec[1].get("default")
                elif isinstance(spec[0], str):
                    entry = {"type": spec[0]}
                    if len(spec) > 1 and isinstance(spec[1], dict):
                        for k in ("default", "min", "max", "step"):
                            if k in spec[1]:
                                entry[k] = spec[1][k]
                    inputs[name] = entry
        nodes[cls] = inputs
    _comfy_cache = {"nodes": nodes}
    _comfy_cache_ts = time.time()
    return _comfy_cache

def _comfy_models(folder):
    data = _comfy_fetch(f"/models/{folder}")
    if data is None:
        return {"error": "ComfyUI unreachable", "models": []}
    return {"folder": folder, "models": data if isinstance(data, list) else []}


LEARN_DIMS = {  # dimension -> how to pull its value out of an artifact card
    "recipe":     lambda m: m.get("recipe"),
    "checkpoint": lambda m: m.get("checkpoint"),
    "palette":    lambda m: (m.get("vary_picks") or {}).get("palette"),
    "lighting":   lambda m: (m.get("vary_picks") or {}).get("lighting"),
    "project":    lambda m: m.get("project"),
}


def learn_projection(dim, min_samples=1):
    """Approval-rate ranking over a feature we already record. Only human
    verdicts (approved/rejected) count as label; drafts add to 'seen' for
    context. This is the belt's own reinforcement signal, harvested."""
    getter = LEARN_DIMS.get(dim, LEARN_DIMS["recipe"])
    buckets = {}
    for r in db().execute("SELECT status, score, meta FROM artifacts"):
        try:
            meta = json.loads(r["meta"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        key = getter(meta)
        if not key:
            continue
        b = buckets.setdefault(str(key), {"value": str(key), "approved": 0,
                                          "rejected": 0, "seen": 0, "_score_sum": 0.0,
                                          "_score_n": 0})
        b["seen"] += 1
        if r["status"] == "approved":
            b["approved"] += 1
        elif r["status"] == "rejected":
            b["rejected"] += 1
        if r["score"] is not None:
            b["_score_sum"] += r["score"]; b["_score_n"] += 1
    out = []
    for b in buckets.values():
        labeled = b["approved"] + b["rejected"]
        b["labeled"] = labeled
        b["approval_rate"] = round(b["approved"] / labeled, 3) if labeled else None
        b["avg_score"] = round(b["_score_sum"] / b["_score_n"], 2) if b["_score_n"] else None
        del b["_score_sum"], b["_score_n"]
        out.append(b)
    # best-approved first; unlabeled (no verdict yet) sink to the bottom
    out.sort(key=lambda x: (x["approval_rate"] is not None, x["approval_rate"] or 0,
                            x["avg_score"] or 0), reverse=True)
    return {"dimension": dim, "buckets": out,
            "note": "approval_rate = approved / (approved+rejected); needs verdicts to be meaningful"}


# ── chat tools: the operator model can act on the belt through its own
#    audited operations (bot-ladder rung A1 — same endpoints, same events).
#    The coming MCP roster plugs into this same loop. ─────────────────────────
CHAT_TOOLS = [
    {"type": "function", "function": {
        "name": "get_status", "description": "Live queue counts and worker liveness.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "list_artifacts",
        "description": "Recent artifacts with id, kind, score, status, purpose.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "optional filter: draft|needs_review|approved|rejected"},
            "limit": {"type": "integer", "description": "max rows, default 8"}}}}},
    {"type": "function", "function": {
        "name": "queue_image",
        "description": "Queue an image generation on the belt (freeform recipe). "
                       "Use when the founder asks for an image to be made.",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "what to generate"},
            "project": {"type": "string", "description": "default careyrpg"},
            "aspect": {"type": "string", "description": "16:9|9:16|1:1|2:3|3:2|21:9"}},
            "required": ["prompt"]}}},
    {"type": "function", "function": {
        "name": "refine_image",
        "description": "Refine an existing artifact: mode 'upscale' = hi-res "
                       "polish of a good image, 'riff' = variations near it. "
                       "Use list_artifacts first to get the artifact id.",
        "parameters": {"type": "object", "properties": {
            "artifact_id": {"type": "string"},
            "mode": {"type": "string", "description": "upscale | riff"}},
            "required": ["artifact_id"]}}},
    {"type": "function", "function": {
        "name": "what_works",
        "description": "Approval-rate ranking of what the founder actually approves, "
                       "by recipe/checkpoint/palette/lighting. Use to recommend settings.",
        "parameters": {"type": "object", "properties": {
            "by": {"type": "string", "description": "recipe|checkpoint|palette|lighting|project"}}}}},
    {"type": "function", "function": {
        "name": "recent_events",
        "description": "Tail of the belt event log (what happened lately).",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "max rows, default 12"}}}}},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for references, viral thumbnails, or facts "
                       "about a game before generating. Returns title/url/snippet rows. "
                       "(In-app equivalent of the brave-search MCP the bot uses in Cherry Studio.)",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "what to search for"},
            "limit": {"type": "integer", "description": "max results, default 5"}},
            "required": ["query"]}}},
]


def run_chat_tool(name, args, actor):
    if name == "get_status":
        counts = {r["status"]: r["n"] for r in db().execute(
            "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
        return {"queue": counts, "workers": live_workers("id,mode,last_heartbeat")}
    if name == "list_artifacts":
        sql, a = ("SELECT id,kind,score,status,project_id,meta FROM artifacts"
                  " WHERE rowid IN (SELECT MAX(rowid) FROM artifacts"
                  " GROUP BY job_id, COALESCE(path, id))"), []
        if args.get("status"):
            sql += " AND status=?"; a.append(args["status"])
        sql += " ORDER BY created_at DESC LIMIT ?"
        a.append(min(int(args.get("limit", 8)), 15))
        out = []
        for r in db().execute(sql, a):
            meta = json.loads(r["meta"] or "{}")
            out.append({"id": r["id"], "kind": r["kind"], "score": r["score"],
                        "status": r["status"], "purpose": meta.get("purpose", "")[:80]})
        return out
    if name == "queue_image":
        jid = new_id("job")
        payload = {"recipe": "freeform", "slots": {"prompt": str(args["prompt"])[:500]},
                   "project": args.get("project", "careyrpg"),
                   "purpose": f"chat request: {str(args['prompt'])[:80]}"}
        if args.get("aspect"):
            payload["aspect"] = args["aspect"]
        db().execute(
            "INSERT INTO jobs(id,type,project_id,payload,priority,required_mode,"
            "required_caps,status,max_attempts,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (jid, "image.generate", payload["project"], json.dumps(payload), 5,
             "IMAGE", json.dumps(["comfyui"]), "queued", 2, now()))
        db().commit()
        event(actor, "job.create", jid, {"type": "image.generate", "via": "chat-tool"})
        return {"queued": jid, "note": "it will appear in the Image Studio when done"}
    if name == "refine_image":
        mode = args.get("mode", "upscale")
        opts = ({"strength": 0.3, "scale": 2.0} if mode == "upscale"
                else {"strength": 0.55, "scale": 1.0, "batch": 4})
        result, code = create_refine_job(str(args.get("artifact_id", "")), opts, actor)
        return result
    if name == "what_works":
        return learn_projection(args.get("by", "recipe"))["buckets"][:10]
    if name == "recent_events":
        return [dict(r) for r in db().execute(
            "SELECT ts,actor,action,subject FROM events ORDER BY id DESC LIMIT ?",
            (min(int(args.get("limit", 12)), 20),))]
    if name == "web_search":
        search = (CFG.get("services", {}).get("search") or "").rstrip("/")
        if not search or search.startswith("CHANGE_ME"):
            return {"error": "web_search not configured — set services.search to a JSON "
                             "search endpoint (e.g. a local SearXNG or a brave-search proxy) "
                             "returning {\"results\":[{title,url,snippet}]}. In Cherry Studio "
                             "the bot uses the brave-search MCP for this instead."}
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "web_search needs a query"}
        n = min(int(args.get("limit", 5)), 10)
        try:
            # &format=json is SearXNG's opt-in for a JSON body instead of the
            # HTML results page; harmless for a brave-search-style proxy too.
            url = f"{search}?q={quote(query)}&n={n}&format=json"
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read().decode())
            results = data.get("results", data) if isinstance(data, dict) else data
            return results[:n] if isinstance(results, list) else results
        except Exception as e:
            return {"error": f"web_search failed: {e}"}
    return {"error": f"unknown tool {name}"}


def create_refine_job(aid, body, actor):
    """One path for refine jobs, shared by POST /artifacts/<id>/refine and
    the chat refine_image tool. Returns (response_dict, http_code)."""
    art = db().execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
    if not art:
        return {"error": "no such artifact"}, 404
    if not art["path"]:
        return {"error": "artifact has no file path to refine"}, 400
    meta = json.loads(art["meta"] or "{}")
    jid = new_id("job")
    payload = {
        "source_artifact": aid, "source_path": art["path"],
        "project": art["project_id"] or "sandbox",
        "purpose": body.get("purpose") or f"refine of {aid}",
        "strength": float(body.get("strength", 0.4)),
        "scale": float(body.get("scale", 1.6)),
        "batch": int(body.get("batch", 1)),
    }
    for k in ("prompt", "negative", "checkpoint", "lora"):
        if body.get(k):
            payload[k] = body[k]
    db().execute(
        "INSERT INTO jobs(id,type,project_id,payload,priority,required_mode,"
        "required_caps,status,max_attempts,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (jid, "image.refine", payload["project"], json.dumps(payload), 5,
         "IMAGE", json.dumps(["comfyui"]), "queued", 2, now()))
    db().commit()
    event(actor, "job.create", jid,
          {"type": "image.refine", "source": aid,
           "strength": payload["strength"], "scale": payload["scale"]})
    return {"id": jid, "status": "queued", "source": aid,
            "recipe": meta.get("recipe")}, 201


# Tools that mutate belt state (create jobs). Read tools are unbounded within
# the round budget; writes are capped per chat request so one model turn can't
# spawn a flood of jobs. Confirmation/destructive-action gating comes before the
# roster grows to code/file/publish tools (see docs/BELT.md security section).
WRITE_TOOLS = {"queue_image", "refine_image"}
MAX_WRITES_PER_CHAT = 3


def chat_tool_loop(lms, model, convo, actor, max_rounds=4):
    """OpenAI-style function-calling loop against LM Studio. Models without
    tool support just answer normally (tools retried off on rejection)."""
    actions, use_tools, writes = [], True, 0
    for _ in range(max_rounds):
        payload = {"model": model, "temperature": 0.7, "max_tokens": 700,
                   "messages": convo}
        if use_tools:
            payload["tools"] = CHAT_TOOLS
        try:
            req = urllib.request.Request(
                f"{lms}/chat/completions", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                msg = json.loads(r.read().decode())["choices"][0]["message"]
        except Exception as e:
            if use_tools:  # model/server rejects the tools param — go plain
                use_tools = False
                continue
            return "", actions, f"operator model failed: {e}"
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or "", actions, None
        convo.append(msg)
        for call in calls[:4]:
            fn = call.get("function", {})
            fname = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if fname in WRITE_TOOLS:
                writes += 1
                if writes > MAX_WRITES_PER_CHAT:
                    result = {"error": f"mutation budget reached "
                              f"({MAX_WRITES_PER_CHAT} per request) — ask again to do more"}
                    actions.append({"tool": fname, "args": args, "blocked": True})
                    convo.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                  "content": json.dumps(result)})
                    continue
            result = run_chat_tool(fname, args, actor)
            actions.append({"tool": fname, "args": args})
            convo.append({"role": "tool", "tool_call_id": call.get("id", ""),
                          "content": json.dumps(result)[:4000]})
    return "(stopped after several tool rounds)", actions, None


def event(actor, action, subject, detail=None, ok=True):
    db().execute(
        "INSERT INTO events(ts,actor,action,subject,detail,ok) VALUES(?,?,?,?,?,?)",
        (now(), actor, action, subject, json.dumps(detail or {}), 1 if ok else 0))
    db().commit()
    if action.startswith(("job.", "mode.")):  # live console trace of state transitions
        print(f"[router] {action} {subject} ({actor})"
              + (f" {detail}" if detail and not ok else ""), flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "ByrdHouseRouter/1"

    def log_message(self, fmt, *args):
        pass  # events table is the log

    # ── plumbing ─────────────────────────────────────────────────────────────
    def _send(self, obj, code=200, content_type="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, indent=1).encode()
        if content_type.startswith(("application/json", "text/")) and "charset" not in content_type:
            content_type += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _authed(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _actor(self) -> str:
        return self.headers.get("X-Actor", "api")

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path.rstrip("/") or "/"

        if path == "/health":
            return self._send({"ok": True, "ts": now(), "api_version": API_VERSION,
                               "build_sha": BUILD["sha"], "branch": BUILD["branch"]})

        if path == "/favicon.ico":
            return self._send(b"", content_type="image/x-icon")

        if path == "/status":
            status = {}
            sj = ROOT / "status.json"
            if sj.exists():
                status = json.loads(sj.read_text(encoding="utf-8-sig"))
            counts = {r["status"]: r["n"] for r in db().execute(
                "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
            workers = live_workers()
            router_build = {"sha": BUILD["sha"], "branch": BUILD["branch"],
                            "api_version": API_VERSION}
            # Drift: any ONLINE worker on a different commit or API version than
            # the router is a silent-split hazard (press a button, half the code
            # is missing). Only online workers count — an offline box is stale by
            # definition and shown as such elsewhere.
            drift = []
            for w in workers:
                if w.get("status") != "online":
                    continue
                wsha, wver = w.get("build_sha"), w.get("api_version")
                if wsha and wsha != BUILD["sha"]:
                    drift.append({"worker": w["id"], "issue": "commit_mismatch",
                                  "worker_sha": wsha, "router_sha": BUILD["sha"]})
                if wver and wver != API_VERSION:
                    drift.append({"worker": w["id"], "issue": "api_version_mismatch",
                                  "worker_api": wver, "router_api": API_VERSION})
            return self._send({"machine": status, "queue": counts, "workers": workers,
                               "router": router_build, "drift": drift})

        if path == "/jobs":
            sql, args = "SELECT * FROM jobs", []
            conds = []
            for col, key in (("status", "status"), ("project_id", "project"), ("type", "type")):
                if key in q:
                    conds.append(f"{col}=?"); args.append(q[key])
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY created_at DESC LIMIT ?"
            args.append(int(q.get("limit", 100)))
            return self._send([dict(r) for r in db().execute(sql, args)])

        if path == "/artifacts":
            # One card per output: retried jobs used to register duplicate rows
            # for the same PNG, so show only the latest row per (job_id, path).
            # Joined job timing rides along so cards can show queue->done times.
            sql, args = (
                "SELECT a.*, j.created_at AS job_queued_at, j.claimed_at AS job_claimed_at,"
                " j.finished_at AS job_finished_at,"
                " CAST(ROUND((julianday(j.finished_at) - julianday(j.claimed_at)) * 86400)"
                "   AS INTEGER) AS gen_seconds"
                " FROM artifacts a LEFT JOIN jobs j ON j.id = a.job_id"
                " WHERE a.rowid IN"
                " (SELECT MAX(rowid) FROM artifacts GROUP BY job_id, COALESCE(path, id))"), []
            conds = []
            for col, key in (("a.status", "status"), ("a.project_id", "project"), ("a.id", "id")):
                if key in q:
                    conds.append(f"{col}=?"); args.append(q[key])
            if conds:
                sql += " AND " + " AND ".join(conds)
            sql += " ORDER BY a.created_at DESC LIMIT ?"
            args.append(int(q.get("limit", 50)))
            return self._send([dict(r) for r in db().execute(sql, args)])

        m = re.fullmatch(r"/artifacts/([\w.-]+)/file", path)
        if m:
            row = db().execute("SELECT path FROM artifacts WHERE id=?", (m.group(1),)).fetchone()
            if row and row["path"] and Path(row["path"]).exists():
                data = Path(row["path"]).read_bytes()
                ctype = "image/png" if row["path"].endswith(".png") else "application/octet-stream"
                return self._send(data, content_type=ctype)
            # artifact files live on the worker's disk — fall back to the
            # preview copy the worker uploaded at registration time
            cached = PREVIEWS / f"{m.group(1)}.png"
            if row and cached.exists():
                return self._send(cached.read_bytes(), content_type="image/png")
            return self._send({"error": "file not on this host"}, 404)

        if path == "/references":
            out = []
            if REFERENCES.exists():
                for p in sorted(REFERENCES.rglob("*.png")) + sorted(REFERENCES.rglob("*.jpg")):
                    out.append({"tag": p.parent.name if p.parent != REFERENCES else "general",
                                "name": p.name})
            tag = q.get("tag", "").lower()
            if tag:
                out = [r for r in out if r["tag"].lower() == tag]
            return self._send(out)

        m = re.fullmatch(r"/references/([\w.-]+)/([\w. -]+)/file", path)
        if m:
            f = (REFERENCES / m.group(1) / m.group(2)).resolve()
            if str(f).startswith(str(REFERENCES.resolve())) and f.is_file():
                ctype = "image/png" if f.suffix == ".png" else "image/jpeg"
                return self._send(f.read_bytes(), content_type=ctype)
            return self._send({"error": "no such reference"}, 404)

        if path == "/profiles":
            out = []
            profiles_dir = ROOT / "profiles"
            if profiles_dir.is_dir():
                for pdir in sorted(profiles_dir.iterdir()):
                    pfile = pdir / "profile.json"
                    if not pfile.exists():
                        continue
                    try:
                        p = json.loads(pfile.read_text(encoding="utf-8-sig"))
                        refs_dir = pdir / "references"
                        photos = [f.name for f in refs_dir.iterdir()
                                  if f.suffix.lower() in (".jpg", ".jpeg", ".png")] if refs_dir.is_dir() else []
                        out.append({"id": p.get("id", pdir.name),
                                    "display_name": p.get("display_name", pdir.name),
                                    "references": len(photos),
                                    "has_references": len(photos) > 0,
                                    "preferences": p.get("preferences", {})})
                    except Exception:
                        continue
            return self._send(out)

        if path == "/recipes":
            out = []
            for p in sorted((ROOT / "recipes").glob("*.v*.json")):
                try:
                    r = json.loads(p.read_text(encoding="utf-8-sig"))
                    entry = {"id": r["id"], "version": r["version"], "kind": r.get("kind"),
                             "slots": list(dict.fromkeys(
                                 re.findall(r"\{(\w+)\}", r.get("template", "")))),
                             "vary": list(r.get("vary", {}).keys()), "file": p.name,
                             "workflow": r.get("workflow"),
                             "note": r.get("_note", "")}
                    if r.get("subject_profile"):
                        entry["subject_profile"] = r["subject_profile"]
                    if r.get("category"):
                        entry["category"] = r["category"]
                    if r.get("runner"):
                        entry["runner"] = r["runner"]
                    if r.get("target_presets"):
                        entry["target_presets"] = [
                            {"id": key, "label": value.get("label", key)}
                            for key, value in r["target_presets"].items()
                        ]
                    out.append(entry)
                except Exception:
                    continue
            return self._send(out)

        # ── ComfyUI proxy: expose live node info + installed models ──────────
        # The dashboard renders real ComfyUI controls (sampler, scheduler,
        # steps, CFG, checkpoints, LoRAs) from the worker's actual install
        # instead of hardcoded dropdowns. Cached until the router restarts.
        if path == "/comfy/nodes":
            return self._send(_comfy_nodes())

        if path.startswith("/comfy/models/"):
            folder = path.split("/comfy/models/", 1)[1].strip("/")
            if not re.fullmatch(r"[\w.-]+", folder):
                return self._send({"error": "bad folder name"}, 400)
            return self._send(_comfy_models(folder))

        if path == "/mode":
            req = db().execute("SELECT value FROM kv WHERE key='requested_mode'").fetchone()
            return self._send({"requested": req["value"] if req else None,
                               "workers": live_workers("id,mode,last_heartbeat")})

        if path == "/stats":
            week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            kinds = {r["kind"] or "?": r["n"] for r in db().execute(
                "SELECT kind, COUNT(*) n FROM artifacts GROUP BY kind")}
            return self._send({
                "artifacts_total": db().execute("SELECT COUNT(*) n FROM artifacts").fetchone()["n"],
                "artifacts_week": db().execute(
                    "SELECT COUNT(*) n FROM artifacts WHERE created_at>?", (week,)).fetchone()["n"],
                "by_kind": kinds,
                "jobs_done_week": db().execute(
                    "SELECT COUNT(*) n FROM jobs WHERE finished_at>?", (week,)).fetchone()["n"],
                "avg_score": db().execute(
                    "SELECT ROUND(AVG(score),2) s FROM artifacts WHERE score IS NOT NULL").fetchone()["s"],
                "approved": db().execute(
                    "SELECT COUNT(*) n FROM artifacts WHERE status='approved'").fetchone()["n"],
            })

        if path == "/learn":
            # The learn loop (reverse-engineered RLHF): every approve/reject the
            # founder makes is a labeled datapoint over features we already store
            # (recipe, checkpoint, palette, lighting). Project them into
            # approval-rate rankings so the belt can tell — and later bias toward —
            # what actually gets approved. Pure read over existing data.
            dim = q.get("by", "recipe")
            return self._send(learn_projection(dim))

        if path == "/events":
            rows = db().execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                                (int(q.get("limit", 50)),))
            return self._send([dict(r) for r in rows])

        if path == "/reports/daily":
            since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            jobs = [dict(r) for r in db().execute(
                "SELECT type,status,COUNT(*) n FROM jobs WHERE created_at>? GROUP BY type,status", (since,))]
            arts = db().execute("SELECT COUNT(*) n, AVG(score) avg_score FROM artifacts WHERE created_at>?",
                                (since,)).fetchone()
            ev = [dict(r) for r in db().execute(
                "SELECT action,COUNT(*) n,SUM(ok=0) failed FROM events WHERE ts>? GROUP BY action ORDER BY n DESC", (since,))]
            md = [f"# ByrdHouse daily report — {datetime.now():%Y-%m-%d}", "", "## Jobs (24h)"]
            md += [f"- {j['type']} {j['status']}: {j['n']}" for j in jobs] or ["- none"]
            md += ["", f"## Artifacts: {arts['n']} created, avg score {arts['avg_score'] or 'n/a'}", "", "## Events"]
            md += [f"- {e['action']}: {e['n']} ({e['failed'] or 0} failed)" for e in ev] or ["- none"]
            return self._send({"jobs": jobs, "artifacts": dict(arts), "events": ev,
                               "markdown": "\n".join(md)})

        # dashboard static files
        if path == "/":
            path = "/index.html"
        f = (DASHBOARD / path.lstrip("/")).resolve()
        if str(f).startswith(str(DASHBOARD)) and f.is_file():
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                     "png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml",
                     "ico": "image/x-icon"}.get(
                f.suffix.lstrip("."), "application/octet-stream")
            return self._send(f.read_bytes(), content_type=ctype)

        self._send({"error": f"no route {path}"}, 404)

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        if not self._authed():
            return self._send({"error": "bad or missing bearer token"}, 401)
        path = urlparse(self.path).path.rstrip("/")

        m = re.fullmatch(r"/references/([\w-]+)/([\w. -]+)", path)
        if m:  # raw reference upload from the dashboard (body is image bytes)
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 20_000_000:
                return self._send({"error": "bad upload size"}, 400)
            dest = REFERENCES / m.group(1) / m.group(2)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.rfile.read(n))
            event(self._actor(), "reference.add", f"{m.group(1)}/{m.group(2)}", {"bytes": n})
            return self._send({"ok": True, "tag": m.group(1), "name": m.group(2)}, 201)

        m = re.fullmatch(r"/artifacts/([\w.-]+)/file", path)
        if m:  # raw image upload from the worker (body is bytes, not JSON)
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 20_000_000:
                return self._send({"error": "bad upload size"}, 400)
            PREVIEWS.mkdir(parents=True, exist_ok=True)
            (PREVIEWS / f"{m.group(1)}.png").write_bytes(self.rfile.read(n))
            event(self._actor(), "artifact.preview", m.group(1), {"bytes": n})
            return self._send({"ok": True}, 201)

        m = re.fullmatch(r"/sources/([\w. -]+)", path)
        if m:  # real source image uploaded from the dashboard (body is bytes)
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 20_000_000:
                return self._send({"error": "bad upload size"}, 400)
            name = m.group(1)
            project = {k: v[0] for k, v in
                       parse_qs(urlparse(self.path).query).items()}.get("project", "careyrpg")
            aid = new_id("src")
            SOURCES.mkdir(parents=True, exist_ok=True)
            dest = SOURCES / f"{aid}_{name}"
            dest.write_bytes(self.rfile.read(n))
            # A real source image is highest grade by definition — real pixels
            # beat diffused lookalikes (v3.1). Record it approved at top score so
            # it lands in the gallery and the belt can composite onto it later.
            card = {"artifact_id": aid, "job_id": None, "project": project,
                    "kind": "source", "path": str(dest), "name": name, "source": True,
                    "purpose": "uploaded source image (real pixels)",
                    "prompt": "", "slots": {}, "score": 5.0,
                    "tags": ["source"], "caption": "", "status": "approved",
                    "created_at": now()}
            db().execute(
                "INSERT OR REPLACE INTO artifacts(id,job_id,project_id,kind,path,meta,"
                "score,tags,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (aid, None, project, "source", str(dest), json.dumps(card),
                 5.0, json.dumps(["source"]), "approved", now()))
            db().commit()
            event(self._actor(), "source.upload", aid, {"bytes": n, "name": name})
            return self._send({"id": aid, "name": name, "path": str(dest),
                               "status": "approved", "score": 5.0}, 201)

        try:
            body = self._body()
        except json.JSONDecodeError:
            return self._send({"error": "invalid JSON"}, 400)

        if path == "/jobs":
            jtype = body.get("type", "")
            if jtype not in JOB_TYPES and not jtype.startswith("content."):
                return self._send({"error": f"unknown job type '{jtype}'"}, 400)
            # Idempotency: a double-tap or a network retry carrying the same key
            # returns the job already created instead of minting a duplicate.
            idem = body.get("idempotency_key")
            if idem:
                dup = db().execute(
                    "SELECT id,status FROM jobs WHERE idempotency_key=?", (idem,)).fetchone()
                if dup:
                    return self._send({"id": dup["id"], "status": dup["status"],
                                       "idempotent": True}, 200)
            jid = new_id("job")
            db().execute(
                "INSERT INTO jobs(id,type,project_id,recipe_id,recipe_version,payload,"
                "priority,required_mode,required_caps,status,max_attempts,created_at,idempotency_key)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (jid, jtype, body.get("project", "sandbox"),
                 body.get("recipe"), body.get("recipe_version"),
                 json.dumps(body.get("payload", {})), int(body.get("priority", 5)),
                 body.get("required_mode", "ANY"),
                 json.dumps(body.get("required_caps", [])),
                 "queued", int(body.get("max_attempts", 2)), now(), idem))
            db().commit()
            event(self._actor(), "job.create", jid, {"type": jtype})
            return self._send({"id": jid, "status": "queued"}, 201)

        if path == "/jobs/claim":
            wid, caps = body.get("worker_id", "?"), set(body.get("caps", []))
            mode = body.get("mode", "ANY")
            rows = db().execute(
                "SELECT * FROM jobs WHERE status='queued' AND (required_mode='ANY' OR required_mode=?)"
                " ORDER BY priority DESC, created_at ASC LIMIT 20", (mode,))
            for job in rows:
                need = set(json.loads(job["required_caps"] or "[]"))
                if not need.issubset(caps):
                    continue
                cur = db().execute(
                    "UPDATE jobs SET status='claimed', worker_id=?, claimed_at=?,"
                    " attempts=attempts+1 WHERE id=? AND status='queued'",
                    (wid, now(), job["id"]))
                db().commit()
                if cur.rowcount:
                    event(wid, "job.claim", job["id"], {"type": job["type"]})
                    return self._send(dict(db().execute(
                        "SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()))
            return self._send({"job": None}, 200)

        m = re.fullmatch(r"/jobs/([\w.-]+)/status", path)
        if m:
            jid, new_status = m.group(1), body.get("status")
            job = job_row(jid)
            if not job:
                return self._send({"error": "no such job"}, 404)
            if new_status == "running":
                db().execute("UPDATE jobs SET status='running' WHERE id=?", (jid,))
            elif new_status == "done":
                final = "needs_review" if job["type"] in REVIEW_TYPES else "done"
                db().execute("UPDATE jobs SET status=?, finished_at=? WHERE id=?",
                             (final, now(), jid))
            elif new_status == "failed":
                fail_job(job, str(body.get("error", ""))[:2000], self._actor())
                return self._send(dict(job_row(jid)))
            else:
                return self._send({"error": f"bad status '{new_status}'"}, 400)
            db().commit()
            event(self._actor(), f"job.{new_status}", jid)
            return self._send(dict(job_row(jid)))

        m = re.fullmatch(r"/jobs/([\w.-]+)/requeue", path)
        if m:
            jid = m.group(1)
            job = job_row(jid)
            if not job:
                return self._send({"error": "no such job"}, 404)
            if job["status"] not in ("dead", "cancelled", "claimed", "running"):
                return self._send({"error": f"cannot requeue a '{job['status']}' job"}, 400)
            # Fence: a claimed/running job whose worker is STILL ALIVE is really
            # executing right now. Requeuing it would hand the same work to a
            # second claim while the first keeps going — duplicate output on the
            # one GPU, racing status writes. Refuse and point at cancel. Only when
            # the owner has gone silent (crash/reboot) is an immediate requeue
            # safe; otherwise the reaper handles it after JOB_REAP_SEC.
            if job["status"] in ("claimed", "running") and worker_online(job["worker_id"]):
                return self._send(
                    {"error": f"job is {job['status']} right now on live worker "
                     f"{job['worker_id']} — it's generating. Let it finish (images "
                     f"take ~1-2 min); if the worker has crashed the job becomes "
                     f"requeueable automatically after ~5 min. Requeue is for "
                     f"dead/cancelled or crashed jobs, not live ones.",
                     "worker": job["worker_id"]}, 409)
            db().execute(
                "UPDATE jobs SET status='queued', worker_id=NULL, attempts=0,"
                " error=NULL, finished_at=NULL WHERE id=?", (jid,))
            db().commit()
            event(self._actor(), "job.requeue", jid, {"was": job["status"]})
            return self._send(dict(job_row(jid)))

        m = re.fullmatch(r"/jobs/([\w.-]+)/cancel", path)
        if m:
            jid = m.group(1)
            job = job_row(jid)
            if not job:
                return self._send({"error": "no such job"}, 404)
            if job["status"] != "queued":
                return self._send({"error": f"only queued jobs can be cancelled (this one is '{job['status']}')"}, 400)
            db().execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?", (now(), jid))
            db().commit()
            event(self._actor(), "job.cancel", jid)
            return self._send(dict(job_row(jid)))

        m = re.fullmatch(r"/jobs/([\w.-]+)/artifacts", path)
        if m:
            jid = m.group(1)
            ids = []
            for card in body.get("artifacts", []):
                aid = card.get("artifact_id") or new_id("art")
                db().execute(
                    "INSERT OR REPLACE INTO artifacts(id,job_id,project_id,kind,path,meta,"
                    "score,tags,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (aid, jid, card.get("project", "sandbox"), card.get("kind", "image"),
                     card.get("path"), json.dumps(card), card.get("score"),
                     json.dumps(card.get("tags", [])), card.get("status", "draft"),
                     card.get("created_at", now())))
                ids.append(aid)
            db().commit()
            event(self._actor(), "artifact.register", jid, {"count": len(ids)})
            return self._send({"ids": ids}, 201)

        m = re.fullmatch(r"/artifacts/([\w.-]+)/refine", path)
        if m:
            result, code = create_refine_job(m.group(1), body, self._actor())
            return self._send(result, code)

        m = re.fullmatch(r"/artifacts/([\w.-]+)/review", path)
        if m:
            aid, action = m.group(1), body.get("action")
            art = db().execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
            if not art:
                return self._send({"error": "no such artifact"}, 404)
            if action in ("approve", "reject"):
                db().execute("UPDATE artifacts SET status=? WHERE id=?",
                             ("approved" if action == "approve" else "rejected", aid))
            elif action == "judge":
                db().execute(
                    "UPDATE artifacts SET score=?, tags=?, judge_notes=? WHERE id=?",
                    (body.get("score"), json.dumps(body.get("tags", [])),
                     json.dumps({"caption": body.get("caption", ""),
                                 "notes": body.get("notes", "")}), aid))
            elif action == "unjudged":
                # score deliberately left null (no vision model) — record why so
                # the gallery can flag it for manual review, don't invent a score
                db().execute(
                    "UPDATE artifacts SET judge_notes=? WHERE id=?",
                    (json.dumps({"unjudged": body.get("reason", "no vision model")}), aid))
            else:
                return self._send({"error": f"bad action '{action}'"}, 400)
            db().commit()
            event(self._actor(), f"artifact.{action}", aid,
                  {"score": body.get("score")} if action == "judge" else None)
            return self._send(dict(db().execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()))

        if path == "/chat":
            # Live line to the operator model (LM Studio on the worker PC).
            # The dashboard has no logic: this endpoint owns model discovery,
            # the system prompt, and the GPU-mode failure story.
            msgs = body.get("messages") or []
            if not msgs:
                return self._send({"error": "messages required"}, 400)
            # Primary: the worker PC's LM Studio. Fallback: a small CPU model
            # on this machine (services.lmstudio_fallback) so chat still answers
            # while the GPU is busy generating or GAMING is off.
            endpoints = [CFG["services"]["lmstudio"].rstrip("/")]
            fb = (CFG["services"].get("lmstudio_fallback") or "").rstrip("/")
            if fb and not fb.startswith("CHANGE_ME"):
                endpoints.append(fb)
            lms, models = None, []
            for cand in endpoints:
                try:
                    with urllib.request.urlopen(f"{cand}/models", timeout=8) as r:
                        found = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
                    if found:
                        lms, models = cand, found
                        break
                except Exception:
                    continue
            if not models:
                return self._send({"error": "no model reachable — GAMING may be mid-generation "
                                            "or offline; set services.lmstudio_fallback to a "
                                            "small model on this machine for always-on chat"}, 503)
            counts = {r["status"]: r["n"] for r in db().execute(
                "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
            system = ("You are the ByrdHouse operator — the local model that also judges the "
                      "image belt. Be direct and useful; short answers unless asked to go deep. "
                      "You have TOOLS over the belt: use them to check real state or queue image "
                      "generations when the founder asks for an image. Live belt state: "
                      f"queue={json.dumps(counts)}, workers="
                      f"{[w['id'] + ':' + w['status'] for w in live_workers('id,last_heartbeat')]}.")
            convo = [{"role": "system", "content": system}] + msgs[-12:]
            actor = self._actor()
            reply, actions, err = chat_tool_loop(lms, models[0], convo, actor)
            if err:
                return self._send({"error": err}, 502)
            event(actor, "chat.ask", models[0],
                  {"chars_in": len(msgs[-1].get("content", "")), "chars_out": len(reply),
                   "tools_used": [a["tool"] for a in actions]})
            return self._send({"reply": reply, "model": models[0], "actions": actions})

        if path == "/workers/heartbeat":
            db().execute(
                "INSERT OR REPLACE INTO workers"
                "(id,host,caps,mode,last_heartbeat,status,build_sha,api_version,gpu)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (body.get("id", "?"), body.get("host", ""), json.dumps(body.get("caps", [])),
                 body.get("mode", "ANY"), now(), "online",
                 body.get("build_sha"), body.get("api_version"),
                 json.dumps(body.get("gpu")) if body.get("gpu") is not None else None))
            db().commit()
            req = db().execute("SELECT value FROM kv WHERE key='requested_mode'").fetchone()
            # Echo the router's own identity so the worker can log a drift warning
            # the moment it talks to a router built from a different commit.
            return self._send({"ok": True, "requested_mode": req["value"] if req else None,
                               "router_build_sha": BUILD["sha"], "api_version": API_VERSION})

        if path == "/mode":
            mode = body.get("mode", "").upper()
            if mode not in ("OPERATOR", "IMAGE", "VIDEO", ""):
                return self._send({"error": "mode must be OPERATOR|IMAGE|VIDEO or empty to clear"}, 400)
            if mode:
                db().execute("INSERT OR REPLACE INTO kv(key,value) VALUES('requested_mode',?)", (mode,))
            else:
                db().execute("DELETE FROM kv WHERE key='requested_mode'")
            db().commit()
            event(self._actor(), "mode.request", mode or "clear")
            return self._send({"requested": mode or None})

        self._send({"error": f"no route {path}"}, 404)


def main():
    port = urlparse(CFG["services"]["router"]).port or 8787
    if TOKEN.startswith("CHANGE_ME"):
        print("[router] WARNING: auth.admin_token is still the placeholder — set it in byrdhouse.config.json")
    db()  # create schema up front
    threading.Thread(target=reaper, daemon=True, name="reaper").start()
    event("router", "router.start", f"port {port}")
    print(f"[router] ByrdHouse router on 0.0.0.0:{port}  db={DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
