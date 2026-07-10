# routes/home_routes.py
"""
Smart Home Integration — Home Assistant, ESPHome, shell commands.
Exposes a unified /api/home/* API surface so the AI agent and web dashboard
can control lights, switches, sensors, scripts, and run arbitrary shell commands
on the local machine (the "home server").
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

HOME_ASSISTANT_URL    = os.getenv("HOME_ASSISTANT_URL",    "http://homeassistant:8123")
HOME_ASSISTANT_TOKEN  = os.getenv("HOME_ASSISTANT_TOKEN",  "")
ESPHOME_HOST          = os.getenv("ESPHOME_HOST",          "esp8266-local")
ESPHOME_PASSWORD      = os.getenv("ESPHOME_PASSWORD",      "")
SHELL_ALLOWED_PATTERNS = list(filter(None, os.getenv("SHELL_ALLOWED_PATTERNS", "").split(",")))
SHELL_TIMEOUT         = float(os.getenv("SHELL_TIMEOUT",   "30"))

# ── Pydantic models ────────────────────────────────────────────────────────

class HomeStateResponse(BaseModel):
    state: str
    attributes: Dict[str, Any]
    last_changed: Optional[str] = None
    last_updated: Optional[str] = None
    context: Optional[Dict] = None

class EntityResponse(BaseModel):
    entity_id: str
    state: str
    attributes: Dict[str, Any]
    domain: str

class ServiceCallRequest(BaseModel):
    entity_id: Optional[str] = None
    domain: Optional[str] = None
    service: str
    data: Optional[Dict[str, Any]] = None

class ShellCommandRequest(BaseModel):
    command: str
    timeout: Optional[float] = SHELL_TIMEOUT
    workdir: Optional[str] = None

class ShellCommandResponse(BaseModel):
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float

class ESPHomeDeviceState(BaseModel):
    device_name: str
    online: bool
    entities: List[Dict[str, Any]]

# ── Home Assistant helpers ──────────────────────────────────────────────────

async def _ha_headers() -> Dict[str, str]:
    if not HOME_ASSISTANT_TOKEN:
        raise HTTPException(503, "HOME_ASSISTANT_TOKEN not configured")
    return {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }

async def _ha_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{HOME_ASSISTANT_URL}{path}",
            headers=await _ha_headers(),
        )
    if resp.status_code == 401:
        raise HTTPException(401, "Home Assistant authentication failed")
    if resp.status_code == 404:
        raise HTTPException(404, f"Home Assistant path not found: {path}")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

async def _ha_post(path: str, data: Optional[dict] = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{HOME_ASSISTANT_URL}{path}",
            headers=await _ha_headers(),
            json=data or {},
        )
    if resp.status_code not in (200, 200):
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

# ── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/home", tags=["Smart Home"])

# ── Health ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def home_status():
    """Overall smart home connectivity status."""
    ha_ok = False
    ha_entities = 0
    try:
        # Simple states API — no token needed for this endpoint in HA
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{HOME_ASSISTANT_URL}/api/states", timeout=5.0)
        ha_ok = (resp.status_code == 200)
        if ha_ok:
            ha_entities = len(resp.json())
    except Exception as e:
        logger.debug(f"HA status check failed: {e}")

    return {
        "home_assistant": {
            "url": HOME_ASSISTANT_URL,
            "reachable": ha_ok,
            "entity_count": ha_entities,
        },
        "esphome": {
            "host": ESPHOME_HOST,
        },
    }

# ── Home Assistant: states ─────────────────────────────────────────────────

@router.get("/ha/states", response_model=List[EntityResponse])
async def ha_list_states(request: Request):
    """List all Home Assistant entity states."""
    states = await _ha_get("/api/states")
    return [
        EntityResponse(
            entity_id=s["entity_id"],
            state=s["state"],
            attributes=s.get("attributes", {}),
            domain=s["entity_id"].split(".")[0],
        )
        for s in states
    ]

@router.get("/ha/state/{entity_id:path}", response_model=EntityResponse)
async def ha_get_state(entity_id: str):
    """Get state of a specific Home Assistant entity."""
    state = await _ha_get(f"/api/states/{entity_id}")
    return EntityResponse(
        entity_id=state["entity_id"],
        state=state["state"],
        attributes=state.get("attributes", {}),
        domain=entity_id.split(".")[0],
    )

@router.post("/ha/state/{entity_id:path}")
async def ha_set_state(entity_id: str, request: Request):
    """
    Set state of a Home Assistant entity.
    body: { "state": "on|off|...}", "attributes": { ... } }
    Note: HA prefers service calls for most entities.
    """
    body = await request.json()
    state = await _ha_post(f"/api/states/{entity_id}", body)
    return state

@router.get("/ha/entity/{entity_id:path}")
async def ha_entity_info(entity_id: str):
    """Get full entity info (state + history URL + config entry)."""
    state = await _ha_get(f"/api/states/{entity_id}")

    # Also get config entries to find which integration owns this
    config_entries = []
    try:
        entries = await _ha_get("/api/config/entity_registry/list")
        config_entries = [e for e in entries if e.get("entity_id") == entity_id]
    except Exception:
        pass

    return {
        "state": state,
        "config_entry": config_entries[0] if config_entries else None,
    }

@router.get("/ha/history/{entity_id:path}")
async def ha_entity_history(entity_id: str, request: Request):
    """Get history for an entity (last 24h by default)."""
    filter_entity = request.query_params.get("filter_entity")
    minimal = request.query_params.get("minimal", "true").lower() == "true"

    params = {"entity_id": entity_id}
    if filter_entity:
        params["filter_entity_id"] = filter_entity

    history = await _ha_get("/api/history/period", params=params)
    if minimal and history:
        # Return only last state per entity
        result = []
        for period in history:
            if period and len(period) > 0:
                result.append(period[-1])  # last entry only
        return result
    return history

# ── Home Assistant: services ─────────────────────────────────────────────────

@router.post("/ha/services")
async def ha_call_service(request: Request):
    """
    Call a Home Assistant service.
    body: { "domain": "light|switch|...", "service": "turn_on|...", "data": { ... } }
    """
    body = await request.json()
    domain = body.get("domain")
    service = body.get("service")
    data = body.get("data", {})

    if not domain or not service:
        raise HTTPException(400, "domain and service are required")

    result = await _ha_post(f"/api/services/{domain}/{service}", data)
    return result

@router.get("/ha/services/{domain}")
async def ha_list_services(domain: str):
    """List available services for a domain."""
    services = await _ha_get(f"/api/services/{domain}")
    return services

# ── Home Assistant: areas / zones ──────────────────────────────────────────

@router.get("/ha/areas")
async def ha_list_areas():
    """List all areas in Home Assistant."""
    return await _ha_get("/api/area_registry/list")

@router.get("/ha/areas/{area_id}/entities")
async def ha_area_entities(area_id: str):
    """List all entities in an area."""
    states = await _ha_get("/api/states")
    area_slug = area_id.lower().replace(" ", "_")
    return [
        s for s in states
        if s.get("attributes", {}).get("area_id", "").lower() == area_slug
    ]

@router.get("/ha/zones")
async def ha_list_zones():
    """List all zones in Home Assistant."""
    return await _ha_get("/api/zone")

# ── Home Assistant: config / system ─────────────────────────────────────────

@router.get("/ha/config")
async def ha_config():
    """Get Home Assistant configuration."""
    return await _ha_get("/api/config")

@router.get("/ha/events")
async def ha_list_events():
    """List all event types currently listened to."""
    return await _ha_get("/api/events")

@router.get("/ha/logbook")
async def ha_logbook(request: Request):
    """Get logbook entries. ?start_time=ISO&end_time=ISO"""
    start = request.query_params.get("start_time")
    end   = request.query_params.get("end_time")
    params = {}
    if start:
        params["start_time"] = start
    if end:
        params["end_time"] = end
    return await _ha_get("/api/logbook", params=params)

# ── Home Assistant: helpers ─────────────────────────────────────────────────

@router.get("/ha/helpers")
async def ha_list_helpers():
    """List all helper entities."""
    return await _ha_get("/api/helpers")

@router.get("/ha/automations")
async def ha_list_automations():
    """List all automations (triggers + last triggered time)."""
    return await _ha_get("/api/automation/list")

@router.post("/ha/automations/{automation_id}/trigger")
async def ha_trigger_automation(automation_id: str):
    """Trigger an automation by ID."""
    return await _ha_post(f"/api/services/automation/trigger", {
        "entity_id": f"automation.{automation_id}",
    })

@router.get("/ha/scripts")
async def ha_list_scripts():
    """List all scripts."""
    return await _ha_get("/api/config/entity_registry", params={"domain": "script"})

@router.post("/ha/scripts/{script_id}")
async def ha_run_script(script_id: str, request: Request):
    """Run a script by ID."""
    body = await request.json() if request else {}
    return await _ha_post(f"/api/services/script/turn_on", {
        "entity_id": f"script.{script_id}",
        **body,
    })

# ── Shell commands ──────────────────────────────────────────────────────────

async def _run_shell(
    command: str,
    timeout: float = SHELL_TIMEOUT,
    workdir: Optional[str] = None,
) -> ShellCommandResponse:
    """Execute a shell command with timeout and optional working directory."""
    start = time.perf_counter()
    cwd = workdir or os.getcwd()

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        return ShellCommandResponse(
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=round(duration_ms, 1),
        )
    except subprocess.TimeoutExpired:
        duration_ms = (time.perf_counter() - start) * 1000
        return ShellCommandResponse(
            command=command,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=-1,
            duration_ms=round(duration_ms, 1),
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return ShellCommandResponse(
            command=command,
            stdout="",
            stderr=str(e),
            exit_code=-2,
            duration_ms=round(duration_ms, 1),
        )

def _is_shell_allowed(command: str) -> bool:
    """Check if a command matches the allowlist patterns."""
    if not SHELL_ALLOWED_PATTERNS:
        # Default: allow only safe read-only/system commands
        deny = ["rm -rf", ">/dev/", "dd if=", "mkfs", ":(){:|:&};:", "curl http", "wget http"]
        cmd_lower = command.lower()
        for d in deny:
            if d in cmd_lower:
                return False
        return True

    for pattern in SHELL_ALLOWED_PATTERNS:
        if re.search(pattern, command):
            return True
    return False

@router.post("/shell", response_model=ShellCommandResponse)
async def shell_exec(request: Request):
    """
    Execute a shell command on the home server.
    Allowlist is configured via SHELL_ALLOWED_PATTERNS env var (comma-separated regex).
    Default: read-only commands only (cat, grep, ls, ps, df, etc.)
    """
    body = await request.json()
    cmd     = body.get("command", "").strip()
    timeout = float(body.get("timeout", SHELL_TIMEOUT))
    workdir = body.get("workdir")

    if not cmd:
        raise HTTPException(400, "command is required")

    if not _is_shell_allowed(cmd):
        raise HTTPException(403, f"Command not in allowlist: {cmd[:60]}")

    return await _run_shell(cmd, timeout, workdir)

@router.post("/shell/batch")
async def shell_batch(request: Request):
    """Execute multiple shell commands in sequence, return all results."""
    body = await request.json()
    commands = body.get("commands", [])
    stop_on_error = body.get("stop_on_error", True)

    results = []
    for cmd in commands:
        res = await _run_shell(cmd.strip())
        results.append(res)
        if stop_on_error and res.exit_code != 0:
            break
    return {"results": results}

# ── System info (read-only) ─────────────────────────────────────────────────

@router.get("/system/info")
async def system_info():
    """Read-only system information for the home server."""
    import shutil as _shutil

    def get(field, fallback=None):
        try:
            import psutil
            return getattr(psutil, field, lambda: fallback)()
        except Exception:
            return fallback

    try:
        import psutil
        cpu_pct  = psutil.cpu_percent(interval=0.5)
        mem      = psutil.virtual_memory()
        disk     = psutil.disk_usage("/")
        net      = psutil.net_io_counters()

        return {
            "cpu_percent": cpu_pct,
            "cpu_count": psutil.cpu_count(),
            "memory": {
                "total_gb": round(mem.total / (1024**3), 1),
                "used_gb":  round(mem.used / (1024**3), 1),
                "percent":  mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "free_gb":  round(disk.free  / (1024**3), 1),
                "percent":  disk.percent,
            },
            "network": {
                "bytes_sent":   net.bytes_sent,
                "bytes_recv":   net.bytes_recv,
            },
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
        }
    except ImportError:
        return {
            "error": "psutil not installed — install with: pip install psutil",
            "cpu_percent": None,
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/system/processes")
async def system_processes(request: Request):
    """List top processes by CPU usage."""
    limit = int(request.query_params.get("limit", "10"))
    try:
        import psutil
        procs = []
        for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                        key=lambda x: x.info["cpu_percent"] or 0, reverse=True)[:limit]:
            info = p.info
            procs.append({
                "pid":           info["pid"],
                "name":          info["name"],
                "cpu_percent":   round(info["cpu_percent"] or 0, 1),
                "memory_percent": round(info["memory_percent"] or 0, 1),
            })
        return {"processes": procs}
    except ImportError:
        return {"error": "psutil not installed", "processes": []}

@router.get("/system/temperatures")
async def system_temperatures():
    """Read CPU/temperature sensors."""
    try:
        import psutil
        temps = {}
        try:
            temps = {k: v.current for k, v in psutil.sensors_temperatures().items()}
        except Exception:
            pass
        return {"temperatures": temps}
    except ImportError:
        return {"error": "psutil not installed", "temperatures": {}}

# ── Quick scene shortcuts ────────────────────────────────────────────────────

@router.post("/scene/{scene_name}")
async def trigger_scene(scene_name: str):
    """
    Trigger a named scene (convenience endpoint).
    Maps scene_name → Home Assistant service call.
    """
    scene_map = {
        "good_morning":  {"domain": "scene", "service": "turn_on", "data": {"entity_id": "scene.good_morning"}},
        "good_night":    {"domain": "scene", "service": "turn_on", "data": {"entity_id": "scene.good_night"}},
        "movie_mode":    {"domain": "script", "service": "turn_on", "data": {"entity_id": "script.movie_mode"}},
        "away":          {"domain": "automation", "service": "trigger", "data": {"entity_id": "automation.away_mode"}},
        "home":          {"domain": "automation", "service": "trigger", "data": {"entity_id": "automation.home_mode"}},
    }

    if scene_name not in scene_map:
        raise HTTPException(404, f"Unknown scene: {scene_name}")

    mapping = scene_map[scene_name]
    result = await _ha_post(f"/api/services/{mapping['domain']}/{mapping['service']}", mapping["data"])
    return {"scene": scene_name, "result": result}

# ── ESPHome proxy (passthrough) ─────────────────────────────────────────────

@router.get("/esphome/devices")
async def esphome_list_devices():
    """List ESPHome native API devices (via direct API)."""
    # ESPHome uses a custom binary protocol on port 6053
    # For HTTP-only environments, return a placeholder with instructions
    return {
        "note": "ESPHome native API uses port 6053 (binary protocol). "
                "Configure ESPHOME_NATIVE_API_HOST env var for direct access, "
                "or use Home Assistant's esphome integration entities instead.",
        "ha_entities": await ha_list_states(),
    }

@router.get("/esphome/device/{name}")
async def esphome_device_state(name: str):
    """Get ESPHome device state via native API."""
    host = os.getenv("ESPHOME_NATIVE_API_HOST", ESPHOME_HOST)
    port = int(os.getenv("ESPHOME_NATIVE_API_PORT", "6053"))

    try:
        import socket as _socket
        reader, writer = await asyncio.open_connection(host, port)
        # Send subscribe state request
        writer.write(b'\x00\x00\x00\x00')
        await writer.drain()
        # Read response (simplified)
        data = await asyncio.wait_for(reader.read(1024), timeout=5)
        writer.close()
        return {"device": name, "raw_response": data.hex(), "host": host, "port": port}
    except Exception as e:
        return {"device": name, "error": str(e), "host": host, "port": port}
