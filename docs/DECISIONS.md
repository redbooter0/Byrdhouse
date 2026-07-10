# ByrdHouse DECISIONS

*Append-only log. One line per decision: date · decision · why. Never edit old lines.*

- 2026-07-10 · Built the full software side (U0–U3 + judge + dashboard) up front per founder request; unlocks still gate what gets USED and verified on hardware, but the code ships now so machines only need config + debugging · founder decision overrides build-in-order
- 2026-07-10 · Router implemented with Python stdlib (http.server + sqlite3) instead of FastAPI — same v2 §6 contract, zero pip installs on the machines; can swap frameworks later without changing routes · fewer failure modes on fresh Windows boxes
- 2026-07-10 · Until BYRD-MINI is set up, BYRD-GAMING hosts the router (startup.run_router=true); when MINI arrives: flip run_router false on GAMING, true on MINI, point services.router at byrd-mini, copy db/byrdhouse.db over · belt owner is MINI per blueprint, GAMING is a temporary host
- 2026-07-10 · Memory/Qdrant live on BYRD-MINI with sqlite_db=D:/ByrdHouse/db/byrdhouse_memory.db, sqlite_table=memories, qdrant_collection=byrdhouse_memories · keeps the ops memory stack off the gaming worker box
- 2026-07-10 · GitHub repo (redbooter0/Byrdhouse) is the source of truth for the U0 kit; machines sync FROM the repo via setup scripts · kills the "living doc drifts" problem with version control
- 2026-07-10 · Smart-home hub code (backend/ + odysseus/) kept in repo as an auxiliary component; Stripe/monetization surface is FROZEN per Blueprint v2 §1.8 (no external users yet) · nothing deleted, nothing built on it until demand
- 2026-07-09 · Realms/Godot weekend lane opens now (Cherry Studio + Godot MCP); belt integration waits for U6 · ROOM_MAP correction
- 2026-07-09 · Engine verdict: Godot (featherweight editor, headless CLI, MCP ecosystem); Unity only if mobile/asset-store need appears; Unreal parked · ROOM_MAP
- 2026-07-08 · ByrdHouse is a creator platform, not a mining platform; miners manual + seasonal · STATE direction
- 2026-07-08 · 5080 order: let expire — kept $1,456; hardware rule: cash only, no financing · Blueprint v3 Layer 0
- 2026-07-08 · Phases collapsed into unlocks U0–U6 + Frozen Backlog; numbered-phase prose retired · Blueprint v2
- 2026-07-08 · No new model downloads (freeze stands); no Redis/broker — SQLite WAL is the queue at this scale · Blueprint v2
