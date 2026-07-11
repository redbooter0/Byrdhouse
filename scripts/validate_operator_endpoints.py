"""Validate the committed ByrdHouse endpoint and MCP configuration templates."""
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent


def fail(message):
    raise SystemExit(message)


cfg = json.loads((ROOT / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
services = cfg.get("services", {})
for name in ("router", "lmstudio", "comfyui"):
    value = services.get(name, "")
    if not value.startswith(("http://", "https://")):
        fail(f"services.{name} must be an HTTP URL")

if urlparse(services["router"]).port != 8787:
    fail("services.router must use port 8787")
if not services["lmstudio"].rstrip("/").endswith("/v1"):
    fail("services.lmstudio must end in /v1")
if urlparse(services["comfyui"]).port != 8188:
    fail("services.comfyui must use port 8188")

mcp = cfg.get("mcp", {})
servers = {name: spec for name, spec in mcp.items() if not name.startswith("_")}
if len(servers) > 8:
    fail(f"config.mcp has {len(servers)} servers; the bounded roster allows at most 8")
belt_cfg = mcp.get("byrdhouse-belt", {})
if belt_cfg.get("transport") != "stdio":
    fail("config.mcp.byrdhouse-belt must use STDIO")
if belt_cfg.get("script") != "scripts/byrd_belt_mcp.py":
    fail("config.mcp.byrdhouse-belt must point to scripts/byrd_belt_mcp.py")
if not (ROOT / belt_cfg["script"]).is_file():
    fail("the configured ByrdHouse Belt MCP script does not exist")

for path in (ROOT / "integrations").glob("*.mcp.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    server = data.get("mcpServers", {}).get("byrdhouse-belt")
    if not server:
        fail(f"{path.name} is missing mcpServers.byrdhouse-belt")
    if server.get("command") != "python":
        fail(f"{path.name} must use the python command")
    if not server.get("args") or not server["args"][0].endswith("scripts\\byrd_belt_mcp.py"):
        fail(f"{path.name} must launch scripts\\byrd_belt_mcp.py")
    if server.get("env", {}).get("BYRD_BELT_MCP_READONLY") != "1":
        fail(f"{path.name} must default to read-only")
    expected_root = "E:\\ByrdHouse" if "gaming" in path.name else "D:\\ByrdHouse"
    if server.get("env", {}).get("BYRDHOUSE_ROOT") != expected_root:
        fail(f"{path.name} must use BYRDHOUSE_ROOT={expected_root}")
    if server["args"][0] != expected_root + "\\scripts\\byrd_belt_mcp.py":
        fail(f"{path.name} has a mismatched MCP script path")

print("operator endpoints and MCP templates: valid")
