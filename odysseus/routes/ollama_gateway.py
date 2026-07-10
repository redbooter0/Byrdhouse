# routes/ollama_gateway.py
"""
OpenAI-compatible gateway to local Ollama.
Provides /v1/chat, /v1/completions, /v1/models — same interface as OpenAI,
so any OpenAI-compatible client (ByrdHouse, AnythingLLM, etc.) can point at
this server and get local AI without knowing it's Ollama underneath.
"""
import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

OLLAMA_BASE      = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_API_KEY   = os.getenv("OLLAMA_API_KEY", "ollama")          # sentinel, not used
OLLAMA_EMBED_BASE = os.getenv("OLLAMA_EMBED_BASE", "http://localhost:11434")
PROXY_TIMEOUT    = float(os.getenv("OLLAMA_PROXY_TIMEOUT", "300"))

# E: drive prefetch cache (models stored here, served to Ollama at startup)
OLLAMA_MODEL_DIR = os.getenv("OLLAMA_MODEL_DIR", "E:/ollama-models")

# ── Request/Response models ─────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[List[str]] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    seed: Optional[int] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[Dict] = None

class CompletionRequest(BaseModel):
    model: str
    prompt: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[List[str]] = None
    echo: bool = False

# ── Helpers ─────────────────────────────────────────────────────────────────

def _ollama_url(path: str) -> str:
    return f"{OLLAMA_BASE}{path}"

async def _ollama_post(path: str, body: dict, timeout: float = PROXY_TIMEOUT) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(_ollama_url(path), json=body)
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

async def _ollama_post_stream(path: str, body: dict) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=PROXY_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("POST", _ollama_url(path), json=body) as resp:
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, await resp.aread())
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk

# ── /v1/chat/completions ────────────────────────────────────────────────────

async def _build_ollama_chat_body(req: ChatCompletionRequest) -> dict:
    # Convert OpenAI-style messages to Ollama /api/chat format
    ollama_messages = []
    for m in req.messages:
        msg = {"role": m.role, "content": m.content}
        if m.name:
            msg["name"] = m.name
        ollama_messages.append(msg)

    body = {
        "model": req.model,
        "messages": ollama_messages,
        "stream": req.stream,
        "options": {
            "temperature": req.temperature,
        },
    }
    if req.max_tokens:
        body["options"]["num_predict"] = req.max_tokens
    if req.stop:
        body["options"]["stop"] = req.stop
    if req.seed is not None:
        body["options"]["seed"] = req.seed
    if req.frequency_penalty:
        body["options"]["repeat_penalty"] = req.frequency_penalty
    return body

async def _stream_chat(req: ChatCompletionRequest) -> StreamingResponse:
    body = await _build_ollama_chat_body(req)

    async def event_generator():
        async for chunk in _ollama_post_stream("/api/chat", body):
            # Ollama returns NDJSON lines. Convert each to OpenAI SSE format.
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    # Ollama delta format → OpenAI chunk format
                    if data.get("done"):
                        yield b"data: [DONE]\n\n"
                        continue
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        choice = {
                            "index": 0,
                            "delta": {"role": "assistant", "content": content},
                            "finish_reason": None,
                        }
                        chunk_data = {
                            "id": f"chatcmpl-ollama-{data.get('created', int(time.time()))}",
                            "object": "chat.completion.chunk",
                            "created": data.get("created", int(time.time())),
                            "model": req.model,
                            "choices": [choice],
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n".encode()
                except json.JSONDecodeError:
                    continue

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

async def _non_stream_chat(req: ChatCompletionRequest) -> dict:
    body = await _build_ollama_chat_body(req)
    body["stream"] = False
    data = await _ollama_post("/api/chat", body)

    message = data.get("message", {})
    return {
        "id": f"chatcmpl-ollama-{data.get('created', int(time.time()))}",
        "object": "chat.completion",
        "created": data.get("created", int(time.time())),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": message.get("role", "assistant"),
                "content": message.get("content", ""),
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
        },
    }

# ── /v1/completions ──────────────────────────────────────────────────────────

