# AgentFrame

> *AI can build your app in an afternoon. The problem is what happens next.*

After the initial burst of generation, most AI-assisted codebases enter a slow decline. The AI loses the thread. Drift accumulates. You spend more time explaining the codebase back to the AI than you do building. Eventually you realize: the code is the only record of what the product was supposed to be — and it's written in a language designed for machines, not for reasoning.

**AgentFrame takes a different bet.** The *product graph* — not source files — is the source of truth. Generated code is a compilation artifact, like a binary. You never edit it by hand. When something needs to change, an agent proposes a mutation to the graph. Policies validate it. A human approves it. Generators recompile everything. The graph persists. The intent survives.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-35%20passing-brightgreen)](#running-the-test-suite)

---

## The core idea in 60 seconds

```
Traditional approach:          AgentFrame:

  Agent → edits files            Agent → proposes graph mutation
  Files → are the truth          Graph → is the truth
  Drift → accumulates            Graph → is always consistent
  Intent → gets lost             Intent → is queryable forever
  Rollback → git revert          Rollback → graph.replay_to(event_id)
  New agent → reads codebase     New agent → reads graph, understands all
```

The graph is a persistent, queryable record of *what your product is*. The `generated/` directory is disposable. Wipe it, regenerate — same app, perfectly, from unchanged graph state. This means you can swap generators (HTMX → React, SQLite → Postgres models) and rebuild the entire app layer from a product model that never needed to change.

---

## Demo: an agent adds a feature while you watch

```bash
# 1. Install and seed a starter SaaS graph (users, plans, signup, login, dashboard)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
python demo_app/graph_seed.py

# 2. Start the server — generators run at startup, routes appear
agentframe dev
# (or: .venv/bin/uvicorn demo_app.main:app --reload)

# 3. In another terminal — an agent proposes adding a password reset flow
python demo_app/demo_agent.py

# 4. A human reviews the proposal and approves it
open http://localhost:8000/_console/proposals

# 5. The server reloads. The new route is live.
curl http://localhost:8000/password_reset/start   # → HTML, not 404
```

That's the loop: **propose → validate → approve → regenerate → live**. No hand-editing generated code. No merge conflicts. No explaining the codebase to a new session. The graph remembers.

---

## What makes this different

### Intent outlives context windows

A conventional AI-built codebase after six months of changes is opaque to a new agent session. It has to read hundreds of files to piece together what the product is. The graph answers "what flows exist, what entities do they touch, what constraints are enforced" definitively — in a single query — without touching a generated file.

### Policy enforcement that doesn't decay

Define a rule once. It runs on every proposed change, forever.

```python
@policy("no_public_pii")
def check(proposal, graph):
    # Runs on every PatchProposal that touches an entity node
    # Can't be forgotten, can't be bypassed, can't be overridden by a new agent
    # that wasn't briefed on it
    if has_pii_fields(proposal) and not requires_auth(proposal):
        return PolicyResult.fail("no_public_pii",
            "Entity has PII fields but requires_auth is False")
    return PolicyResult.pass_("no_public_pii")
```

Not a linter. Not a comment. Not a PR review checklist. A structural constraint that runs before anything reaches the filesystem.

### Human oversight as architecture, not process

Every structural change passes through `/_console` — a clean approval UI with before/after diffs and policy results — before it touches a file. The sequence of approved proposals is a changelog of product decisions, readable by humans and agents alike.

### Fix the generator, fix everything

A bug or improvement in `route_gen.py` instantly improves every generated route on next regeneration. In a conventional codebase the same fix requires finding and patching every affected file individually.

### Multi-agent safety

When multiple AI sessions work on the same product, they submit proposals to the shared graph — not competing file edits. There are no file-level merge conflicts at the structural level.

---

## How it works

```
                    ┌─────────────────────────────────────────┐
                    │             Product Graph                │
                    │         (SQLite via SQLModel)            │
                    │  nodes: entity · flow · page · policy   │
                    │         integration · (custom)           │
                    │  events: append-only mutation log        │
                    └──────────────┬──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
       PolicyEngine          Executor            GeneratorEngine
    validates every      applies approved        compiles graph →
    PatchProposal         proposals to           generated/ (pure
    before it lands       the graph              functions, deterministic)
              │                    │                    │
              └────────────────────┴────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │         FastAPI App          │
                    │  /mcp  — agent protocol      │
                    │  /_console — approval UI     │
                    │  /api/* — CRUD endpoints     │
                    │  /<flow>/* — flow routes     │
                    └─────────────────────────────┘
```

### The approval loop in detail

```
Agent                Protocol (/mcp)        PolicyEngine        Console (/_console)
  │                       │                      │                      │
  ├─ POST /graph/patch ──►│                      │                      │
  │                       ├─ validate() ────────►│                      │
  │                       │◄─ [results] ─────────┤                      │
  │                       │                      │                      │
  │    copy change +       │                      │                      │
  │    all policies pass?  │                      │                      │
  │◄─ AUTO_APPROVED ───────┤                      │                      │
  │                       │                      │                      │
  │    structural change   │                      │                      │
  │    or policy warning?  │                      │                      │
  │◄─ PENDING ─────────────┤──────────────────────────────────────────►│
  │                       │                      │            diff + checklist
  │                       │                      │            Approve / Reject
  │                       │                      │                      │
  │                       │◄──────── APPROVED ───────────────────────────┤
  │                       │                      │                      │
  │                       │  Executor.apply()    │                      │
  │                       │  graph mutation      │                      │
  │                       │  run_for_node()      │                      │
  │                       │  generated/ updated  │                      │
  │                       │  server reloads      │                      │
```

### Blast radius awareness

The engine knows exactly which generators are affected by any node change. Only those generators rerun — not all of them.

| Changed node type | Generators that re-run |
|---|---|
| `entity` | `SchemaGenerator` · `CRUDGenerator` · `UIGenerator` · `MigrationGenerator` · `DockerfileGenerator` · `ProdGenerator` (and any flows/pages that reference it) |
| `flow` | `RouteGenerator` · `UIGenerator` · `DockerfileGenerator` · `ProdGenerator` |
| `page` | `UIGenerator` |
| `integration` | `AuthGenerator` · `DeploymentGenerator` · `DockerfileGenerator` · `ProdGenerator` |
| `policy` | none (metadata only) |

---

## Build your own app

```
Read AGENTS.md, then build me an app that does [describe your app]. Tell me when you're ready.
```

That's the prompt. `AGENTS.md` tells the agent exactly what to read and in what order.
The documentation lives in the project — not in the prompt.

---

## From local to production

The full lifecycle is built in:

```bash
# Develop locally (full stack: graph + console + MCP + generated routes)
agentframe dev

# Set credentials for deployment
agentframe secrets set google_client_id
# or: open http://localhost:8000/_console/secrets

# Add a deployment target to the graph, then deploy
agentframe deploy --target gcp   # or --target aws
# → runs all generators
# → generates Alembic migration for any schema changes
# → docker build + push
# → cloud deploy
# → container startup: alembic upgrade head (schema applied, data preserved)
```

The production container (`main_prod.py`, generated) has no `/mcp` and no `/_console` — only the routes your users need.

---

## Running the test suite

```bash
.venv/bin/python -m pytest tests/ -v
# 35 passed
```

| File | What it covers |
|---|---|
| `tests/test_graph.py` | CRUD, event log, replay to point-in-time, keyword query |
| `tests/test_generators.py` | File generation, blast radius, determinism guarantee |
| `tests/test_policies.py` | PII policy, auth policy, widget limit warn vs. error |
| `tests/test_protocol.py` | Full MCP endpoint integration, auto-approve logic |

---

## Honest tradeoffs

AgentFrame is the right bet when:
- The app will evolve frequently via agent proposals
- You want structural constraints enforced on every change, not just at setup
- The approval workflow and audit trail have real value (regulated industries, teams with multiple AI sessions)
- You want the freedom to swap technology layers without touching product intent

AgentFrame is the wrong bet when:
- The app is largely bespoke logic — pricing calculations, recommendation algorithms, ML inference. The graph helps you structure the shell around that logic, but the shell is a small fraction of the code.
- The UI needs to be highly custom from the start. Generators hit a ceiling for drag-and-drop, canvas editors, or complex data visualizations. The `handler_fn` escape hatch helps, but adds friction.
- You're building a one-shot script or tool that will never meaningfully evolve.

---

## Tech stack

Python 3.11+ · FastAPI · SQLModel · SQLite / Postgres / NeonDB · Alembic · Jinja2 · HTMX · pytest · Docker (for deployment)

No React. No TypeScript. No Docker required locally.

---

## License

MIT — see [LICENSE](LICENSE).
Copyright © 2026 [Han Yuan](https://github.com/h6y3)
