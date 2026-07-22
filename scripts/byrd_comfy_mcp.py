#!/usr/bin/env python3
"""byrd_comfy_mcp.py — ByrdCoder's APPROVED RECIPE EXECUTOR (Role A of
docs/BYRDCODER_COMFY_MCP.md). A deliberately NARROW MCP server that lets a
local coding model run curated ByrdHouse image recipes — nothing else.

Design basis: joenorton/comfyui-mcp-server (Apache-2.0) was evaluated and its
useful surface kept (constrained PARAM overrides, workflow discovery, job
polling, cancellation, regeneration, asset metadata, ComfyUI error
extraction). Its dangerous surface DOES NOT EXIST here rather than being
switched off: no publish_asset, no set_comfyui_output_root, no persistent
set_defaults, no arbitrary workflow execution, no direct writes outside the
MCP runtime directory (logs/byrdcoder/comfy_exec/).

The hard line (Blueprint / DECISIONS 2026-07-11) is preserved: this server
NEVER talks to ComfyUI. Every execution is a normal belt job submitted to the
ByrdHouse router, so the queue, worker mode ritual, artifact archive, sidecar
cards, and judge pipeline all apply unchanged — the upstream project's
temporary in-memory asset registry is replaced by the ByrdHouse artifact
system itself. Assets are registered the moment the worker cards them.

Only recipes listed in configs/byrdcoder/approved_workflows.json can run.
Path traversal and unmapped parameter overrides are rejected (tested in
tests/integration_test.py). BYRD_COMFY_MCP_READONLY=1 hides the write tools
(submit/cancel/regenerate) — the same tier gate as byrd_belt_mcp.py.

Transport: JSON-RPC 2.0 over stdio (loopback by construction — no HTTP port,
nothing to bind, nothing to expose). Auth to the router uses the admin token
from byrdhouse.config.json exactly like the dashboard. Stdlib only; runs in
the dedicated ByrdCoder Python 3.11 venv (docs/BYRDCODER_COMFY_MCP.md).

Register in the ByrdCoder OpenCode config (already wired in the example):
    command: python   args: ["<ROOT>/scripts/byrd_comfy_mcp.py"]
    env: { BYRDHOUSE_ROOT: "E:/ByrdHouse", BYRD_COMFY_MCP_READONLY: "1" }
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "byrd-comfy-executor", "version": "0.1.0"}
MANIFEST_REL = "configs/byrdcoder/approved_workflows.json"
EXEC_DIR_REL = "logs/byrdcoder/comfy_exec"  # the ONLY place this server writes

# Tools that exist upstream but are structurally absent here. Kept as data so
# the contract test can prove they never re-enter the roster.
REMOVED_TOOLS = ("publish_asset", "set_comfyui_output_root", "set_defaults",
                 "run_workflow", "list_models", "generate_song")


# ── Pure, importable validation core (tested without router/ComfyUI) ────────
def load_manifest(root):
    path = Path(root) / MANIFEST_REL
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest.get("approved"), dict):
        raise ValueError("manifest has no 'approved' map")
    return manifest


def resolve_workflow_path(root, workflow_rel):
    """Resolve a manifest workflow reference safely. Rejects absolute paths,
    parent traversal, and anything that escapes <root>/workflows/."""
    root = Path(root).resolve()
    rel = str(workflow_rel).replace("\\", "/")
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise ValueError(f"absolute workflow paths are rejected: {workflow_rel}")
    if ".." in rel.split("/"):
        raise ValueError(f"path traversal rejected: {workflow_rel}")
    resolved = (root / rel).resolve()
    workflows_root = (root / "workflows").resolve()
    if workflows_root != resolved and workflows_root not in resolved.parents:
        raise ValueError(f"workflow must live under workflows/: {workflow_rel}")
    if not resolved.is_file():
        raise ValueError(f"approved workflow file missing: {workflow_rel}")
    return resolved


def validate_overrides(entry, overrides):
    """Only parameters explicitly mapped in the manifest entry may be
    overridden, with type/bound checks. Unknown keys are rejected by name."""
    params = entry.get("params", {})
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(params))
    if unknown:
        raise ValueError(f"unmapped parameter override(s) rejected: {', '.join(unknown)} "
                         f"(mapped: {', '.join(sorted(params)) or 'none'})")
    clean = {}
    for key, value in overrides.items():
        spec = params[key]
        ptype = spec.get("type", "string")
        if ptype == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{key} must be an integer")
            if "min" in spec and value < spec["min"]:
                raise ValueError(f"{key}={value} below minimum {spec['min']}")
            if "max" in spec and value > spec["max"]:
                raise ValueError(f"{key}={value} above maximum {spec['max']}")
        elif ptype == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{key} must be a number")
            if "min" in spec and value < spec["min"]:
                raise ValueError(f"{key}={value} below minimum {spec['min']}")
            if "max" in spec and value > spec["max"]:
                raise ValueError(f"{key}={value} above maximum {spec['max']}")
        elif ptype == "enum":
            if value not in spec.get("values", []):
                raise ValueError(f"{key}='{value}' not in allowed values "
                                 f"{spec.get('values', [])}")
        else:  # string
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
            maxlen = spec.get("maxlen", 500)
            if len(value) > maxlen:
                raise ValueError(f"{key} exceeds {maxlen} chars")
        clean[key] = value
    return clean


def workflow_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── Runtime wiring (lazy — importing this module never reads config) ────────
def _ctx():
    root = os.environ.get("BYRDHOUSE_ROOT")
    if not root:
        sys.exit("BYRDHOUSE_ROOT not set")
    cfg = json.loads((Path(root) / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
    return {"root": Path(root), "router": cfg["services"]["router"].rstrip("/"),
            "token": cfg["auth"]["admin_token"]}


def router_call(ctx, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ctx['router']}{path}", data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {ctx['token']}",
                 "X-Actor": "byrd-comfy-mcp"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _card_path(ctx, job_id):
    out = ctx["root"] / EXEC_DIR_REL
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in str(job_id) if c.isalnum() or c in "._-")
    return out / f"{safe}.json"


def _write_card(ctx, card):
    path = _card_path(ctx, card["byrdhouse_job_id"])
    path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    return str(path)


def _extract_comfy_error(job_row):
    """Surface the worker's recorded ComfyUI failure (if any) to the agent."""
    err = job_row.get("error") or ""
    if not err and job_row.get("status") in ("failed", "dead"):
        err = "job failed with no recorded error text"
    return err[:1200] if err else None


