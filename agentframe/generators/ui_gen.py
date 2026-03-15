from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph
from agentframe.graph.step_schema import normalize_steps, get_step_name, get_step_type

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
        input, select, textarea { padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; }
        textarea { min-height: 100px; resize: vertical; }
        button { padding: 0.5rem 1.5rem; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
        button:hover { background: #1d4ed8; }
        .widget { border: 1px dashed #ccc; padding: 1rem; margin: 0.5rem 0; border-radius: 4px; color: #666; }
        .step-indicator { color: #666; margin-bottom: 1rem; }
        nav a { margin-right: 1rem; }
        .loading { text-align: center; padding: 2rem; }
        .loading-spinner { border: 4px solid #f3f3f3; border-top: 4px solid #2563eb; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 1rem auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .result-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }
        .error { color: #dc2626; background: #fef2f2; border: 1px solid #fecaca; padding: 1rem; border-radius: 4px; }
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

_FLOW_FORM_STEP_TEMPLATE = """\
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

_FLOW_LLM_LOADING_TEMPLATE = """\
{{% extends "base.html" %}}
{{% block content %}}
<h1>{flow_label}</h1>
<p class="step-indicator">Step {step_num} of {total_steps}: {step_label}</p>

<div class="loading" id="loading-state">
    <div class="loading-spinner"></div>
    <p>Generating response...</p>
</div>

<div id="result-container" style="display: none;">
    <div class="result-card">
        <pre id="result-content"></pre>
    </div>
    <a href="/{flow_id}/step/{step_name}/result/{{{{ session_id }}}}" class="button">Continue</a>
</div>

<div id="error-container" style="display: none;" class="error">
    <p id="error-message"></p>
    <a href="/{flow_id}/start">Try Again</a>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {{
    const sessionId = '{{{{ session_id }}}}';
    const flowId = '{flow_id}';
    const stepName = '{step_name}';

    const eventSource = new EventSource(`/${{flowId}}/step/${{stepName}}/stream/${{sessionId}}`);

    eventSource.onmessage = function(event) {{
        const data = JSON.parse(event.data);

        if (data.error) {{
            eventSource.close();
            document.getElementById('loading-state').style.display = 'none';
            document.getElementById('error-container').style.display = 'block';
            document.getElementById('error-message').textContent = data.error;
            return;
        }}

        if (data.done) {{
            eventSource.close();
            document.getElementById('loading-state').style.display = 'none';
            document.getElementById('result-container').style.display = 'block';
            document.getElementById('result-content').textContent = JSON.stringify(data.result, null, 2);
            // Auto-redirect to result page
            window.location.href = `/${{flowId}}/step/${{stepName}}/result/${{sessionId}}`;
        }}
    }};

    eventSource.onerror = function() {{
        eventSource.close();
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('error-container').style.display = 'block';
        document.getElementById('error-message').textContent = 'Connection lost. Please try again.';
    }};
}});
</script>
{{% endblock %}}
"""

_FLOW_DISPLAY_STEP_TEMPLATE = """\
{{% extends "base.html" %}}
{{% block content %}}
<h1>{flow_label}</h1>
<p class="step-indicator">Step {step_num} of {total_steps}: {step_label}</p>

<div class="result-card">
    {{% if result %}}
    <pre>{{{{ result | tojson(indent=2) }}}}</pre>
    {{% else %}}
    <p>No result available.</p>
    {{% endif %}}
</div>

<a href="/{flow_id}/complete" class="button">Finish</a>
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
    "textarea": '    <textarea name="{name}" placeholder="{label}" {required}></textarea>',
}


def _step_label(step_name: str) -> str:
    return step_name.replace("_", " ").title()


def _field_input(field: dict) -> str:
    name = field.get("name", "data")
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
            raw_steps = flow.attrs.get("steps", [])
            steps = normalize_steps(raw_steps)
            entity_refs: list[str] = flow.attrs.get("entity_refs", [])
            total_steps = len(steps)

            # Gather fields from referenced entities (for legacy support)
            all_entity_fields: list[dict] = []
            for ref in entity_refs:
                all_entity_fields.extend(entity_fields.get(ref, []))

            for i, step in enumerate(steps):
                step_name = get_step_name(step)
                step_type = get_step_type(step)

                if step_type == "form":
                    # Form step template
                    step_fields = step.get("fields", [])
                    if step_fields:
                        field_inputs = "\n".join(_field_input(f) for f in step_fields)
                    elif i == 0 and all_entity_fields:
                        # Legacy: use entity fields for first step
                        field_inputs = "\n".join(_field_input(f) for f in all_entity_fields)
                    else:
                        field_inputs = '    <input type="text" name="data" placeholder="Enter data" required>'

                    content = _FLOW_FORM_STEP_TEMPLATE.format(
                        flow_label=flow.label,
                        step_num=i + 1,
                        total_steps=total_steps,
                        step_label=_step_label(step_name),
                        flow_id=flow.id,
                        step_name=step_name,
                        field_inputs=field_inputs,
                    )
                    files[f"templates/{flow.id}/{step_name}.html"] = content

                elif step_type == "llm":
                    # LLM loading template
                    content = _FLOW_LLM_LOADING_TEMPLATE.format(
                        flow_label=flow.label,
                        step_num=i + 1,
                        total_steps=total_steps,
                        step_label=_step_label(step_name),
                        flow_id=flow.id,
                        step_name=step_name,
                    )
                    files[f"templates/{flow.id}/{step_name}_loading.html"] = content

                elif step_type == "display":
                    # Display step template
                    content = _FLOW_DISPLAY_STEP_TEMPLATE.format(
                        flow_label=flow.label,
                        step_num=i + 1,
                        total_steps=total_steps,
                        step_label=_step_label(step_name),
                        flow_id=flow.id,
                        step_name=step_name,
                    )
                    files[f"templates/{flow.id}/{step_name}.html"] = content

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
