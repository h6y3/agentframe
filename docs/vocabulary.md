# Graph Vocabulary — Node Types and Attrs

Every node is a row in the `nodes` table, discriminated by `node_type`.
The `attrs` field is freeform JSON but each type follows a conventional schema.

---

## entity

A data model. Maps to a generated Pydantic model in `generated/models/`,
a SQLModel table class in `generated/models/<id>_table.py`, and a full
CRUD REST API in `generated/routes/<id>_crud.py`.

```python
graph.add_node("entity", "user", "User", attrs={
    "fields": [
        {"name": "email", "type": "str",   "pii": True,  "required": True},
        {"name": "name",  "type": "str",   "pii": False, "required": True},
        {"name": "role",  "type": "str",   "pii": False, "required": False},
    ],
    "requires_auth": True,   # MUST be True if any field has pii: True (policy enforced)
})
```

**Field `type` values:** `str` · `int` · `float` · `bool` · `datetime` · `list` · `dict` · `object`

**Generated REST API:** `GET/POST /api/<id>s/` · `GET/PUT/DELETE /api/<id>s/{id}`

### Tool schema entities

Entities can be marked as LLM tool schemas with `is_tool_schema: True`.
These are converted to JSON schemas for structured LLM output.

```python
graph.add_node("entity", "wisdom_output", "Wisdom Output", attrs={
    "is_tool_schema": True,
    "fields": [
        {"name": "insight", "type": "str", "description": "The key insight", "required": True},
        {"name": "action", "type": "str", "description": "Suggested action", "required": True},
        {"name": "confidence", "type": "float", "description": "0.0-1.0 confidence", "required": False},
    ],
})
```

Reference in LLM steps via `tool_schema_ref`:

```python
{"name": "generate", "type": "llm", "integration_ref": "anthropic_llm", "tool_schema_ref": "wisdom_output"}
```

This ensures the LLM returns structured JSON matching the entity schema.

**Policies that apply:**
- `no_public_pii` — fails with error if any field has `pii: True` and `requires_auth` is False
- `auth_required_on_sensitive_pages` — cascades: any page referencing a PII entity must also set `requires_auth: True`

---

## flow

A multi-step user journey. Maps to a generated FastAPI router in `generated/routes/`
and a set of HTML form templates in `generated/templates/<flow_id>/`.

### Legacy format (string steps)

```python
graph.add_node("flow", "signup", "Sign Up", attrs={
    "steps": ["email_capture", "plan_select", "confirm"],   # snake_case, URL-safe
    "entity_refs": ["user", "plan"],                        # entities this flow reads/writes
})
```

### Modern format (dict steps with types)

The modern format supports three step types: `form`, `llm`, and `display`.

```python
graph.add_node("flow", "reflect", "Reflect & Shift", attrs={
    "steps": [
        # Form step: collects user input
        {"name": "describe", "type": "form", "fields": [
            {"name": "situation", "type": "textarea", "required": True}
        ]},
        # LLM step: calls an LLM and streams the response
        {"name": "generate", "type": "llm",
         "integration_ref": "anthropic_llm",      # references an LLM integration
         "system_prompt": "You are a helpful assistant...",
         # OR use prompt_ref to load from resources/prompts/{ref}.md
         # "prompt_ref": "wise_counselor",
         "tool_schema_ref": "wisdom_output",      # optional: references an entity with is_tool_schema
         "max_tokens": 4096},
        # Display step: shows the LLM result
        {"name": "result", "type": "display"},
    ],
    "entity_refs": ["wisdom"],
})
```

### Step types

| Type | Required attrs | Optional attrs | Description |
|------|---------------|----------------|-------------|
| `form` | `name` | `fields`, `validator_fn` | User input form |
| `llm` | `name`, `integration_ref` | `system_prompt`, `prompt_ref`, `tool_schema`, `tool_schema_ref`, `max_tokens` | LLM call with streaming |
| `display` | `name` | `template_ref` | Show results |

### Form field types

| Type | HTML input |
|------|------------|
| `str` | `<input type="text">` |
| `email` | `<input type="email">` |
| `int` | `<input type="number">` |
| `float` | `<input type="number" step="0.01">` |
| `bool` | `<input type="checkbox">` |
| `textarea` | `<textarea>` |

### Generated routes

- `GET  /<flow_id>/start` → renders first step template
- `POST /<flow_id>/step/<step_name>` → advances to next step
- `GET  /<flow_id>/step/<step_name>/stream/{session_id}` → SSE stream for LLM steps
- `GET  /<flow_id>/step/<step_name>/result/{session_id}` → result page after LLM
- `GET  /<flow_id>/complete` → success page

All form templates include a `_csrf_token` hidden field automatically.

### Policies that apply

- `flow_steps_valid` — validates step schema (required fields, valid types)
- `llm_integration_ref_exists` — ensures LLM steps reference existing integrations
- `flow_steps_modern_format` — warns if using legacy string format (not an error)

---

## page

A rendered view. Maps to a generated Jinja2 template in `generated/templates/`.

```python
graph.add_node("page", "dashboard", "Dashboard", attrs={
    "widgets": ["activity_feed", "usage_chart", "quick_actions"],  # max 8 (policy enforced)
    "requires_auth": True,
    "entity_refs": ["user"],
})
```

**Policies that apply:**
- `widget_limit` — warns (not blocks) if more than 8 widgets
- `auth_required_on_sensitive_pages` — fails with error if page refs a PII entity without `requires_auth: True`

---

## policy

Constraint metadata stored in the graph. The actual enforcement logic lives in Python.
This node type is informational — it documents which policies are active.

