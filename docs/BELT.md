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

## Why not import Temporal/river/an MCP job server
They're heavier than this scale needs, they'd break the stdlib-only rule, and —
the real reason — **the belt already is one.** Reverse-engineering the patterns
keeps the whole system inspectable in one `router.py` a founder can read, which
is worth more here than any feature a framework would add.
