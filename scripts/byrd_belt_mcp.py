"""
byrd_belt_mcp.py — the belt as an MCP server (the bot's hands on ByrdHouse).

WHY THIS EXISTS (founder's dream, 2026-07): an always-on operator that lives on
both machines and RUNS THE BELT while Carey is away. The belt is the environment
the bot operates in and out of. This server is that environment's control
surface: it exposes the router's already-audited endpoints as MCP tools, so ANY
MCP client — Cherry Studio, LM Studio, or an autonomous loop — drives the belt
with one shared roster, on either machine, over the tailnet.

HARD LINE (Blueprint): the bot NEVER touches ComfyUI or the GPU directly. Every
tool here only talks to the router (byrd-mini:8787), which queues jobs the worker
pulls under the GPU mode ritual. Autonomy is a permissions change, not a new
build — set BYRD_BELT_MCP_READONLY=1 and the write tools vanish from the roster
(the A0/A1 rung: read-only suggestions). Flip it off to let the bot act (A2+).

Transport: JSON-RPC 2.0 over stdio, newline-delimited (the MCP stdio transport).
Stdlib only — no pip, so it runs on both machines exactly like the rest of the kit.

Register in an MCP client (e.g. Cherry Studio / LM Studio) as:
    command: python   args: ["<ROOT>/scripts/byrd_belt_mcp.py"]
    env: { BYRDHOUSE_ROOT: "D:/ByrdHouse" }
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "byrd-belt", "version": "1.0.0"}
READONLY = os.environ.get("BYRD_BELT_MCP_READONLY", "").lower() in ("1", "true", "yes")


def _load_cfg():
    root = os.environ.get("BYRDHOUSE_ROOT")
    if not root:
        sys.exit("BYRDHOUSE_ROOT not set")
    cfg = json.loads((Path(root) / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
    return cfg


CFG = _load_cfg()
ROUTER = CFG["services"]["router"].rstrip("/")
TOKEN = CFG["auth"]["admin_token"]
ACTOR = "belt-mcp"


def router_call(path, payload=None, method=None):
    """One line to the belt. Read tools GET, write tools POST — all audited by
    the router (events table) exactly as if the dashboard had called them."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ROUTER}{path}", data=data, method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}", "X-Actor": ACTOR})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ── Tool roster: each maps to an audited router endpoint ─────────────────────
def _t(name, desc, schema, write, fn):
    return {"name": name, "description": desc, "inputSchema": schema,
            "write": write, "fn": fn}


def _belt_status(a):
    return router_call("/status")


def _list_artifacts(a):
    q = f"?limit={int(a.get('limit', 8))}"
    if a.get("status"):
        q += f"&status={a['status']}"
    rows = router_call(f"/artifacts{q}")
    # trim to what the bot reasons over — id, kind, score, status, purpose
    out = []
    for r in rows:
        meta = json.loads(r.get("meta") or "{}")
        out.append({"id": r["id"], "kind": r["kind"], "score": r.get("score"),
                    "status": r["status"], "purpose": meta.get("purpose", "")[:80]})
    return out


def _what_works(a):
    return router_call(f"/learn?by={a.get('by', 'recipe')}")


def _recent_events(a):
    return router_call(f"/events?limit={int(a.get('limit', 12))}")


def _queue_image(a):
    prompt = str(a.get("prompt", "")).strip()
    if not prompt and not a.get("recipe"):
        return {"error": "queue_image needs a prompt (freeform) or a recipe+slots"}
    project = a.get("project", "careyrpg")
    if a.get("recipe"):
        payload = {"recipe": a["recipe"], "slots": a.get("slots", {}),
                   "project": project, "purpose": a.get("purpose") or f"bot: {a['recipe']}"}
    else:
        payload = {"recipe": "freeform", "slots": {"prompt": prompt[:500]},
                   "project": project, "purpose": f"bot request: {prompt[:80]}"}
    if a.get("aspect"):
        payload["aspect"] = a["aspect"]
    return router_call("/jobs", {"type": "image.generate", "project": project,
                                 "required_mode": "IMAGE", "required_caps": ["comfyui"],
                                 "payload": payload})


