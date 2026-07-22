#!/usr/bin/env python3
"""ByrdCoder model discovery (docs/BYRDCODER_LOCAL.md, Phase 1).

Asks the LM Studio configured in byrdhouse.config.json (services.lmstudio —
zero hardcoded hosts) what models it exposes, the same way the pinned
opencode-lmstudio plugin does, and reports:

  - chat-capable LLMs (embedding models EXCLUDED, as the plugin excludes them)
  - context length per model (loaded context when reported, else max)
  - tool-use / vision capability flags where the native API reports them
  - which models look coder-capable (qwen / qwopus / coder / deepseek names)

Endpoints probed in order (LM Studio versions differ): the native REST API
(/api/v1/models, then /api/v0/models — richer metadata) and the
OpenAI-compatible /v1/models (ids only) as the floor.

Stdlib only. Read-only. Usage:
    python scripts/byrdcoder_models.py [--root E:\\ByrdHouse] [--json] [--check]
--check exits 1 if no chat-capable LLM is found (used by preflight).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

CODER_HINTS = ("qwen", "qwopus", "coder", "deepseek", "codestral", "starcoder")
EMBED_TYPES = ("embedding", "embeddings")


def fetch_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def normalize_native(payload, source):
    """LM Studio native REST record -> normalized dict (excludes embeddings)."""
    out = []
    records = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return out
    for m in records:
        if not isinstance(m, dict):
            continue
        mtype = str(m.get("type", "llm")).lower()
        if mtype in EMBED_TYPES:
            continue
        caps = m.get("capabilities") or []
        if isinstance(caps, dict):
            caps = [k for k, v in caps.items() if v]
        out.append({
            "id": m.get("id") or m.get("key") or "?",
            "type": mtype,
            "context": m.get("loaded_context_length") or m.get("max_context_length"),
            "loaded": str(m.get("state", "")).lower() in ("loaded",),
            "tool_capable": ("tool_use" in caps) or bool(m.get("supports_tool_calls")),
            "vision": ("vision" in caps) or (mtype == "vlm"),
            "source": source,
        })
    return out


def discover(base_v1):
    """base_v1 is the OpenAI-compatible URL from config, e.g. http://host:1234/v1"""
    host = base_v1.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3].rstrip("/")
    for path in ("/api/v1/models", "/api/v0/models"):
        payload = fetch_json(host + path)
        if payload:
            models = normalize_native(payload, path)
            if models:
                return models, path
    payload = fetch_json(base_v1.rstrip("/") + "/models")
    if payload and isinstance(payload.get("data"), list):
        models = [{"id": m.get("id", "?"), "type": "llm", "context": None,
                   "loaded": None, "tool_capable": None, "vision": None,
                   "source": "/v1/models"}
                  for m in payload["data"]
                  if not any(h in str(m.get("id", "")).lower() for h in ("embed",))]
        return models, "/v1/models"
    return [], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if no chat-capable LLM is discovered")
    args = ap.parse_args()

    cfg_path = os.path.join(args.root, "byrdhouse.config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        base = cfg["services"]["lmstudio"]
    except (OSError, KeyError, ValueError) as e:
        print(f"cannot read services.lmstudio from {cfg_path}: {e}", file=sys.stderr)
        return 2

    models, endpoint = discover(base)
    for m in models:
        m["coder_hint"] = any(h in m["id"].lower() for h in CODER_HINTS)

    if args.json:
        print(json.dumps({"lmstudio": base, "endpoint": endpoint,
                          "models": models}, indent=2))
    else:
        if not endpoint:
            print(f"LM Studio unreachable or no models at {base}")
        else:
            print(f"LM Studio {base} — {len(models)} chat model(s) via {endpoint} "
                  f"(embeddings excluded)")
            for m in models:
                flags = []
                if m["coder_hint"]:
                    flags.append("coder")
                if m["tool_capable"]:
                    flags.append("tools")
                if m["vision"]:
                    flags.append("vision")
                if m["loaded"]:
                    flags.append("loaded")
                ctx = m["context"] if m["context"] else "?"
                print(f"  {m['id']:<50} ctx={ctx:<8} {' '.join(flags)}")

    if args.check and not models:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
