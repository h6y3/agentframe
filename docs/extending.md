# Extending AgentFrame — New Node Types and Generators

When the built-in node types (entity, flow, page, policy, integration) aren't enough,
follow this five-step pattern. Every real-world capability — Stripe, DB queries,
background jobs, webhooks — maps to these same five steps.

---

## The pattern

### Step A — Add a node to the graph

```python
graph.add_node("webhook", "stripe_payment", "Stripe Payment Webhook", attrs={
    "integration_ref": "stripe",
    "event": "payment_intent.succeeded",
    "webhook_secret_env": "STRIPE_WEBHOOK_SECRET",
    "handler_fn": "app.handlers.payment.on_success",
})
```

Pick a `node_type` string that is meaningful and consistent. All nodes of the
same type will be processed by the same generator.

> **Note on `integration` nodes:** The built-in `AuthGenerator` and `DeploymentGenerator`
> already process `integration` nodes for known `provider` values (`google_oauth`,
> `email_magic_link`, `gcp_cloudrun`, `aws_apprunner`). If you need a new integration
> that doesn't fit those, use a distinct node type (e.g., `webhook`, `payment`, `query`)
> rather than `integration`, to avoid conflicts.

### Step B — Write a generator

Create `agentframe/generators/<name>_gen.py`:

```python
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph


class WebhookGenerator(BaseGenerator):
    def generate(self, graph: Graph) -> dict[str, str]:
        files = {}
        for node in graph.list_nodes("webhook"):
            content = _render_webhook_router(node)
            files[f"routes/{node.id}_webhook.py"] = content
        return files


def _render_webhook_router(node) -> str:
    handler = node.attrs.get("handler_fn", "")
    handler_module = ".".join(handler.split(".")[:-1])
    handler_fn = handler.split(".")[-1]
    secret_env = node.attrs.get("webhook_secret_env", "WEBHOOK_SECRET")
    return f"""\
# generated/routes/{node.id}_webhook.py — DO NOT EDIT
from fastapi import APIRouter, Request, Header, HTTPException
import hmac, hashlib, os
from {handler_module} import {handler_fn}

router = APIRouter(prefix="/webhooks/{node.id}")
_secret = os.environ.get("{secret_env}", "")

@router.post("/")
async def handle_webhook(request: Request, stripe_signature: str = Header(...)):
    payload = await request.body()
    # TODO: verify signature
    data = await request.json()
    return await {handler_fn}(data)
"""
```

**Generator rules:**
- `generate()` is a pure function — takes a Graph, returns `dict[str, str]`
- No file I/O inside `generate()` — the base class `write()` handles that
- Must be deterministic — same graph always produces identical output
- Filenames are relative to the `generated/` directory (e.g., `"routes/foo.py"`)
- To write outside `generated/` (e.g., project root), prefix with `../` (e.g., `"../alembic.ini"`)

### Step C — Register the generator

In `agentframe/generators/engine.py`, import and add to the `generators` list:

```python
from agentframe.generators.webhook_gen import WebhookGenerator

# In GeneratorEngine.__init__:
self.generators = [
    RouteGenerator(),
    SchemaGenerator(),
    UIGenerator(),
    CRUDGenerator(),
    AuthGenerator(),
    MigrationGenerator(),
    DockerfileGenerator(),
    DeploymentGenerator(),
    ProdGenerator(),
    WebhookGenerator(),   # add here
]
```

### Step D — Add blast radius triggers

In the same file, add to `_GENERATOR_TRIGGERS`:

```python
_GENERATOR_TRIGGERS: dict[str, list[str]] = {
    "RouteGenerator":       ["flow"],
    "SchemaGenerator":      ["entity"],
    "UIGenerator":          ["flow", "page", "entity"],
    "CRUDGenerator":        ["entity"],
    "AuthGenerator":        ["integration"],
    "MigrationGenerator":   ["entity"],
    "DockerfileGenerator":  ["entity", "flow", "integration"],
    "DeploymentGenerator":  ["integration"],
    "ProdGenerator":        ["entity", "flow", "integration"],
    "WebhookGenerator":     ["webhook"],   # add here
}
```

