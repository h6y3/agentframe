from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph
from agentframe.graph.step_schema import normalize_steps, get_step_name, get_step_type


_ROUTE_FILE_TEMPLATE = '''\
# generated/routes/{flow_id}_flow.py — DO NOT EDIT
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import json
import uuid

router = APIRouter(prefix="/{flow_id}")
templates = Jinja2Templates(directory="generated/templates")

# In-memory session storage for flow state
_flow_sessions: dict[str, dict] = {{}}

{route_functions}
'''

_START_ROUTE = '''\
@router.get("/start")
async def {flow_id}_start(request: Request):
    return templates.TemplateResponse("{flow_id}/{first_step}.html", {{"request": request}})
'''

_FORM_STEP_ROUTE = '''\
@router.post("/step/{step_name}")
async def {flow_id}_{safe_step}(request: Request):
    form = await request.form()
    session_id = str(uuid.uuid4())
    _flow_sessions[session_id] = dict(form)
    return templates.TemplateResponse("{flow_id}/{next_step}.html", {{
        "request": request,
        "session_id": session_id,
        **dict(form),
    }})
'''

_LLM_STEP_ROUTE = '''\
@router.post("/step/{step_name}")
async def {flow_id}_{safe_step}(request: Request):
    """Start LLM generation - returns loading page with SSE connection."""
    form = await request.form()
    session_id = str(uuid.uuid4())
    _flow_sessions[session_id] = {{
        "input": dict(form),
        "status": "pending",
        "result": None,
    }}
    return templates.TemplateResponse("{flow_id}/{step_name}_loading.html", {{
        "request": request,
        "session_id": session_id,
        "flow_id": "{flow_id}",
        "step_name": "{step_name}",
    }})


@router.get("/step/{step_name}/stream/{{session_id}}")
async def {flow_id}_{safe_step}_stream(session_id: str):
    """SSE endpoint for streaming LLM response."""
    from services.llm_client import call_llm, LLMConfig

    session = _flow_sessions.get(session_id)
    if not session:
        async def error_stream():
            yield f"data: {{json.dumps({{'error': 'Session not found'}})}}\\n\\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def generate():
        try:
            # Build the LLM config from integration
            config = LLMConfig(
                provider="{provider}",
                model="{model}",
                system_prompt="""{system_prompt}""",
                tool_schema={tool_schema},
                max_tokens={max_tokens},
            )

            # Get user input from session
            user_input = session["input"].get("{input_field}", "")

            # Call LLM
            response = await call_llm(config, user_input)

            # Store result in session
            session["status"] = "complete"
            session["result"] = response.content

            yield f"data: {{json.dumps({{'done': True, 'result': response.content}})}}\\n\\n"

        except Exception as e:
            session["status"] = "error"
            yield f"data: {{json.dumps({{'error': str(e)}})}}\\n\\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/step/{step_name}/result/{{session_id}}")
async def {flow_id}_{safe_step}_result(request: Request, session_id: str):
    """Get the result page after LLM generation completes."""
    session = _flow_sessions.get(session_id)
    if not session or session.get("status") != "complete":
        return templates.TemplateResponse("{flow_id}/{step_name}_loading.html", {{
            "request": request,
            "session_id": session_id,
            "flow_id": "{flow_id}",
            "step_name": "{step_name}",
            "error": "Session not ready or not found",
        }})

    return templates.TemplateResponse("{flow_id}/{next_step}.html", {{
        "request": request,
        "session_id": session_id,
        "result": session["result"],
        **session["input"],
    }})
'''

_DISPLAY_STEP_ROUTE = '''\
@router.get("/step/{step_name}/{{session_id}}")
async def {flow_id}_{safe_step}(request: Request, session_id: str):
    session = _flow_sessions.get(session_id, {{}})
    return templates.TemplateResponse("{flow_id}/{step_name}.html", {{
        "request": request,
        "session_id": session_id,
        "result": session.get("result"),
        **session.get("input", {{}}),
    }})
'''

_LAST_STEP_ROUTE = '''\
@router.post("/step/{step_name}")
async def {flow_id}_{safe_step}(request: Request):
    # TODO: validate final step, persist data
    return templates.TemplateResponse("{flow_id}/complete.html", {{"request": request}})
'''

_COMPLETE_ROUTE = '''\
@router.get("/complete")
async def {flow_id}_complete(request: Request):
    return templates.TemplateResponse("{flow_id}/complete.html", {{"request": request}})
'''


