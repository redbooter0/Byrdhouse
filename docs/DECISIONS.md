# ByrdHouse DECISIONS

*Append-only log. One line per decision: date · decision · why. Never edit old lines.*

- 2026-07-10 · Treat U0 as functionally complete and move active work to U1 Image Lab; setup/status commands are gated by anti-loop rules · prevents future sessions from re-running machine setup instead of using the working belt
- 2026-07-10 · Built the full software side (U0–U3 + judge + dashboard) up front per founder request; unlocks still gate what gets USED and verified on hardware, but the code ships now so machines only need config + debugging · founder decision overrides build-in-order
- 2026-07-10 · Router implemented with Python stdlib (http.server + sqlite3) instead of FastAPI — same v2 §6 contract, zero pip installs on the machines; can swap frameworks later without changing routes · fewer failure modes on fresh Windows boxes
- 2026-07-10 · Until BYRD-MINI is set up, BYRD-GAMING hosts the router (startup.run_router=true); when MINI arrives: flip run_router false on GAMING, true on MINI, point services.router at byrd-mini, copy db/byrdhouse.db over · belt owner is MINI per blueprint, GAMING is a temporary host
- 2026-07-10 · Memory/Qdrant live on BYRD-MINI with sqlite_db=D:/ByrdHouse/db/byrdhouse_memory.db, sqlite_table=memories, qdrant_collection=byrdhouse_memories · keeps the ops memory stack off the gaming worker box
- 2026-07-10 · GitHub repo (redbooter0/Byrdhouse) is the source of truth for the U0 kit; machines sync FROM the repo via setup scripts · kills the "living doc drifts" problem with version control
- 2026-07-10 · Odysseus/smart-home/Stripe stack removed from repo; Cherry Studio remains the user-facing model GUI and ByrdHouse focuses on router/worker/dashboard/image/video/game/MCP belt · founder clarified Odysseus was not planned or needed
- 2026-07-09 · Realms/Godot weekend lane opens now (Cherry Studio + Godot MCP); belt integration waits for U6 · ROOM_MAP correction
- 2026-07-09 · Engine verdict: Godot (featherweight editor, headless CLI, MCP ecosystem); Unity only if mobile/asset-store need appears; Unreal parked · ROOM_MAP
- 2026-07-08 · ByrdHouse is a creator platform, not a mining platform; miners manual + seasonal · STATE direction
- 2026-07-08 · 5080 order: let expire — kept $1,456; hardware rule: cash only, no financing · Blueprint v3 Layer 0
- 2026-07-08 · Phases collapsed into unlocks U0–U6 + Frozen Backlog; numbered-phase prose retired · Blueprint v2
- 2026-07-08 · No new model downloads (freeze stands); no Redis/broker — SQLite WAL is the queue at this scale · Blueprint v2
- 2026-07-11 · Belt exposed as an MCP server (byrd_belt_mcp.py) so one shared tool roster drives it from any client on either machine; bot NEVER drives ComfyUI directly (mode ritual); autonomy = BYRD_BELT_MCP_READONLY permission flag, not a new build · founder dream: always-on operator on both PCs
- 2026-07-12 · Phase B Product Recovery Sprint: dashboard redesigned from 16 rooms to 3 tabs (Home/Create/Library) + hidden System panel; all backend behavior preserved, zero router/worker changes; no room earns main nav until real output has passed through it · founder identified the app became an admin console instead of a command center; the machinery was showing instead of being hidden
- 2026-07-12 · Identity profiles live under profiles/{id}/ with profile.json schema and references/ for face photos; reference photos gitignored (personal); worker auto-resolves face from profile dir when recipe has subject_profile · Creator V1 spec: recurring subject identity preservation via IP-Adapter FaceID
- 2026-07-13 · The GAMING anime target-edit lane uses a compact SD1.5-scale Meina base + optional LCM draft LoRA, with face-only img2img/inpaint and an owner-authorized identity LoRA; Flux2/SDXL and InsightFace swaps are excluded from the funded application lane · fits the 8 GB RTX 3070, preserves the belt, and avoids a non-commercial face-recognition dependency