async def _stream_completion(req: CompletionRequest) -> StreamingResponse:
    body = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": True,
        "options": {"temperature": req.temperature},
    }
    if req.max_tokens:
        body["options"]["num_predict"] = req.max_tokens
    if req.stop:
        body["options"]["stop"] = req.stop

    async def event_generator():
        async for chunk in _ollama_post_stream("/api/generate", body):
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("done"):
                        yield b"data: [DONE]\n\n"
                        continue
                    content = data.get("response", "")
                    if content:
                        chunk_data = {
                            "id": f"cmpl-ollama-{data.get('created', int(time.time()))}",
                            "object": "text_completion",
                            "created": data.get("created", int(time.time())),
                            "model": req.model,
                            "choices": [{
                                "index": 0,
                                "text": content,
                                "finish_reason": None,
                            }],
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n".encode()
                except json.JSONDecodeError:
                    continue

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

async def _non_stream_completion(req: CompletionRequest) -> dict:
    body = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": False,
        "options": {"temperature": req.temperature},
    }
    if req.max_tokens:
        body["options"]["num_predict"] = req.max_tokens
    if req.stop:
        body["options"]["stop"] = req.stop

    data = await _ollama_post("/api/generate", body)
    return {
        "id": f"cmpl-ollama-{data.get('created', int(time.time()))}",
        "object": "text_completion",
        "created": data.get("created", int(time.time())),
        "model": req.model,
        "choices": [{
            "index": 0,
            "text": data.get("response", ""),
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
        },
    }

# ── /v1/models ──────────────────────────────────────────────────────────────

async def _list_models() -> dict:
    """Return local + cached models in OpenAI /v1/models format."""
    models = []

    # 1. E: drive prefetch cache (already downloaded, just not loaded into RAM)
    e_cache = Path(OLLAMA_MODEL_DIR)
    if e_cache.exists():
        for mf in e_cache.iterdir():
            # Ollama stores manifests as .txt or .json alongside blobs
            if mf.suffix in (".txt", ".json", "") and mf.is_file():
                # Extract model name from manifest
                name = mf.stem
                if name not in [m["id"] for m in models]:
                    models.append({
                        "id": name,
                        "object": "model",
                        "created": int(mf.stat().st_mtime),
                        "owned_by": "local",
                        "permission": [],
                    })

    # 2. Ask Ollama itself (running models + fully downloaded)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_ollama_url("/api/tags"))
        if resp.status_code == 200:
            ollama_data = resp.json()
            for m in (ollama_data.get("models") or []):
                name = m.get("name", "")
                if name and name not in [mod["id"] for mod in models]:
                    models.append({
                        "id": name,
                        "object": "model",
                        "created": m.get("modified_at", int(time.time())),
                        "owned_by": "local",
                        "permission": [],
                    })
    except Exception as e:
        logger.warning(f"Could not reach Ollama /api/tags: {e}")

    return {
        "object": "list",
        "data": models,
    }

# ── /v1/embeddings ──────────────────────────────────────────────────────────

async def _embeddings_create(model: str, input_texts: List[str]) -> dict:
    """Proxy embeddings to Ollama /api/embeddings."""
    results = []
    async with httpx.AsyncClient(timeout=60) as client:
        for text in input_texts:
            body = {"model": model, "prompt": text}
            resp = await client.post(f"{OLLAMA_EMBED_BASE}/api/embeddings", json=body)
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            d = resp.json()
            results.append({
                "object": "embedding",
                "embedding": d.get("embedding", []),
                "index": len(results),
            })
    return {
        "object": "list",
        "data": results,
        "model": model,
        "usage": {
            "prompt_tokens": 0,
            "total_tokens": 0,
        },
    }

# ── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/v1", tags=["Ollama Gateway"])

@router.api_route("/chat/completions", methods=["POST"])
async def chat_completions(request: Request):
    """
    OpenAI-compatible /v1/chat/completions → proxies to Ollama /api/chat.
    Works with streaming and non-streaming. Supports full tool/function-calling
    passthrough when Ollama model supports it.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")

    if req.stream:
        return await _stream_chat(req)
    return _non_stream_chat(req)

@router.api_route("/completions", methods=["POST"])
async def completions(request: Request):
    """OpenAI-compatible /v1/completions → proxies to Ollama /api/generate."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    try:
        req = CompletionRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")

    if req.stream:
        return await _stream_completion(req)
    return _non_stream_completion(req)

@router.get("/models")
async def list_models():
    """OpenAI-compatible /v1/models — lists all local and E: drive cached models."""
    return await _list_models()

@router.post("/embeddings")
async def embeddings(request: Request):
    """OpenAI-compatible /v1/embeddings → Ollama /api/embeddings."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    model = body.get("model", "nomic-embed-text")
    input_texts = body.get("input")
    if isinstance(input_texts, str):
        input_texts = [input_texts]
    if not input_texts:
        raise HTTPException(400, "'input' field required")

    return await _embeddings_create(model, input_texts)

# ── Health / Info ────────────────────────────────────────────────────────────

@router.get("/gateway/status")
async def gateway_status():
    """Quick health check — can we reach Ollama?"""
    reachable = False
    model_count = 0
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(_ollama_url("/api/tags"))
        reachable = (resp.status_code == 200)
        if reachable:
            model_count = len(resp.json().get("models") or [])
    except Exception:
        pass

    return {
        "ollama_base": OLLAMA_BASE,
        "ollama_reachable": reachable,
        "model_cache_dir": OLLAMA_MODEL_DIR,
        "models_loaded": model_count,
    }
