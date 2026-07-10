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
  POST /jobs                create job                      token
  GET  /jobs?status=&project=&type=                         open
  POST /jobs/claim          {worker_id,caps,mode}           token
  POST /jobs/<id>/status    {status:running|done|failed}    token
  POST /jobs/<id>/artifacts {artifacts:[card,...]}          token
  GET  /artifacts?project=&status=&id=&limit=               open
  GET  /artifacts/<id>/file image bytes (if local)          open
  POST /artifacts/<id>/review {action:approve|reject|judge} token
  GET  /recipes             list recipe files               open
  POST /workers/heartbeat   {id,caps,mode,vram}             token
  GET  /mode                requested + worker modes        open
  POST /mode                {mode} request a shift          token
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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get("BYRDHOUSE_ROOT") or sys.exit("BYRDHOUSE_ROOT not set"))
CFG = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8"))
TOKEN = CFG["auth"]["admin_token"]
DB_PATH = ROOT / "db" / "byrdhouse.db"
DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"

JOB_TYPES = {
    "image.generate", "image.judge", "image.upscale", "video.i2v",
    "memory.save", "memory.import", "report.daily",
    "export.csv", "export.zip", "backup.nightly",
    "game.godot_task", "code.task",
}
REVIEW_TYPES = {"image.generate", "image.upscale", "video.i2v"}  # done -> needs_review

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


def db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _local.conn = conn
    return _local.conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    ts = format(int(time.time() * 1000), "x")
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}_{ts}{rand}"


def event(actor, action, subject, detail=None, ok=True):
    db().execute(
        "INSERT INTO events(ts,actor,action,subject,detail,ok) VALUES(?,?,?,?,?,?)",
        (now(), actor, action, subject, json.dumps(detail or {}), 1 if ok else 0))
    db().commit()


class Handler(BaseHTTPRequestHandler):
    server_version = "ByrdHouseRouter/1"

    def log_message(self, fmt, *args):
        pass  # events table is the log

    # ── plumbing ─────────────────────────────────────────────────────────────
    def _send(self, obj, code=200, content_type="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, indent=1).encode()
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
            return self._send({"ok": True, "ts": now()})

        if path == "/favicon.ico":
            return self._send(b"", content_type="image/x-icon")

        if path == "/status":
            status = {}
            sj = ROOT / "status.json"
            if sj.exists():
                status = json.loads(sj.read_text(encoding="utf-8"))
            counts = {r["status"]: r["n"] for r in db().execute(
                "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
            workers = [dict(r) for r in db().execute("SELECT * FROM workers")]
            return self._send({"machine": status, "queue": counts, "workers": workers})

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
            sql, args = "SELECT * FROM artifacts", []
            conds = []
            for col, key in (("status", "status"), ("project_id", "project"), ("id", "id")):
                if key in q:
                    conds.append(f"{col}=?"); args.append(q[key])
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY created_at DESC LIMIT ?"
            args.append(int(q.get("limit", 50)))
            return self._send([dict(r) for r in db().execute(sql, args)])

        m = re.fullmatch(r"/artifacts/([\w.-]+)/file", path)
        if m:
            row = db().execute("SELECT path FROM artifacts WHERE id=?", (m.group(1),)).fetchone()
            if row and row["path"] and Path(row["path"]).exists():
                data = Path(row["path"]).read_bytes()
                ctype = "image/png" if row["path"].endswith(".png") else "application/octet-stream"
                return self._send(data, content_type=ctype)
            return self._send({"error": "file not on this host"}, 404)

        if path == "/recipes":
            out = []
            for p in sorted((ROOT / "recipes").glob("*.v*.json")):
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                    out.append({"id": r["id"], "version": r["version"], "kind": r.get("kind"),
                                "slots": re.findall(r"\{(\w+)\}", r.get("template", "")),
                                "vary": list(r.get("vary", {}).keys()), "file": p.name})
                except Exception:
                    continue
            return self._send(out)

        if path == "/mode":
            req = db().execute("SELECT value FROM kv WHERE key='requested_mode'").fetchone()
            workers = [dict(r) for r in db().execute("SELECT id,mode,last_heartbeat FROM workers")]
            return self._send({"requested": req["value"] if req else None, "workers": workers})

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
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(
                f.suffix.lstrip("."), "application/octet-stream")
            return self._send(f.read_bytes(), content_type=ctype)

        self._send({"error": f"no route {path}"}, 404)

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        if not self._authed():
            return self._send({"error": "bad or missing bearer token"}, 401)
        path = urlparse(self.path).path.rstrip("/")
        try:
            body = self._body()
        except json.JSONDecodeError:
            return self._send({"error": "invalid JSON"}, 400)

        if path == "/jobs":
            jtype = body.get("type", "")
            if jtype not in JOB_TYPES and not jtype.startswith("content."):
                return self._send({"error": f"unknown job type '{jtype}'"}, 400)
            jid = new_id("job")
            db().execute(
                "INSERT INTO jobs(id,type,project_id,recipe_id,recipe_version,payload,"
                "priority,required_mode,required_caps,status,max_attempts,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (jid, jtype, body.get("project", "sandbox"),
                 body.get("recipe"), body.get("recipe_version"),
                 json.dumps(body.get("payload", {})), int(body.get("priority", 5)),
                 body.get("required_mode", "ANY"),
                 json.dumps(body.get("required_caps", [])),
                 "queued", int(body.get("max_attempts", 2)), now()))
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
            job = db().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not job:
                return self._send({"error": "no such job"}, 404)
            if new_status == "running":
                db().execute("UPDATE jobs SET status='running' WHERE id=?", (jid,))
            elif new_status == "done":
                final = "needs_review" if job["type"] in REVIEW_TYPES else "done"
                db().execute("UPDATE jobs SET status=?, finished_at=? WHERE id=?",
                             (final, now(), jid))
            elif new_status == "failed":
                err = str(body.get("error", ""))[:2000]
                if job["attempts"] < job["max_attempts"]:
                    db().execute("UPDATE jobs SET status='queued', worker_id=NULL, error=? WHERE id=?",
                                 (err, jid))
                else:
                    db().execute("UPDATE jobs SET status='dead', finished_at=?, error=? WHERE id=?",
                                 (now(), err, jid))
            else:
                return self._send({"error": f"bad status '{new_status}'"}, 400)
            db().commit()
            event(self._actor(), f"job.{new_status}", jid,
                  {"error": body.get("error")} if new_status == "failed" else None,
                  ok=new_status != "failed")
            return self._send(dict(db().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()))

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
            else:
                return self._send({"error": f"bad action '{action}'"}, 400)
            db().commit()
            event(self._actor(), f"artifact.{action}", aid,
                  {"score": body.get("score")} if action == "judge" else None)
            return self._send(dict(db().execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()))

        if path == "/workers/heartbeat":
            db().execute(
                "INSERT OR REPLACE INTO workers(id,host,caps,mode,last_heartbeat,status)"
                " VALUES(?,?,?,?,?,?)",
                (body.get("id", "?"), body.get("host", ""), json.dumps(body.get("caps", [])),
                 body.get("mode", "ANY"), now(), "online"))
            db().commit()
            req = db().execute("SELECT value FROM kv WHERE key='requested_mode'").fetchone()
            return self._send({"ok": True, "requested_mode": req["value"] if req else None})

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
    event("router", "router.start", f"port {port}")
    print(f"[router] ByrdHouse router on 0.0.0.0:{port}  db={DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
