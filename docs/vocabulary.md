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

**Field `type` values:** `str` · `int` · `float` · `bool` · `datetime` · `list` · `dict`

**Generated REST API:** `GET/POST /api/<id>s/` · `GET/PUT/DELETE /api/<id>s/{id}`

**Policies that apply:**
- `no_public_pii` — fails with error if any field has `pii: True` and `requires_auth` is False
- `auth_required_on_sensitive_pages` — cascades: any page referencing a PII entity must also set `requires_auth: True`

---

## flow

A multi-step user journey. Maps to a generated FastAPI router in `generated/routes/`
and a set of HTML form templates in `generated/templates/<flow_id>/`.

```python
graph.add_node("flow", "signup", "Sign Up", attrs={
    "steps": ["email_capture", "plan_select", "confirm"],   # snake_case, URL-safe
    "entity_refs": ["user", "plan"],                        # entities this flow reads/writes
})
```

Generated routes per step:
- `GET  /<flow_id>/start` → renders first step template
- `POST /<flow_id>/step/<step_name>` → advances to next step
- `GET  /<flow_id>/complete` → success page

All form templates include a `_csrf_token` hidden field automatically.

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
