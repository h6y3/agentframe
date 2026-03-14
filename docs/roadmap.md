# AgentFrame Roadmap

Items below are out of scope for the current build but are natural next steps. They follow the same extension pattern as everything else: add a node type, add a generator, add a policy.

---

## Near-term

### Staging environments
`agentframe deploy --env staging` — promote from dev to staging before production. Requires environment-tagged graph snapshots and separate DATABASE_URL per environment.

### Redis integration
```python
graph.add_node("integration", "redis_cache", "Redis Cache", attrs={
    "provider": "redis",
    "use_for": ["sessions", "rate_limiting", "job_queue"],
})
```
Generator produces `generated/middleware/cache.py` with `redis.asyncio` client. Secrets auto-declare `REDIS_URL`.

### Background jobs (Inngest / Celery)
```python
graph.add_node("workflow", "send_welcome_email", "Welcome Email", attrs={
    "trigger": {"event": "user/signup"},
    "steps": ["fetch_user", "render_email", "send"],
    "retries": 3,
    "handler_fn": "app.workflows.welcome",
})
```
`WorkflowGenerator` produces Inngest function definitions or Celery task stubs. `handler_fn` points to your implementation.

### Transactional email
```python
graph.add_node("integration", "email", "Transactional Email", attrs={
    "provider": "resend",  # or "sendgrid"
})
```
Generator produces `generated/services/email.py` wrapper. Secrets auto-declare `RESEND_API_KEY`.

---

## Medium-term

### File storage (S3 / GCS)
```python
graph.add_node("integration", "storage", "File Storage", attrs={
    "provider": "s3",  # or "gcs"
    "bucket": "my-app-uploads",
})
```
Generator produces upload/download helpers and presigned URL routes.

### Row-level security / multi-tenancy
EntityNode gets an `owner_field` attr. CRUD generator adds `WHERE owner_id = current_user.id` to all queries for that entity. Policy enforces that PII entities always have an owner_field.

### Observability
```python
graph.add_node("integration", "observability", "Error Tracking", attrs={
    "provider": "sentry",
})
```
Generator adds Sentry SDK init to `main_prod.py`. Secrets auto-declare `SENTRY_DSN`.

### Named queries / QueryNode
```python
graph.add_node("query", "recent_quotes", "Recent Quotes", attrs={
    "entity_ref": "quote",
    "filters": [{"field": "created_at", "op": "gte", "param": "since"}],
    "order_by": "created_at desc",
    "limit": 20,
})
```
`QueryGenerator` produces repository functions. PageNode widgets reference query IDs to pre-populate pages with real data.

---

## Long-term

### CLI — natural language mode
```bash
agentframe agent "add a comment system to the quotes app"
```
Wraps the MCP client in a CLI flow: agent proposes via `/mcp`, prints proposals for review, confirms approval, applies. Uses Claude API directly.

### Graph versioning / branching
Take a snapshot of the graph at any commit. Branch the graph for experimental features (like git branches). Merge branches back. Requires graph-level diff and conflict detection.

### Vercel support
Serverless functions require: Mangum ASGI adapter, Neon/Postgres (no SQLite), edge-compatible session storage. Feasible as a deployment target once the database layer is mature.

### OpenAPI / Swagger integration
Generated CRUD routes already produce OpenAPI-compatible schemas via FastAPI. Expose `generated/openapi.json` as a static artifact for integration with other tools.

### Override nodes (stretch goal from original spec)
```python
graph.add_node("override", "custom_search", "Custom Search Endpoint", attrs={
    "target_file": "generated/routes/quote_flow.py",
    "inject_after": "router = APIRouter",
    "code": "...",
})
```
GeneratorEngine applies overrides as a post-processing pass. Custom code is stored in the graph (audited, policy-checked), not floating in files that generators might overwrite.