# ── Tools ────────────────────────────────────────────────────────────────────
def _list_recipes(ctx, a):
    manifest = load_manifest(ctx["root"])
    out = []
    for rid, entry in sorted(manifest["approved"].items()):
        wf = resolve_workflow_path(ctx["root"], entry["workflow"])
        out.append({"recipe_id": rid, "recipe_version": entry.get("recipe_version"),
                    "kind": entry.get("kind", "image.generate"),
                    "description": entry.get("description", ""),
                    "workflow": entry["workflow"],
                    "workflow_sha256": workflow_sha256(wf),
                    "params": sorted(entry.get("params", {}))})
    return {"approved_recipes": out,
            "note": "only these curated recipes can run; the full workflows/ "
                    "directory is deliberately not exposed"}


def _describe_recipe(ctx, a):
    manifest = load_manifest(ctx["root"])
    rid = a.get("recipe_id", "")
    entry = manifest["approved"].get(rid)
    if not entry:
        return {"error": f"'{rid}' is not an approved recipe — list_recipes shows the curated set"}
    wf = resolve_workflow_path(ctx["root"], entry["workflow"])
    recipe_file = ctx["root"] / "recipes" / f"{entry['recipe']}.v{entry['recipe_version']}.json"
    recipe = json.loads(recipe_file.read_text(encoding="utf-8-sig")) if recipe_file.is_file() else {}
    return {"recipe_id": rid, "entry": entry,
            "workflow_sha256": workflow_sha256(wf),
            "recipe_defaults": recipe.get("defaults", {}),
            "vary_axes": sorted(recipe.get("vary", {}))}


def _submit_recipe(ctx, a):
    manifest = load_manifest(ctx["root"])
    rid = a.get("recipe_id", "")
    entry = manifest["approved"].get(rid)
    if not entry:
        return {"error": f"'{rid}' is not an approved recipe"}
    wf = resolve_workflow_path(ctx["root"], entry["workflow"])
    overrides = validate_overrides(entry, a.get("overrides"))

    slots, top = {}, {}
    for key, value in overrides.items():
        spec = entry["params"][key]
        if spec.get("slot"):
            slots[spec["slot"]] = value
        elif spec.get("top"):
            top[spec["top"]] = value
    purpose = (a.get("purpose") or f"byrdcoder: {rid}")[:200]
    payload = {"recipe": entry["recipe"], "slots": slots,
               "project": a.get("project", "careyrpg"), "purpose": purpose,
               "byrdcoder_meta": {"executor": SERVER_INFO["name"],
                                  "recipe_id": rid,
                                  "recipe_version": entry.get("recipe_version"),
                                  "workflow": entry["workflow"],
                                  "workflow_sha256": workflow_sha256(wf),
                                  "overrides": overrides}}
    payload.update(top)
    job = router_call(ctx, "/jobs", {
        "type": entry.get("kind", "image.generate"),
        "project": payload["project"], "required_mode": "IMAGE",
        "required_caps": ["comfyui"], "payload": payload})
    job_id = job.get("id") or job.get("job_id") or "unknown"

    card = {"tool": SERVER_INFO["name"], "created_at": datetime.now(timezone.utc).isoformat(),
            "byrdhouse_job_id": job_id,
            "recipe_id": rid, "recipe_version": entry.get("recipe_version"),
            "workflow": entry["workflow"], "workflow_sha256": workflow_sha256(wf),
            "parameter_overrides": overrides,
            "checkpoint": a.get("checkpoint") or "recipe default (recorded in sidecar)",
            "seed": "belt-assigned at submit (hard rule) — recorded on completion",
            "source_hashes": {p: sha256_file(p) for p in a.get("source_files", [])
                              if Path(p).is_file()},
            "reference_hashes": {},
            "output_path": None, "runtime_s": None,
            "result_status": "submitted", "submitted_at_epoch": time.time()}
    card_file = _write_card(ctx, card)
    return {"job_id": job_id, "status": "submitted", "execution_card": card_file,
            "note": "job runs through the normal belt (queue -> worker mode "
                    "ritual -> artifact + sidecar). Poll with job_status."}


def _job_status(ctx, a):
    job_id = a.get("job_id", "")
    rows = router_call(ctx, "/jobs")
    row = next((r for r in rows if str(r.get("id")) == str(job_id)), None)
    if not row:
        return {"error": f"job {job_id} not found on the router"}
    result = {"job_id": job_id, "status": row.get("status"),
              "comfyui_error": _extract_comfy_error(row)}
    artifacts = router_call(ctx, "/artifacts?limit=50")
    mine = [r for r in artifacts if str(r.get("job_id", "")) == str(job_id)]
    result["artifacts"] = [{"id": r["id"], "status": r.get("status"),
                            "path": r.get("path")} for r in mine]

    card_file = _card_path(ctx, job_id)
    if card_file.is_file():
        card = json.loads(card_file.read_text(encoding="utf-8"))
        card["result_status"] = row.get("status")
        if row.get("status") in ("done", "needs_review", "approved", "failed", "dead"):
            card["runtime_s"] = round(time.time() - card.get("submitted_at_epoch", time.time()), 1)
        if mine:
            card["output_path"] = mine[0].get("path")
            meta = json.loads(mine[0].get("meta") or "{}")
            card["seed"] = meta.get("seed", card["seed"])
            card["checkpoint"] = meta.get("checkpoint", card["checkpoint"])
        if result["comfyui_error"]:
            card["comfyui_error"] = result["comfyui_error"]
        _write_card(ctx, card)
        result["execution_card"] = str(card_file)
    return result


def _cancel_job(ctx, a):
    job_id = a.get("job_id", "")
    out = router_call(ctx, f"/jobs/{job_id}/cancel", {})
    card_file = _card_path(ctx, job_id)
    if card_file.is_file():
        card = json.loads(card_file.read_text(encoding="utf-8"))
        card["result_status"] = "cancelled"
        _write_card(ctx, card)
    return out


def _regenerate(ctx, a):
    """Resubmit a previous execution with identical validated parameters (the
    belt assigns a fresh seed at submit, per the hard rule)."""
    job_id = a.get("job_id", "")
    card_file = _card_path(ctx, job_id)
    if not card_file.is_file():
        return {"error": f"no execution card for job {job_id} — regenerate only "
                         "replays jobs this executor submitted"}
    card = json.loads(card_file.read_text(encoding="utf-8"))
    return _submit_recipe(ctx, {"recipe_id": card["recipe_id"],
                                "overrides": card["parameter_overrides"],
                                "purpose": f"regenerate of {job_id}"})


def _asset_meta(ctx, a):
    aid = a.get("artifact_id", "")
    rows = router_call(ctx, f"/artifacts?id={aid}")
    if not rows:
        return {"error": f"artifact {aid} not found"}
    row = rows[0] if isinstance(rows, list) else rows
    meta = json.loads(row.get("meta") or "{}") if isinstance(row.get("meta"), str) else row.get("meta")
    return {"id": row.get("id"), "kind": row.get("kind"), "status": row.get("status"),
            "score": row.get("score"), "path": row.get("path"), "meta": meta,
            "note": "registered in the ByrdHouse artifact system (permanent), "
                    "not a session-scoped registry"}


def _last_error(ctx, a):
    job_id = a.get("job_id", "")
    rows = router_call(ctx, "/jobs")
    row = next((r for r in rows if str(r.get("id")) == str(job_id)), None)
    if not row:
        return {"error": f"job {job_id} not found"}
    return {"job_id": job_id, "status": row.get("status"),
            "comfyui_error": _extract_comfy_error(row) or "(no error recorded)"}


def _t(name, desc, schema, write, fn):
    return {"name": name, "description": desc, "inputSchema": schema,
            "write": write, "fn": fn}


TOOLS = [
    _t("list_recipes", "List the curated, founder-approved ByrdHouse recipes this "
       "executor can run (id, params, workflow hash). Nothing outside this list "
       "is executable.", {"type": "object", "properties": {}}, False, _list_recipes),
    _t("describe_recipe", "Details for one approved recipe: mapped parameters "
       "with types/bounds, workflow hash, recipe defaults and variation axes.",
       {"type": "object", "properties": {"recipe_id": {"type": "string"}},
        "required": ["recipe_id"]}, False, _describe_recipe),
    _t("submit_recipe", "Submit an approved recipe as a normal ByrdHouse belt job "
       "(router queue -> GPU worker -> archived artifact + sidecar). Only mapped "
       "parameter overrides are accepted; everything is recorded in an execution "
       "card.", {"type": "object", "properties": {
           "recipe_id": {"type": "string"}, "overrides": {"type": "object"},
           "purpose": {"type": "string"}, "project": {"type": "string"}},
        "required": ["recipe_id"]}, True, _submit_recipe),
    _t("job_status", "Poll a submitted job: belt status, produced artifacts, "
       "extracted ComfyUI error if it failed. Updates the execution card "
       "(runtime, output path, seed, checkpoint, result).",
       {"type": "object", "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]}, False, _job_status),
    _t("cancel_job", "Cancel a queued job on the router.",
       {"type": "object", "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]}, True, _cancel_job),
    _t("regenerate", "Resubmit a previous execution with the same validated "
       "parameters (fresh belt-assigned seed).",
       {"type": "object", "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]}, True, _regenerate),
    _t("asset_meta", "Metadata for an archived artifact (sidecar card fields) — "
       "the permanent ByrdHouse registry, not a session store.",
       {"type": "object", "properties": {"artifact_id": {"type": "string"}},
        "required": ["artifact_id"]}, False, _asset_meta),
    _t("last_error", "The recorded ComfyUI/worker error for a job, extracted for "
       "the agent.", {"type": "object", "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]}, False, _last_error),
]


def readonly():
    return os.environ.get("BYRD_COMFY_MCP_READONLY", "").lower() in ("1", "true", "yes")


def visible_tools():
    return [t for t in TOOLS if not (readonly() and t["write"])]


def call_tool(ctx, name, arguments):
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if not tool:
        return {"error": f"unknown tool {name}"}, True
    if readonly() and tool["write"]:
        return {"error": f"{name} is a write tool and this executor is in read-only "
                         "mode (BYRD_COMFY_MCP_READONLY) — a founder permission flip "
                         "is required (Tier 2/3)."}, True
    try:
        return tool["fn"](ctx, arguments or {}), False
    except ValueError as e:  # validation rejections are answers, not crashes
        return {"error": str(e)}, True
    except Exception as e:
        return {"error": f"{name} failed: {e}"}, True


def handle(ctx, msg):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t["name"], "description": t["description"],
             "inputSchema": t["inputSchema"]} for t in visible_tools()]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        result, is_error = call_tool(ctx, params.get("name"), params.get("arguments"))
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": is_error}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    ctx = _ctx()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(ctx, msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