class RouteGenerator(BaseGenerator):
    output_dir = Path("routes")

    def generate(self, graph: Graph) -> dict[str, str]:
        flows = graph.list_nodes("flow")
        files: dict[str, str] = {}

        for flow in sorted(flows, key=lambda n: n.id):
            raw_steps = flow.attrs.get("steps", [])
            if not raw_steps:
                continue

            steps = normalize_steps(raw_steps)
            route_functions = []

            # GET /start → first step
            first_step_name = get_step_name(steps[0])
            route_functions.append(
                _START_ROUTE.format(flow_id=flow.id, first_step=first_step_name)
            )

            # Generate routes for each step
            for i, step in enumerate(steps):
                step_name = get_step_name(step)
                step_type = get_step_type(step)
                safe_step = step_name.replace("-", "_")
                next_step = get_step_name(steps[i + 1]) if i + 1 < len(steps) else None

                if step_type == "llm":
                    # LLM step: generate POST + SSE stream + result routes
                    route_fn = self._generate_llm_step_route(
                        flow, step, safe_step, next_step, graph
                    )
                    route_functions.append(route_fn)

                elif step_type == "display":
                    # Display step: GET route that shows results
                    route_functions.append(
                        _DISPLAY_STEP_ROUTE.format(
                            flow_id=flow.id,
                            step_name=step_name,
                            safe_step=safe_step,
                        )
                    )

                elif next_step:
                    # Form step with next step
                    route_functions.append(
                        _FORM_STEP_ROUTE.format(
                            flow_id=flow.id,
                            step_name=step_name,
                            safe_step=safe_step,
                            next_step=next_step,
                        )
                    )
                else:
                    # Last form step
                    route_functions.append(
                        _LAST_STEP_ROUTE.format(
                            flow_id=flow.id,
                            step_name=step_name,
                            safe_step=safe_step,
                        )
                    )

            # GET /complete
            route_functions.append(_COMPLETE_ROUTE.format(flow_id=flow.id))

            content = _ROUTE_FILE_TEMPLATE.format(
                flow_id=flow.id,
                route_functions="\n".join(route_functions),
            )
            files[f"routes/{flow.id}_flow.py"] = content

        return files

    def _generate_llm_step_route(
        self, flow, step: dict, safe_step: str, next_step: str | None, graph: Graph
    ) -> str:
        """Generate routes for an LLM step."""
        step_name = get_step_name(step)
        integration_ref = step.get("integration_ref", "")

        # Get integration config
        integration = graph.get_node(integration_ref) if integration_ref else None
        provider = "anthropic"
        model = "claude-3-haiku-20240307"
        if integration:
            provider = integration.attrs.get("provider", provider)
            model = integration.attrs.get("default_model", model)

        # Get prompt
        system_prompt = step.get("system_prompt", "You are a helpful assistant.")
        if "prompt_ref" in step:
            # Try to load from resources/prompts/{prompt_ref}.md
            prompt_ref = step["prompt_ref"]
            prompt_path = Path(f"resources/prompts/{prompt_ref}.md")
            if prompt_path.exists():
                system_prompt = prompt_path.read_text()

        # Get tool schema
        tool_schema = step.get("tool_schema")
        tool_schema_ref = step.get("tool_schema_ref")
        if tool_schema_ref and not tool_schema:
            # Look up entity node with is_tool_schema
            entity = graph.get_node(tool_schema_ref)
            if entity and entity.attrs.get("is_tool_schema"):
                tool_schema = self._entity_to_tool_schema(entity)

        # Determine input field (first field from previous form step)
        input_field = "input"
        # Find previous step to get its form fields
        steps = normalize_steps(flow.attrs.get("steps", []))
        for i, s in enumerate(steps):
            if get_step_name(s) == step_name and i > 0:
                prev_step = steps[i - 1]
                if get_step_type(prev_step) == "form":
                    fields = prev_step.get("fields", [])
                    if fields:
                        input_field = fields[0].get("name", "input")
                break

        max_tokens = step.get("max_tokens", 4096)

        # Escape the system prompt for Python string
        system_prompt_escaped = system_prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        return _LLM_STEP_ROUTE.format(
            flow_id=flow.id,
            step_name=step_name,
            safe_step=safe_step,
            next_step=next_step or "complete",
            provider=provider,
            model=model,
            system_prompt=system_prompt_escaped,
            tool_schema=repr(tool_schema) if tool_schema else "None",
            max_tokens=max_tokens,
            input_field=input_field,
        )

    def _entity_to_tool_schema(self, entity) -> dict:
        """Convert an entity node with is_tool_schema to a JSON schema."""
        fields = entity.attrs.get("fields", [])
        properties = {}
        required = []

        for field in fields:
            name = field.get("name", "")
            ftype = field.get("type", "str")

            # Map field types to JSON schema types
            type_map = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "object": "object",
            }

            prop = {"type": type_map.get(ftype, "string")}
            if "description" in field:
                prop["description"] = field["description"]

            # Handle nested object fields
            if ftype == "object" and "fields" in field:
                nested_schema = self._entity_to_tool_schema(
                    type("MockEntity", (), {"attrs": {"fields": field["fields"]}})()
                )
                prop["properties"] = nested_schema.get("properties", {})
                prop["required"] = nested_schema.get("required", [])

            properties[name] = prop
            if field.get("required", False):
                required.append(name)

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema
