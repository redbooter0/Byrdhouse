# The Belt — what it is, and how it compounds

*Canonical reference for ByrdHouse's job engine. The belt is the right idea;
this is how we strengthen it without importing a framework. Paste to any AI to
resume architectural work.*

## What the belt is (reverse-engineered from durable-execution systems)

Strip the theme away and ByrdHouse's core is a **durable job queue** — the same
shape as Temporal, river (Go), Oban (Elixir), or Sidekiq, built stdlib-only on
SQLite (WAL). It already has the load-bearing pieces those systems are famous for:

| Canonical pattern | Where the belt already has it |
|---|---|
| Durable queue | `jobs` table, SQLite WAL (survives restart) |
| Pull-based workers | `POST /jobs/claim` (atomic UPDATE…WHERE status='queued') |
| At-least-once + retry→dead | `attempts`/`max_attempts`, `fail_job()` |
| Liveness / orphan recovery | `reaper()` requeues jobs whose worker went silent |
| Event log (event sourcing spine) | `events` table — append-only, every state change |
| Read model / projection | `/stats`, `/reports/daily`, and now `/learn` |
| Priority scheduling | `ORDER BY priority DESC, created_at ASC` |
| Capability routing | `required_mode` / `required_caps` matched at claim |
| Idempotency (exactly-once submit) | `idempotency_key` + partial unique index |

That table is the point: **we didn't need the framework — we needed its
patterns, and we can add the rest one compounding piece at a time.**

## The compounding ladder (each rung multiplies the ones below)

### Shipped
- **Idempotency keys** — a double-tap or retry with the same key returns the
  existing job. Kills duplicate jobs at the source (we'd previously only fixed
  duplicate *artifacts* downstream).
- **Migration spine** (`migrate()`) — guarded additive `ALTER TABLE`s so the
  belt's schema can evolve on live machine DBs without a wipe. Every rung below
  becomes a one-line migration.
- **Learn loop** (`/learn`) — projects approve/reject history into approval-rate
  rankings by recipe/checkpoint/palette/lighting. Reverse-engineered RLHF from
  data we already store.

### Reserved (columns already migrated in, logic pending a greenlight)
- **`parent_id` — job chaining / DAG.** Today a generate job *imperatively*
  enqueues its judge job from inside the worker. With `parent_id`, chains become
  data: lineage graphs ("this thumbnail ← this generate ← this chat request"),
  fan-in gates ("when all 4 judges finish, run pick-best"), and whole-workflow
  retry. **This is the spine of the video pipeline** (transcribe → clip →
  thumbnail → package → post as one chain). Highest structural leverage.
- **`run_after` — deferred / scheduled jobs.** Claim ignores jobs whose
  `run_after` is in the future. Unlocks: exponential backoff on retry
  (`run_after = now + 2^attempts`, so a failing ComfyUI stops hammering itself),
  recurring jobs (fold `backup-nightly.ps1` into the belt as a real job), and
  "generate a batch every morning."

### The payoff rung (greenlight-gated — changes creative output)
- **Bias generation toward winners.** The learn loop *reads*; this makes it
  *act*. When `byrdimage` picks from a recipe's `vary` lists, weight the random
  choice by historical approval rate from `/learn`. The belt starts producing
  more of what you actually approve — local, self-improving, zero new deps.
  U4. Ask before enabling: it changes what comes out.

## Rules any belt upgrade must keep (from the blueprints)
- Stdlib only on the machines — no pip/framework. Every rung above obeys this.
- SQLite (WAL) is the queue. No Redis/brokers at this scale.
- Everything is a job; every state change writes an event.
- Dashboard has no logic — new capability is an endpoint first, a button second.
- No artifact without a card; recipes over prompts.

## Security & trust boundary (be honest about what this is)

The belt is a **trusted single-user system on a private tailnet** — correct for
one founder, NOT a multi-user SaaS backend. Known, deliberate boundaries:

- One global admin bearer token; several GET endpoints are open; CORS is
  permissive; the dashboard stores the token in browser localStorage. Fine on a
  private tailnet during development. Before any outside user / public host,
  this needs real auth, per-user scoping, and locked-down CORS. Do not pretend
  otherwise.
- **Token hygiene**: the config in git is a template (`admin_token` must stay
  `CHANGE_ME…`); real tokens live only on the machines. CI's `secret-scan` job
  fails the build if a real token or key lands in a tracked file. A token that
  ever reached public history is compromised — rotate on the machines, don't
  just edit `main`.

Agent-safety guardrails (in place; tighten before the tool roster grows to
code/file/publish):
- **Judging requires a vision model.** A text-only model may chat and enhance
  prompts but may NOT invent visual quality scores — the artifact stays
  honestly unjudged instead (protects the learn-loop dataset).
- **Chat mutation budget.** Write-class tools (queue/refine) are capped per
  request so one model turn can't spawn a flood of jobs; read tools are free.
- **Checkpoint fallback is recorded**, not silent — the card carries
  requested-vs-resolved and the gallery flags it yellow.
- Every tool acts only through the same audited belt endpoints the dashboard
  uses; every action writes an event. Confirmation gating for
  expensive/destructive actions comes before code/file/publish tools land.

Deferred hardening (tracked, not yet needed):
- **Video will break the heartbeat model** — the worker's heartbeat pauses
  during a job; long video/upscale jobs will trip the 15-min reaper. Move
  heartbeats to a separate thread or use renewable leases *before U5*.
- **Split the monolith after U1 is proven** — `router.py` and the one-file
  dashboard are the right call for U0/U1 (no build chain, serves from the
  router, iPad-friendly), but split along boundaries before adding video, code
  execution, users, and publishing.

## Why not import Temporal/river/an MCP job server
They're heavier than this scale needs, they'd break the stdlib-only rule, and —
the real reason — **the belt already is one.** Reverse-engineering the patterns
keeps the whole system inspectable in one `router.py` a founder can read, which
is worth more here than any feature a framework would add.
