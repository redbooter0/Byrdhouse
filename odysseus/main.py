"""
Odysseus — ByrdHouse AI gateway.

FastAPI app wiring together:
  - /api/home/*  Smart home control (Home Assistant, scenes, shell, system stats)
  - /v1/*        OpenAI-compatible gateway to Ollama (chat, models, embeddings)
  - /static/*    Dashboard frontend (home.html)
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes.home_routes import router as home_router
from routes.ollama_gateway import router as ollama_router

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="Odysseus", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home_router)
app.include_router(ollama_router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
@app.get("/home")
async def home_page():
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
