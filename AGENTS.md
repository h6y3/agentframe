# AgentFrame — Agent Orientation

You are working in an AgentFrame project. Read this file first, then the files
listed below in order. When you have read them all, you are ready to build.

## What this is

The **product graph** — not source files — is the source of truth. You propose
mutations to the graph through the MCP protocol. Generators compile the graph
into a running FastAPI app. You never edit `generated/` directly.

The loop is: **propose → validate → approve → regenerate → live.**

## Read these files in order

### 1. Understand the graph (the data model you work with)
- `agentframe/graph/models.py` — Node and GraphEvent table definitions
- `agentframe/graph/store.py` — Graph.add_node / update_node / remove_node / query
- `docs/vocabulary.md` — every node type and its attrs schema

### 2. Understand how proposals flow
- `agentframe/runtime/proposals.py` — PatchProposal model, ProposalStatus enum
- `agentframe/protocol/server.py` — all /mcp endpoints and auto-approve logic
- `agentframe/runtime/executor.py` — how approved proposals become graph mutations

### 3. Understand how generators work
- `agentframe/generators/base.py` — BaseGenerator ABC (pure function contract)
- `agentframe/generators/engine.py` — blast radius, run_all, run_for_node
- `agentframe/generators/route_gen.py` — example: flow → FastAPI router
- `agentframe/generators/schema_gen.py` — example: entity → Pydantic model
- `agentframe/generators/crud_gen.py` — entity → SQLModel table + CRUD REST API
- `agentframe/generators/auth_gen.py` — integration → auth routes + CSRF middleware
- `agentframe/generators/prod_gen.py` — generates main_prod.py (no MCP/console)

### 4. Understand policies
- `agentframe/policies/base.py` — @policy decorator, PolicyResult, registry
- `agentframe/policies/engine.py` — PolicyEngine.validate() and is_approved()
- `agentframe/policies/builtin/no_public_pii.py` — example error policy
- `agentframe/policies/builtin/widget_limit.py` — example warning policy

### 5. Understand secrets and deployment
- `agentframe/secrets/vault.py` — EncryptedVault: declare/set/get/list
- `agentframe/database/connection.py` — get_engine() + get_app_engine()
- `agentframe/database/migrations.py` — run_pending_migrations() + generate_migration()
- `agentframe/deployment/cli.py` — `agentframe` CLI: dev / build / migrate / deploy / secrets

### 6. See a complete working example
- `demo_app/graph_seed.py` — seeds a starter SaaS app; study the node patterns
- `demo_app/main.py` — how everything mounts into a FastAPI app
- `demo_app/demo_agent.py` — a working agent script using the /mcp protocol

## Now build the app

1. Replace `demo_app/graph_seed.py` with your domain's entities, flows, and pages
2. Run `python demo_app/graph_seed.py` to seed the graph
3. Start the server: `agentframe dev` (or `.venv/bin/uvicorn demo_app.main:app --reload`)
4. Verify routes exist: `curl http://localhost:8000/<flow_id>/start`
5. Check CRUD APIs: `curl http://localhost:8000/api/<entity_id>s/`
6. Set required secrets: `/_console/secrets` or `agentframe secrets set <id>`
7. To deploy: add integration nodes for `gcp_cloudrun` or `aws_apprunner`, then `agentframe deploy --target gcp`
8. If you need custom generators or policies, read `docs/extending.md`

## Iteration workflow

```
1. LOCAL DEVELOP
   Agent proposes via /mcp → approve in /_console/proposals → generators run → server reloads → test

2. FIRST DEPLOY
   agentframe deploy --target gcp
   → runs all generators (build step)
   → alembic revision --autogenerate (generate initial migration)
   → docker build + push to registry
   → deploy service (Cloud Run / App Runner)
   → on container startup: alembic upgrade head
   → app is live

3. ITERATE LOCALLY
   Agent proposes adding a field to User → approve → CRUDGenerator updates table class
   → MigrationGenerator updates alembic/env.py → test locally

4. REDEPLOY
   agentframe deploy --target gcp (same command as Step 2)
   → detects schema diff → generates new migration
   → builds new image
   → deploys
   → on startup: alembic upgrade head (runs pending migration against live DB)
   → new field is live, old data preserved
```

## Node type quick reference

| node_type | Key attrs | What it generates |
|---|---|---|
| `entity` | `fields`, `requires_auth` | Pydantic DTO + SQLModel table + CRUD REST API |
| `flow` | `steps`, `entity_refs` | FastAPI router + Jinja2 step templates |
| `page` | `widgets`, `requires_auth`, `entity_refs` | Jinja2 page template |
| `policy` | `rule_fn`, `severity` | Metadata only (enforcement is in Python) |
| `integration` (auth) | `provider: "google_oauth"` or `"email_magic_link"` | Auth routes + CSRF middleware |
| `integration` (deploy) | `provider: "gcp_cloudrun"` or `"aws_apprunner"` | Deploy scripts + service config |

## Rules

- Never edit anything in `generated/` — it is overwritten on every regeneration
- Agents interact with the graph only through `/mcp` endpoints
- `Generator.generate()` must be a pure function — no file I/O, no DB access
- Policy functions must be stateless — no DB writes, no side effects
- `pyproject.toml` must use `build-backend = "setuptools.build_meta"`
- New generated routes only go live after server restart (`--reload` handles this)
- `main_prod.py` is generated — never edit by hand
- Secrets are encrypted at rest; never log or display decrypted values
