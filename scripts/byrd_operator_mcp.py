"""Private, least-privilege MCP bridge for the ByrdHouse operator.

The operator can run from MINI, GAMING, Cherry Studio, LM Studio, or another
MCP client. It always talks to the MINI router; it never talks to ComfyUI,
Godot, Python, or the filesystem directly. Those systems remain behind the
audited belt and their own MCPs can be added as separate, explicit adapters.

Transport: newline-delimited JSON-RPC over stdio (MCP stdio-compatible).
Environment: BYRDHOUSE_ROOT and optional BYRD_OPERATOR_READONLY=1.
"""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
READONLY = os.environ.get("BYRD_OPERATOR_READONLY", "1").lower() in {"1", "true", "yes"}


def _config():
    root = os.environ.get("BYRDHOUSE_ROOT")
    if not root:
        raise RuntimeError("BYRDHOUSE_ROOT is required")
    return json.loads((Path(root) / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))


CFG = _config()
ROUTER = CFG["services"]["router"].rstrip("/")
TOKEN = CFG["auth"]["admin_token"]


def router_call(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        ROUTER + path, data=data, method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}",
                 "X-Actor": "operator-mcp"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def _tool(name, description, schema, write, fn):
    return {"name": name, "description": description, "inputSchema": schema,
            "write": write, "fn": fn}


def _status(_):
    return router_call("/status")


def _recipes(_):
    return router_call("/recipes")


def _validate(a):
    recipe = str(a.get("recipe", "")).strip()
    slots = a.get("slots") or {}
    recipes = _recipes({})
    match = next((r for r in recipes if f"{r['id']}@{r['version']}" == recipe), None)
    if not match:
        return {"valid": False, "error": f"unknown pinned recipe '{recipe}'"}
    required = [s for s in match["slots"] if s not in match.get("vary", [])]
    missing = [s for s in required if not str(slots.get(s, "")).strip()]
    return {"valid": not missing, "recipe": recipe, "required": required,
            "missing": missing, "vary": match.get("vary", [])}


def _queue(a):
    recipe = str(a.get("recipe", "")).strip()
    prompt = str(a.get("prompt", "")).strip()
    if not recipe and not prompt:
        return {"error": "provide recipe+slots or prompt"}
    project = str(a.get("project", "careyrpg")).strip() or "careyrpg"
    payload = {"recipe": recipe or "freeform", "slots": a.get("slots") or {},
               "project": project, "purpose": a.get("purpose") or "operator request"}
    if not recipe:
        payload["slots"] = {"prompt": prompt[:500]}
    if a.get("aspect"):
        payload["aspect"] = a["aspect"]
    request_id = str(a.get("request_id", "")).strip()
    idem = hashlib.sha256((request_id or json.dumps(payload, sort_keys=True)).encode()).hexdigest()
    return router_call("/jobs", {"type": "image.generate", "project": project,
                                 "required_mode": "IMAGE", "required_caps": ["comfyui"],
                                 "idempotency_key": "operator-" + idem, "payload": payload})


def _job(a):
    jid = urllib.parse.quote(str(a.get("job_id", "")).strip(), safe=".-_")
    if not jid:
        return {"error": "job_id is required"}
    rows = router_call("/jobs?limit=100")
    return next((r for r in rows if r.get("id") == jid), {"error": "job not found"})


def _artifacts(a):
    q = "?limit=" + str(min(max(int(a.get("limit", 12)), 1), 50))
    if a.get("status"):
        q += "&status=" + urllib.parse.quote(str(a["status"]))
    return router_call("/artifacts" + q)


def _review(a):
    if a.get("action") not in {"approve", "reject"}:
        return {"error": "action must be approve or reject"}
    aid = urllib.parse.quote(str(a.get("artifact_id", "")).strip(), safe=".-_")
    return router_call(f"/artifacts/{aid}/review", {"action": a["action"]})


TOOLS = [
    _tool("belt_status", "Read-only MINI router, queue, worker, and machine status.",
          {"type": "object", "properties": {}}, False, _status),
    _tool("list_recipes", "List pinned recipes and their founder versus vary slots.",
          {"type": "object", "properties": {}}, False, _recipes),
    _tool("validate_recipe", "Preflight a pinned recipe before spending a worker attempt.",
          {"type": "object", "properties": {"recipe": {"type": "string"},
          "slots": {"type": "object"}}, "required": ["recipe"]}, False, _validate),
    _tool("queue_image", "Queue an image through the audited belt; never drive ComfyUI directly.",
          {"type": "object", "properties": {"prompt": {"type": "string"},
          "recipe": {"type": "string"}, "slots": {"type": "object"},
          "project": {"type": "string"}, "purpose": {"type": "string"},
          "aspect": {"type": "string"}, "request_id": {"type": "string"}}}, True, _queue),
    _tool("job_status", "Read the current state and error of a belt job.",
          {"type": "object", "properties": {"job_id": {"type": "string"}},
           "required": ["job_id"]}, False, _job),
    _tool("list_artifacts", "List generated artifacts and human review status.",
          {"type": "object", "properties": {"status": {"type": "string"},
          "limit": {"type": "integer"}}}, False, _artifacts),
    _tool("review_artifact", "Approve or reject an artifact; feeds the learn loop.",
          {"type": "object", "properties": {"artifact_id": {"type": "string"},
          "action": {"type": "string"}}, "required": ["artifact_id", "action"]}, True, _review),
]


def _visible():
    return [t for t in TOOLS if not (READONLY and t["write"])]


def handle(message):
    method, mid = message.get("method"), message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
            "serverInfo": {"name": "byrd-operator", "version": "1.0.0"}}}
    if method in {"notifications/initialized", "initialized"}:
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema")} for t in _visible()]}}
    if method == "tools/call":
        p = message.get("params") or {}
        tool = next((t for t in TOOLS if t["name"] == p.get("name")), None)
        if not tool:
            result, failed = {"error": "unknown tool"}, True
        elif READONLY and tool["write"]:
            result, failed = {"error": "operator is read-only; set BYRD_OPERATOR_READONLY=0"}, True
        else:
            try:
                result, failed = tool["fn"](p.get("arguments") or {}), False
            except Exception as e:
                result, failed = {"error": str(e)}, True
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": failed}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    for line in sys.stdin:
        try:
            response = handle(json.loads(line))
            if response is not None:
                print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32000, "message": str(e)}}), flush=True)


if __name__ == "__main__":
    main()
