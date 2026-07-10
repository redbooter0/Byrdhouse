# ByrdHouse - Smart Home AI Hub

## Overview
ByrdHouse is a modern smart home dashboard with AI-powered voice control, multi-model support, and monetization features.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ByrdHouse Frontend                      │
│              (Modern SPA - home.html + dashboard)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Reverse Proxy (Caddy)                    │
│              SSL termination, routing, caching              │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ byrdhouse-  │      │  Odysseus   │      │   Home      │
│  backend    │      │  (Python)   │      │  Assistant  │
│  (Node.js)  │      │  FastAPI    │      │   (HA)      │
│  :3001      │      │  :3000      │      │  :8123      │
└─────────────┘      └─────────────┘      └─────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │    Ollama + HF     │
                    │   (Local Models)    │
                    │   + HuggingFace    │
                    │   Inference API    │
                    └─────────────────────┘
```

## Features

### Dashboard
- [x] Real-time entity control (lights, switches, climate, etc.)
- [x] Quick scenes (Good Morning, Good Night, Movie Mode, Away, Home)
- [x] AI chat widget with model selection
- [x] System stats (CPU, Memory, Disk, Uptime)
- [x] Shell console for home server
- [x] Ad rotation system withbacker priority

### AI Integration
- [x] Ollama gateway (OpenAI-compatible API)
- [x] HuggingFace Inference API integration
- [x] Multiple model support (Llama, Qwen, Gemma, Mistral, DeepSeek)
- [x] Streaming responses
- [x] Model switching via UI

### Monetization
- [x] Ad rotation with refresh on completion
- [x] Backer priority rotation
- [x] Multiple ad slots (sidebar, interstitial, native)
- [x] User data options (opt-in analytics)

### API Endpoints

#### ByrdHouse Backend (port 3001)
- `POST /api/create-checkout-session` - Stripe checkout
- `POST /api/create-portal-session` - Stripe billing portal
- `POST /api/webhook` - Stripe webhooks
- `POST /api/chat` - Non-streaming AI chat
- `POST /api/chat/stream` - Streaming AI chat
- `GET /api/models` - List available models
- `POST /api/home/chat` - Smart home AI control
- `GET /api/prices` - Get Stripe products

#### Odysseus (port 3000)
- `GET /api/home/status` - HA connection status
- `GET /api/home/ha/states` - All entity states
- `POST /api/home/ha/services` - Call HA services
- `POST /api/home/scene/{name}` - Trigger scenes
- `POST /api/home/shell` - Execute shell commands
- `GET /api/home/system/info` - System stats
- `GET /v1/chat/completions` - OpenAI-compatible chat
- `GET /v1/models` - List Ollama models
- `POST /v1/embeddings` - Generate embeddings

## Environment Variables

```env
# ByrdHouse Backend
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=http://localhost
ODYSSEUS_URL=http://localhost:3000
ODYSSEUS_MODEL=llama3.2:latest

# Odysseus
HOME_ASSISTANT_URL=http://homeassistant:8123
HOME_ASSISTANT_TOKEN=your_token
OLLAMA_BASE=http://localhost:11434
OLLAMA_MODEL_DIR=E:/ollama-models
```

## Quick Start

```bash
# Start with Docker
cd byrdhouse
docker-compose up -d

# Or manually
cd backend && npm install && npm start
cd odysseus && pip install -r requirements.txt && uvicorn main:app
```

## Recommended Models

### For Smart Home Control (Low Latency)
1. **Qwen 2.5** - Best for HA integration
2. **Llama 3.2** - General purpose, good balance
3. **Gemma 4** - Fast, good reasoning

### For Conversational AI
1. **DeepSeek-V4-Flash** - Best value, 1M context
2. **Qwen3.5-397B** - Highest quality
3. **Gemma-4-31B** - Google quality

### For Tool Use/Function Calling
1. **gpt-oss-120b** - Best structured output
2. **Qwen3-235B** - Excellent tool use
3. **Command-R+** - Built for RAG

## HuggingFace Integration

ByrdHouse supports HuggingFace Inference API for:
- Cloud model access (DeepSeek, Qwen, Gemma via providers)
- Embeddings generation
- Model inference without local GPU

Set `HUGGINGFACE_TOKEN` in environment to enable.

## Ad System

### Ad Types
- **Sidebar Ads**: Fixed position, rotates every 60s or on completion
- **Interstitial Ads**: Full-screen on scene triggers
- **Native Ads**: Contextual, integrated into content

### Backer Priority
Backers get priority in ad rotation:
1. Verified backers (Stripe subscription)
2. Free tier users

### Refresh Strategy
- Sidebar: Refresh after 60s or ad completion
- Interstitial: Trigger on scene activation
- Native: Refresh every 5 items

## License

MIT