def _compose_thumbnail(a):
    title = str(a.get("title", "")).strip()
    if not title:
        return {"error": "compose_thumbnail needs a title (real text is composited, never diffused)"}
    project = a.get("project", "careyrpg")
    payload = {"title": title, "project": project,
               "purpose": a.get("purpose") or f"bot thumbnail: {title[:60]}"}
    src = a.get("source_artifact")
    if src:  # composite onto an uploaded/real source — no GPU pass
        payload["source_artifact"] = src
        return router_call("/jobs", {"type": "content.thumbnail", "project": project,
                                     "required_mode": "ANY", "required_caps": [], "payload": payload})
    # two-pass: recipe art, then real text
    payload["recipe"] = a.get("recipe", "yt_thumbnail")
    payload["slots"] = a.get("slots", {})
    return router_call("/jobs", {"type": "content.thumbnail", "project": project,
                                 "required_mode": "IMAGE", "required_caps": ["comfyui"], "payload": payload})


def _review_artifact(a):
    aid = str(a.get("artifact_id", "")).strip()
    action = a.get("action")
    if action not in ("approve", "reject"):
        return {"error": "action must be approve|reject"}
    if not aid:
        return {"error": "review_artifact needs an artifact_id"}
    return router_call(f"/artifacts/{aid}/review", {"action": action})


TOOLS = [
    _t("belt_status", "Live belt health: queue counts, worker liveness, services. "
       "The bot's first look before it acts.",
       {"type": "object", "properties": {}}, False, _belt_status),
    _t("list_artifacts", "Recent artifacts (id, kind, score, status, purpose). "
       "Use before review_artifact or refine to get an id.",
       {"type": "object", "properties": {
           "status": {"type": "string", "description": "draft|needs_review|approved|rejected"},
           "limit": {"type": "integer"}}}, False, _list_artifacts),
    _t("what_works", "Approval-rate ranking of what the founder actually approves, "
       "by recipe|checkpoint|palette|lighting|project. Use to pick settings.",
       {"type": "object", "properties": {"by": {"type": "string"}}}, False, _what_works),
    _t("recent_events", "Tail of the belt event log — what happened lately.",
       {"type": "object", "properties": {"limit": {"type": "integer"}}}, False, _recent_events),
    _t("queue_image", "Queue an image generation on the belt. Give a freeform "
       "'prompt', or a 'recipe' id (e.g. yt_thumbnail) + 'slots'. The worker runs "
       "it under the GPU mode ritual — you never touch ComfyUI directly.",
       {"type": "object", "properties": {
           "prompt": {"type": "string"}, "recipe": {"type": "string"},
           "slots": {"type": "object"}, "project": {"type": "string"},
           "aspect": {"type": "string", "description": "16:9|9:16|1:1|2:3|3:2|21:9"},
           "purpose": {"type": "string"}}}, True, _queue_image),
    _t("compose_thumbnail", "Make a YouTube thumbnail: real title text composited "
       "onto art. Pass 'source_artifact' (an uploaded/real image id) to composite "
       "onto real pixels, or a 'recipe'+'slots' to generate the art first.",
       {"type": "object", "properties": {
           "title": {"type": "string"}, "source_artifact": {"type": "string"},
           "recipe": {"type": "string"}, "slots": {"type": "object"},
           "project": {"type": "string"}, "purpose": {"type": "string"}},
        "required": ["title"]}, True, _compose_thumbnail),
    _t("review_artifact", "Approve or reject an artifact by id (feeds the learn loop).",
       {"type": "object", "properties": {
           "artifact_id": {"type": "string"},
           "action": {"type": "string", "description": "approve|reject"}},
        "required": ["artifact_id", "action"]}, True, _review_artifact),
]


def visible_tools():
    """Read-only mode hides write tools — the autonomy ladder is literally this
    filter (A0/A1 suggest-only vs A2+ act), no separate build."""
    return [t for t in TOOLS if not (READONLY and t["write"])]


def call_tool(name, arguments):
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if not tool:
        return {"error": f"unknown tool {name}"}, True
    if READONLY and tool["write"]:
        return {"error": f"{name} is a write tool; belt-MCP is in read-only mode "
                         "(BYRD_BELT_MCP_READONLY). Flip the permission to let the bot act."}, True
    try:
        return tool["fn"](arguments or {}), False
    except Exception as e:  # surface the belt's real error to the agent
        return {"error": f"{name} failed: {e}"}, True


# ── JSON-RPC 2.0 dispatch (testable without stdio) ───────────────────────────
def handle(msg):
    """Return a JSON-RPC response dict, or None for notifications."""
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in visible_tools()]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        result, is_error = call_tool(params.get("name"), params.get("arguments"))
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": is_error}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    # newline-delimited JSON-RPC on stdio (MCP stdio transport)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
