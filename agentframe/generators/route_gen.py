from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph


_ROUTE_FILE_TEMPLATE = '''\
# generated/routes/{flow_id}_flow.py — DO NOT EDIT
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/{flow_id}")
templates = Jinja2Templates(directory="generated/templates")

{route_functions}
'''

_START_ROUTE = '''\
@router.get("/start")
async def {flow_id}_start(request: Request):
    return templates.TemplateResponse("{flow_id}/{first_step}.html", {{"request": request}})
'''

_STEP_ROUTE = '''\
@router.post("/step/{step_name}")
async def {flow_id}_{safe_step}(request: Request):
    # TODO: validate form, advance state
    return templates.TemplateResponse("{flow_id}/{next_step}.html", {{"request": request}})
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
            steps: list[str] = flow.attrs.get("steps", [])
            if not steps:
                continue

            route_functions = []

            # GET /start → first step
            route_functions.append(
                _START_ROUTE.format(flow_id=flow.id, first_step=steps[0])
            )

            # POST /step/<step> → next step (or complete for last)
            for i, step in enumerate(steps):
                next_step = steps[i + 1] if i + 1 < len(steps) else None
                safe_step = step.replace("-", "_")
                if next_step:
                    route_functions.append(
                        _STEP_ROUTE.format(
                            flow_id=flow.id,
                            step_name=step,
                            safe_step=safe_step,
                            next_step=next_step,
                        )
                    )
                else:
                    # Last step redirects to complete
                    last_step_route = f'''\
@router.post("/step/{step}")
async def {flow.id}_{safe_step}(request: Request):
    # TODO: validate final step, persist data
    return templates.TemplateResponse("{flow.id}/complete.html", {{"request": request}})
'''
                    route_functions.append(last_step_route)

            # GET /complete
            route_functions.append(_COMPLETE_ROUTE.format(flow_id=flow.id))

            content = _ROUTE_FILE_TEMPLATE.format(
                flow_id=flow.id,
                route_functions="\n".join(route_functions),
            )
            files[f"routes/{flow.id}_flow.py"] = content

        return files
