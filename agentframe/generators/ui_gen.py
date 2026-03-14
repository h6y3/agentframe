from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph

_BASE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentFrame App</title>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
        form { display: flex; flex-direction: column; gap: 1rem; max-width: 400px; }
        input, select { padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; }
        button { padding: 0.5rem 1.5rem; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
        button:hover { background: #1d4ed8; }
        .widget { border: 1px dashed #ccc; padding: 1rem; margin: 0.5rem 0; border-radius: 4px; color: #666; }
        .step-indicator { color: #666; margin-bottom: 1rem; }
        nav a { margin-right: 1rem; }
    </style>
</head>
<body>
    <nav>
        <a href="/">Home</a>
        <a href="/_console">Console</a>
    </nav>
    {% block content %}{% endblock %}
</body>
</html>
"""

_FLOW_STEP_TEMPLATE = """\
{{% extends "base.html" %}}
{{% block content %}}
<h1>{flow_label}</h1>
<p class="step-indicator">Step {step_num} of {total_steps}: {step_label}</p>
<form method="POST" action="/{flow_id}/step/{step_name}">
    <input type="hidden" name="_csrf_token" value="{{{{ request.cookies.get('csrf_token', '') }}}}">
{field_inputs}
    <button type="submit">Continue</button>
</form>
{{% endblock %}}
"""

_FLOW_COMPLETE_TEMPLATE = """\
{{% extends "base.html" %}}
{{% block content %}}
<h1>{flow_label}</h1>
<p>You have successfully completed the {flow_label} flow.</p>
<a href="/">Return Home</a>
{{% endblock %}}
"""

_PAGE_TEMPLATE = """\
{{% extends "base.html" %}}
{{% block content %}}
<h1>{page_label}</h1>
{widget_divs}
{{% endblock %}}
"""

_FIELD_INPUT_TEMPLATES = {
    "str": '    <input type="text" name="{name}" placeholder="{label}" {required}>',
    "email": '    <input type="email" name="{name}" placeholder="{label}" {required}>',
    "float": '    <input type="number" step="0.01" name="{name}" placeholder="{label}" {required}>',
    "int": '    <input type="number" name="{name}" placeholder="{label}" {required}>',
    "bool": '    <input type="checkbox" name="{name}" id="{name}"><label for="{name}">{label}</label>',
}


def _step_label(step_name: str) -> str:
    return step_name.replace("_", " ").title()


def _field_input(field: dict) -> str:
    name = field["name"]
    ftype = field.get("type", "str")
    # Use email input for fields named "email"
    if name == "email":
        ftype = "email"
    required = "required" if field.get("required", False) else ""
    template = _FIELD_INPUT_TEMPLATES.get(ftype, _FIELD_INPUT_TEMPLATES["str"])
    return template.format(name=name, label=name.replace("_", " ").title(), required=required)


class UIGenerator(BaseGenerator):
    output_dir = Path("templates")

    def generate(self, graph: Graph) -> dict[str, str]:
        files: dict[str, str] = {}

        # Always write base.html
        files["templates/base.html"] = _BASE_TEMPLATE

        # Build a map of entity_id -> fields for field input generation
        entity_fields: dict[str, list[dict]] = {}
        for entity in graph.list_nodes("entity"):
            entity_fields[entity.id] = entity.attrs.get("fields", [])

        # Generate flow templates
        for flow in sorted(graph.list_nodes("flow"), key=lambda n: n.id):
            steps: list[str] = flow.attrs.get("steps", [])
            entity_refs: list[str] = flow.attrs.get("entity_refs", [])
            total_steps = len(steps)

            # Gather fields from referenced entities
            all_fields: list[dict] = []
            for ref in entity_refs:
                all_fields.extend(entity_fields.get(ref, []))

            for i, step in enumerate(steps):
                # Use entity fields for first step; no fields for subsequent steps (simplified)
                if i == 0:
                    field_inputs = "\n".join(
                        _field_input(f) for f in all_fields
                    ) or '    <input type="text" name="data" placeholder="Enter data" required>'
                else:
                    field_inputs = '    <input type="text" name="data" placeholder="Enter data">'

                content = _FLOW_STEP_TEMPLATE.format(
                    flow_label=flow.label,
                    step_num=i + 1,
                    total_steps=total_steps,
                    step_label=_step_label(step),
                    flow_id=flow.id,
                    step_name=step,
                    field_inputs=field_inputs,
                )
                files[f"templates/{flow.id}/{step}.html"] = content

            # Complete page
            files[f"templates/{flow.id}/complete.html"] = _FLOW_COMPLETE_TEMPLATE.format(
                flow_label=flow.label
            )

        # Generate page templates
        for page in sorted(graph.list_nodes("page"), key=lambda n: n.id):
            widgets: list[str] = page.attrs.get("widgets", [])
            widget_divs = "\n".join(
                f'<div class="widget">[Widget: {w.replace("_", " ").title()}]</div>'
                for w in widgets
            )
            content = _PAGE_TEMPLATE.format(
                page_label=page.label,
                widget_divs=widget_divs,
            )
            files[f"templates/{page.id}.html"] = content

        return files