This tells the engine which generators to rerun when a node of that type changes.
Only the affected generators run — not all generators.

### Step E — Add a policy (optional but recommended)

Create `agentframe/policies/builtin/<name>.py`:

```python
from agentframe.policies.base import policy, PolicyResult
from agentframe.runtime.proposals import PatchProposal
from agentframe.graph.store import Graph


@policy("webhook_requires_handler")
def check(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    rule = "webhook_requires_handler"
    if proposal.node_type != "webhook":
        return PolicyResult.pass_(rule)
    if not proposal.attrs.get("handler_fn"):
        return PolicyResult.fail(
            rule,
            f"Webhook '{proposal.node_id}' missing required attr 'handler_fn'",
            severity="error",
        )
    return PolicyResult.pass_(rule)
```

Then register it in `agentframe/policies/engine.py`:

```python
import agentframe.policies.builtin.webhook_requires_handler  # noqa: F401
```

That's it. The `@policy` decorator registers the function automatically on import.

---

## The escape hatch — handler_fn

For business logic that generators can't produce (payment handling, email
sending, recommendation logic), use the `handler_fn` pattern:

```python
graph.add_node("webhook", "payment_success", "Payment Succeeded", attrs={
    "integration_ref": "stripe",
    "event": "payment_intent.succeeded",
    "handler_fn": "app.handlers.payment.on_success",
})
```

Your generator reads `handler_fn` and emits a call to it:

```python
# Inside the generator:
handler = node.attrs.get("handler_fn", "")
content = f"""
from {'.'.join(handler.split('.')[:-1])} import {handler.split('.')[-1]}

@router.post("/")
async def handle(request: Request):
    data = await request.json()
    return await {handler.split('.')[-1]}(data)
"""
```

You write `app/handlers/payment.py` by hand. The generator never touches `app/`.

**The hard boundary:**
- `app/` — your code, never touched by generators
- `generated/` — generator output, never hand-edited

---

## Reference implementations

Study these before writing your first generator:

| File | Pattern it demonstrates |
|---|---|
| `agentframe/generators/route_gen.py` | Iterating flow nodes, building route functions, f-string templates |
| `agentframe/generators/schema_gen.py` | Type mapping, generating `__init__.py`, class name derivation |
| `agentframe/generators/ui_gen.py` | Nested output paths, conditional field rendering, CSRF token injection |
| `agentframe/generators/crud_gen.py` | Entity → SQLModel table class + full CRUD REST router |
| `agentframe/generators/auth_gen.py` | Integration node → multiple output files, conditional generation |
| `agentframe/generators/migration_gen.py` | Writing to project root with `../` prefix, Alembic project setup |
| `agentframe/policies/builtin/no_public_pii.py` | Merging existing node attrs with proposal attrs for UPDATE ops |
| `agentframe/policies/builtin/widget_limit.py` | Warning-severity policy that doesn't block approval |

---

## Testing your generator

Add to `tests/test_generators.py`:

```python
def test_webhook_gen_produces_route(graph, tmp_path):
    graph.add_node("webhook", "payment_success", "Payment Webhook", attrs={
        "webhook_secret_env": "STRIPE_WEBHOOK_SECRET",
        "handler_fn": "app.handlers.payment.on_success",
    })
    gen = WebhookGenerator()
    files = gen.generate(graph)
    assert "routes/payment_success_webhook.py" in files
    assert "router = APIRouter" in files["routes/payment_success_webhook.py"]

def test_webhook_gen_deterministic(graph):
    graph.add_node("webhook", "payment_success", "Payment Webhook", attrs={
        "handler_fn": "app.handlers.payment.on_success",
    })
    gen = WebhookGenerator()
    assert gen.generate(graph) == gen.generate(graph)
```
