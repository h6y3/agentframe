import json
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from agentframe.graph.store import Graph
from agentframe.runtime.proposals import PatchProposal, ProposalStatus
from agentframe.runtime.executor import Executor
from agentframe.generators.engine import GeneratorEngine

router = APIRouter(prefix="/_console", tags=["console"])

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Set at startup by main.py
_graph: Optional[Graph] = None
_executor: Optional[Executor] = None
_generator_engine: Optional[GeneratorEngine] = None
_vault = None  # EncryptedVault, set at startup if available


def set_dependencies(graph: Graph, executor: Executor, generator_engine: GeneratorEngine, vault=None) -> None:
    global _graph, _executor, _generator_engine, _vault
    _graph = graph
    _executor = executor
    _generator_engine = generator_engine
    _vault = vault


def _get_graph() -> Graph:
    if _graph is None:
        raise RuntimeError("Graph not initialized")
    return _graph


def _get_executor() -> Executor:
    if _executor is None:
        raise RuntimeError("Executor not initialized")
    return _executor


# ---- Graph Explorer ----

@router.get("/", response_class=HTMLResponse)
async def graph_explorer(request: Request):
    graph = _get_graph()
    all_nodes = graph.list_nodes()

    type_order = ["entity", "flow", "page", "policy", "integration"]
    grouped: dict[str, list] = {}
    for t in type_order:
        nodes = [n for n in all_nodes if n.node_type == t]
        if nodes:
            grouped[t] = sorted(nodes, key=lambda n: n.label)

    # Catch any other types
    known = set(type_order)
    for node in all_nodes:
        if node.node_type not in known:
            grouped.setdefault(node.node_type, []).append(node)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "grouped_nodes": grouped,
            "total_nodes": len(all_nodes),
            "active_page": "explorer",
        },
    )


@router.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail_partial(request: Request, node_id: str):
    graph = _get_graph()
    node = graph.get_node(node_id)
    if node is None:
        return HTMLResponse("<div class='card'><p>Node not found.</p></div>", status_code=404)

    attrs_json = json.dumps(node.attrs, indent=2)

    # Compute affected generated files
    affected_files: list[str] = []
    if _generator_engine:
        gen_names = _generator_engine._compute_blast_radius(node_id)
        gen_map = {
            "RouteGenerator": [f"generated/routes/{node_id}_flow.py"],
            "SchemaGenerator": [f"generated/models/{node_id}.py"],
            "CRUDGenerator": [f"generated/models/{node_id}_table.py", f"generated/routes/{node_id}_crud.py"],
            "UIGenerator": [],
        }
        # Add UI files
        if node.node_type == "flow":
            steps = node.attrs.get("steps", [])
            for step in steps:
                gen_map["UIGenerator"].append(f"generated/templates/{node_id}/{step}.html")
            gen_map["UIGenerator"].append(f"generated/templates/{node_id}/complete.html")
        elif node.node_type == "page":
            gen_map["UIGenerator"].append(f"generated/templates/{node_id}.html")

        for gen_name in gen_names:
            affected_files.extend(gen_map.get(gen_name, []))

    return templates.TemplateResponse(
        "node_detail.html",
        {
            "request": request,
            "node": node,
            "attrs_json": attrs_json,
            "affected_files": affected_files,
        },
    )


# ---- Proposals ----

@router.get("/proposals", response_class=HTMLResponse)
async def proposals_list(request: Request, status: Optional[str] = None):
    graph = _get_graph()
    with Session(graph.engine) as session:
        stmt = select(PatchProposal).order_by(PatchProposal.created_at.desc())
        all_proposals = list(session.exec(stmt).all())

    if status:
        all_proposals = [p for p in all_proposals if p.status == status]

    return templates.TemplateResponse(
        "proposals.html",
        {
            "request": request,
            "proposals": all_proposals,
            "status_filter": status,
            "active_page": "proposals",
        },
    )


@router.get("/proposals/{proposal_id}", response_class=HTMLResponse)
async def proposal_detail(request: Request, proposal_id: str, message: Optional[str] = None):
    graph = _get_graph()
    with Session(graph.engine) as session:
        proposal = session.get(PatchProposal, proposal_id)
        if proposal is None:
            return HTMLResponse("<h2>Proposal not found</h2>", status_code=404)
        p_data = {
            "id": proposal.id,
            "op": proposal.op,
            "node_type": proposal.node_type,
            "node_id": proposal.node_id,
            "attrs": proposal.attrs,
            "label": proposal.label,
            "status": proposal.status,
            "policy_results": proposal.policy_results,
            "created_at": proposal.created_at,
            "resolved_at": proposal.resolved_at,
            "resolved_by": proposal.resolved_by,
        }

    # Build diff preview
    existing = graph.get_node(p_data["node_id"])
    diff_lines = [f"--- {p_data['op'].upper()} {p_data['node_type']} '{p_data['node_id']}' ---"]

    if p_data["op"] == "add":
        diff_lines.append("+ New node:")
        if p_data["label"]:
            diff_lines.append(f"  label: {p_data['label']}")
        for k, v in p_data["attrs"].items():
            diff_lines.append(f"  + {k}: {json.dumps(v)}")
    elif p_data["op"] == "update" and existing:
        diff_lines.append("~ Changes:")
        if p_data["label"] and p_data["label"] != existing.label:
            diff_lines.append(f"  label: '{existing.label}' → '{p_data['label']}'")
        for k, v in p_data["attrs"].items():
            old_v = existing.attrs.get(k, "<not set>")
            if old_v != v:
                diff_lines.append(f"  {k}:")
                diff_lines.append(f"    - {json.dumps(old_v)}")
                diff_lines.append(f"    + {json.dumps(v)}")
    elif p_data["op"] == "remove" and existing:
        diff_lines.append(f"- Remove: {p_data['node_id']} ({existing.label})")
        for k, v in existing.attrs.items():
            diff_lines.append(f"  - {k}: {json.dumps(v)}")

    diff_preview = "\n".join(diff_lines)
    policy_results = p_data["policy_results"] or []

    class ProposalView:
        pass

    pv = ProposalView()
    for k, v in p_data.items():
        setattr(pv, k, v)

    return templates.TemplateResponse(
        "proposal_detail.html",
        {
            "request": request,
            "proposal": pv,
            "diff_preview": diff_preview,
            "policy_results": policy_results,
            "message": message,
            "active_page": "proposals",
        },
    )


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    executor = _get_executor()
    success = executor.approve(proposal_id)
    if success:
        return RedirectResponse(
            f"/_console/proposals/{proposal_id}?message=Proposal+approved+and+applied",
            status_code=303,
        )
    return RedirectResponse(f"/_console/proposals/{proposal_id}", status_code=303)


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    executor = _get_executor()
    executor.reject(proposal_id)
    return RedirectResponse(f"/_console/proposals/{proposal_id}", status_code=303)


# ---- Secrets ----

@router.get("/secrets", response_class=HTMLResponse)
async def secrets_list(request: Request, message: Optional[str] = None):
    secrets = _vault.list_all() if _vault else []
    return templates.TemplateResponse(
        "secrets.html",
        {"request": request, "secrets": secrets, "message": message, "active_page": "secrets"},
    )


@router.post("/secrets")
async def declare_secret(
    id: str = Form(...),
    env_var: str = Form(...),
    description: str = Form(""),
):
    if _vault:
        _vault.declare(id=id, env_var=env_var, description=description)
    return RedirectResponse(
        f"/_console/secrets?message=Secret+%27{id}%27+declared",
        status_code=303,
    )


@router.post("/secrets/{secret_id}/value")
async def set_secret_value(secret_id: str, value: str = Form(...)):
    if _vault:
        try:
            _vault.set_value(secret_id, value)
        except KeyError:
            _vault.declare(id=secret_id, env_var=secret_id.upper())
            _vault.set_value(secret_id, value)
    return RedirectResponse(
        f"/_console/secrets?message=Secret+%27{secret_id}%27+updated",
        status_code=303,
    )


@router.post("/secrets/{secret_id}/delete")
async def delete_secret(secret_id: str):
    if _vault:
        _vault.delete(secret_id)
    return RedirectResponse(
        f"/_console/secrets?message=Secret+%27{secret_id}%27+deleted",
        status_code=303,
    )


# ---- Deploy ----

def _deploy_context(request: Request, message: Optional[str] = None, message_type: Optional[str] = None,
                    build_summary: Optional[str] = None, deploy_output: Optional[str] = None) -> dict:
    graph = _get_graph()
    secrets = _vault.list_all() if _vault else []
    integrations = graph.list_nodes("integration")
    return {
        "request": request,
        "secrets": secrets,
        "has_gcp": any(n.attrs.get("provider") == "gcp_cloudrun" for n in integrations),
        "has_aws": any(n.attrs.get("provider") == "aws_apprunner" for n in integrations),
        "message": message,
        "message_type": message_type,
        "build_summary": build_summary,
        "deploy_output": deploy_output,
        "active_page": "deploy",
    }


@router.get("/deploy", response_class=HTMLResponse)
async def deploy_page(request: Request):
    return templates.TemplateResponse("deploy.html", _deploy_context(request))


@router.post("/deploy/build")
async def deploy_build(request: Request):
    if _generator_engine is None:
        return templates.TemplateResponse(
            "deploy.html",
            _deploy_context(request, message="Generator engine not initialized", message_type="warn"),
        )
    summary = _generator_engine.run_all()
    lines = []
    for gen_name, files in summary.items():
        lines.append(f"{gen_name}: {len(files)} file(s)")
        for f in files:
            lines.append(f"  → {f}")
    return templates.TemplateResponse(
        "deploy.html",
        _deploy_context(
            request,
            message="Build complete.",
            message_type="success",
            build_summary="\n".join(lines),
        ),
    )


def _run_deploy_script(script_path: str) -> str:
    if not Path(script_path).exists():
        return f"Deploy script not found: {script_path}\nRun Build first to generate deploy scripts."
    try:
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            timeout=600,
        )
        return (result.stdout + result.stderr) or f"Exit code: {result.returncode}"
    except subprocess.TimeoutExpired:
        return "Deploy timed out after 10 minutes."
    except Exception as e:
        return f"Deploy error: {e}"


@router.post("/deploy/gcp")
async def deploy_gcp(request: Request):
    output = _run_deploy_script("deploy/deploy_gcp.sh")
    return templates.TemplateResponse(
        "deploy.html",
        _deploy_context(request, message="GCP deploy triggered.", message_type="info", deploy_output=output),
    )


@router.post("/deploy/aws")
async def deploy_aws(request: Request):
    output = _run_deploy_script("deploy/deploy_aws.sh")
    return templates.TemplateResponse(
        "deploy.html",
        _deploy_context(request, message="AWS deploy triggered.", message_type="info", deploy_output=output),
    )