```python
graph.add_node("policy", "no_public_pii", "No Public PII", attrs={
    "rule_fn": "agentframe.policies.builtin.no_public_pii.check",
    "severity": "error",   # "error" blocks approval | "warn" flags but allows
})
```

---

## integration

A third-party integration. Processed by AuthGenerator (auth providers) and
DeploymentGenerator (deployment targets).

### Auth providers

```python
# Google OAuth
graph.add_node("integration", "google_auth", "Google Login", attrs={
    "provider": "google_oauth",
    "scopes": ["openid", "email", "profile"],
})

# Email magic link
graph.add_node("integration", "email_auth", "Email Magic Link", attrs={
    "provider": "email_magic_link",
    "from_email": "noreply@myapp.com",
})
```

**Auth providers generate:**
- `generated/middleware/google_auth.py` or `generated/middleware/email_auth.py`
- `generated/middleware/csrf.py` (always generated when any auth node exists)
- Auto-declare secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY` (Google) or `RESEND_API_KEY`, `SECRET_KEY` (magic link)

### Deployment targets

```python
# GCP Cloud Run
graph.add_node("integration", "deploy_gcp", "Deploy: GCP Cloud Run", attrs={
    "provider": "gcp_cloudrun",
    "project_id": "my-gcp-project",
    "region": "us-central1",
})

# AWS App Runner
graph.add_node("integration", "deploy_aws", "Deploy: AWS App Runner", attrs={
    "provider": "aws_apprunner",
    "region": "us-east-1",
})
```

**Deployment targets generate:**
- `deploy/gcp/service.yaml` + `deploy/deploy_gcp.sh` (GCP)
- `deploy/aws/apprunner.yaml` + `deploy/deploy_aws.sh` (AWS)

See `docs/deploy-gcp-cloudrun.md` for full GCP Cloud Run setup guide.

### LLM providers (with code generation)

For LLM integrations that generate client code, use `provider_type: "llm"`.
This triggers the `LLMGenerator` to create `generated/services/llm_client.py`
and provider-specific adapters.

```python
# Anthropic Claude (generates client code)
graph.add_node("integration", "anthropic_llm", "Anthropic LLM", attrs={
    "provider_type": "llm",                  # triggers LLMGenerator
    "provider": "anthropic",
    "default_model": "claude-haiku-4-5-20251001",
    "env_var": "ANTHROPIC_API_KEY",
})

# OpenAI (generates client code)
graph.add_node("integration", "openai_llm", "OpenAI LLM", attrs={
    "provider_type": "llm",
    "provider": "openai",
    "default_model": "gpt-4o",
    "env_var": "OPENAI_API_KEY",
})
```

**LLM integrations generate:**
- `generated/services/llm_client.py` — provider-agnostic interface
- `generated/services/anthropic_adapter.py` — Anthropic-specific code
- `generated/services/openai_adapter.py` — OpenAI-specific code

**Using in flow steps:**

Reference the integration in an LLM step:

```python
{"name": "generate", "type": "llm", "integration_ref": "anthropic_llm", ...}
```

**Policies that apply:**
- `llm_integration_valid` — validates required attrs (provider, env_var)

### LLM / API providers (config only)

For apps that call external APIs manually (custom code in `app/`), use an integration
node without `provider_type: "llm"` to store configuration only.

```python
# Anthropic Claude (config only, no code generation)
graph.add_node("integration", "anthropic", "Anthropic API", attrs={
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "env_var": "ANTHROPIC_API_KEY",
    "purpose": "wisdom_generation",
})
```

**Reading config in your code (`app/wisdom.py`):**

```python
from agentframe.graph.store import Graph

def _get_llm_config() -> tuple[str, str]:
    """Read LLM config from the graph integration node."""
    graph = Graph()
    node = graph.get_node("anthropic")
    if node is None:
        return "ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001"
    return node.attrs.get("env_var", "ANTHROPIC_API_KEY"), node.attrs.get("model")
```

**Why use the graph for this?**
- Single source of truth for model configuration
- Agents can update models via MCP without editing code
- Easy to switch providers (change node attrs, not code)
- Production config visible in `/_console/graph`

---

## Secrets

Secrets are not graph nodes — they live in the `secret_nodes` table managed by `EncryptedVault`.
Generators auto-declare secrets via `vault.declare()` at startup.

```python
# Declared automatically by AuthGenerator; manage via:
# agentframe secrets list
# agentframe secrets set google_client_id
# /_console/secrets
```

**Vault behavior:**
- Encrypted at rest with Fernet (AGENTFRAME_SECRET_KEY env var)
- Values never logged or returned in API responses
- `vault.get_env_dict()` decrypts all at deploy time for injection as env vars

---

## Extending the vocabulary

When you need OAuth, Stripe, background jobs, named queries, etc., add a new
node type. See `docs/extending.md` for the step-by-step pattern.

Common extensions:

| Use case | Suggested node_type | Key attrs |
|---|---|---|
| Stripe / payment | `integration` | `provider: "stripe"`, `events: [...]` |
| Incoming webhook | `webhook` | `integration_ref`, `event`, `handler_fn` |
| Named DB query | `query` | `entity_ref`, `filters`, `order_by`, `limit` |
| Background job | `workflow` | `trigger` (`event` or `cron`), `steps`, `retries` |
| File storage | `integration` | `provider: "s3"` or `"gcs"`, `bucket` |

The `handler_fn` attr is the escape hatch for custom business logic — it points to
a Python function you write in `app/`. The generator emits the plumbing (route,
signature verification, retry wrapper). You write the logic. This is the hard
boundary between generated and hand-written code.
