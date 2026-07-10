# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What ByrdHouse Is

ByrdHouse is a local-first smart home + AI hub: a dashboard with AI-powered voice/chat control, Home Assistant integration, local LLM inference via Ollama, and Stripe-based monetization. It is part of a larger "ByrdHouse platform" vision (command center, job queue, content pipeline) described in the owner's Master Blueprint docs; this repo currently contains the smart-home/AI-hub core.

## Architecture

Two services behind a Caddy reverse proxy, orchestrated with docker-compose:

- **`backend/`** — Node.js/Express (port 3001). Stripe checkout/portal/webhooks (`/api/create-checkout-session`, `/api/webhook`, `/api/prices`) and an AI chat proxy (`/api/chat`, `/api/chat/stream`, `/api/models`) that forwards to Odysseus's OpenAI-compatible endpoint. Single-file server (`server.js`); `middleware/`, `routes/`, `services/` are placeholders for future extraction.
- **`odysseus/`** — Python/FastAPI (port 3000), the AI gateway. `main.py` wires two routers plus the static frontend:
  - `routes/home_routes.py` (`/api/home/*`) — Home Assistant entity states/services, scenes, shell console, system stats.
  - `routes/ollama_gateway.py` (`/v1/*`) — OpenAI-compatible chat completions (streaming + non-streaming), models list, embeddings, backed by a local Ollama server.
  - `src/integrations.py` — user-defined external API integrations stored as JSON, injected into the AI prompt.
  - `static/home.html` — the dashboard SPA (entity control, quick scenes, AI chat widget, ad rotation).
- **`config/Caddyfile`** — SSL termination and routing: static/dashboard → Odysseus, `api.byrdhouse.local` → backend, `ai.byrdhouse.local` → Odysseus.

Request flow for chat: frontend → backend `/api/chat` → Odysseus `/v1/chat/completions` → Ollama. The backend never talks to Ollama directly; always go through the Odysseus gateway.

## Commands

```bash
# Full stack
docker-compose up -d

# Backend only
cd backend && npm install && npm start        # needs .env (see .env.example)

# Odysseus only
cd odysseus && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 3000
```

There is no test suite or linter configured yet. Quick sanity checks: `node --check backend/server.js` and importing the FastAPI app (`python -c "from main import app"` from `odysseus/`).

## Conventions & Constraints

- **Secrets:** `.env` is gitignored and must never be committed. `backend/.env.example` documents required variables (Stripe keys/price IDs, `ODYSSEUS_URL`, `FRONTEND_URL`). Odysseus reads `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN`, `OLLAMA_BASE`, `HUGGINGFACE_TOKEN` from the environment.
- **Local-first:** inference defaults to local Ollama models; HuggingFace Inference API is an optional cloud fallback (enabled by `HUGGINGFACE_TOKEN`).
- **OpenAI compatibility:** the `/v1/*` surface in `ollama_gateway.py` intentionally mirrors the OpenAI API shape so any OpenAI client can point at it. Preserve that contract when changing it.
- **Ports:** Odysseus 3000, backend 3001, Home Assistant 8123, Ollama 11434 — hardcoded in Caddyfile and docker-compose; change them in all three places or not at all.
- The owner prefers GUI/app-first workflows; terminal commands are for setup and maintenance, not the primary UX.
