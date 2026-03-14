from datetime import datetime
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session, select

from agentframe.graph.store import Graph
from agentframe.runtime.proposals import PatchProposal, ProposalStatus
from agentframe.policies.engine import PolicyEngine

router = APIRouter(prefix="/mcp", tags=["mcp"])

# These will be set by the application at startup
_graph: Optional[Graph] = None


def set_graph(graph: Graph) -> None:
    global _graph
    _graph = graph


def get_graph() -> Graph:
    if _graph is None:
        raise RuntimeError("Graph not initialized. Call set_graph() first.")
    return _graph


# ---------- Request/Response models ----------

class ListRequest(BaseModel):
    node_type: Optional[str] = None
    filter: Optional[str] = None


class PatchRequest(BaseModel):
    op: str  # "add" | "update" | "remove"
    node_type: str
    node_id: str
    attrs: dict = {}
    label: Optional[str] = None


class SimulateRequest(BaseModel):
    proposal_id: str


class ExplainRequest(BaseModel):
    node_id: str


class QueryRequest(BaseModel):
    q: str


# ---------- Helpers ----------

def _node_to_dict(node) -> dict:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "label": node.label,
        "attrs": node.attrs,
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }


def _is_low_risk(proposal: PatchProposal) -> bool:
    """
    Auto-approve only if the changed attrs are label or string values under 200 chars.
    Structural changes (steps, fields, entity_refs, etc.) require human review.
    """
    if proposal.op == "remove":
        return False
    if proposal.op == "add":
        return False

    # For updates: check if only copy-like changes
    structural_keys = {"fields", "steps", "entity_refs", "widgets", "requires_auth", "rule_fn"}
    changed_keys = set(proposal.attrs.keys())

    if changed_keys & structural_keys:
        return False

    # All changed values must be short strings
    for v in proposal.attrs.values():
        if not isinstance(v, str):
            return False
        if len(v) > 200:
            return False

    return True


def _policy_result_to_dict(r) -> dict:
    return {
        "rule": r.rule,
        "passed": r.passed,
        "reason": r.reason,
        "severity": r.severity,
    }


# ---------- Endpoints ----------

@router.post("/graph/list")
async def list_nodes(req: ListRequest) -> list[dict]:
    graph = get_graph()
    nodes = graph.list_nodes(node_type=req.node_type)
    if req.filter:
        q = req.filter.lower()
        nodes = [n for n in nodes if q in n.label.lower() or q in n.id.lower()]
    return [_node_to_dict(n) for n in nodes]


@router.post("/graph/patch")
async def patch_graph(req: PatchRequest) -> dict:
    graph = get_graph()
    policy_engine = PolicyEngine(graph)

    # Create proposal
    proposal = PatchProposal(
        op=req.op,
        node_type=req.node_type,
        node_id=req.node_id,
        attrs=req.attrs,
        label=req.label,
        status=ProposalStatus.PENDING,
    )

    # Run policies
    results = policy_engine.validate(proposal)
    proposal.policy_results = [_policy_result_to_dict(r) for r in results]

    # Determine status
    policies_pass = policy_engine.is_approved(results)
    low_risk = _is_low_risk(proposal)

    if policies_pass and low_risk:
        proposal.status = ProposalStatus.AUTO_APPROVED
        proposal.resolved_at = datetime.utcnow()
        proposal.resolved_by = "auto"

    # Persist proposal
    with Session(graph.engine) as session:
        session.add(proposal)
        session.commit()
        session.refresh(proposal)
        proposal_id = proposal.id
        status = proposal.status

    # If auto-approved, apply immediately
    if status == ProposalStatus.AUTO_APPROVED:
        _apply_proposal(graph, proposal)

    return {"proposal_id": proposal_id, "status": status}


@router.post("/graph/simulate")
async def simulate_patch(req: SimulateRequest) -> dict:
    graph = get_graph()

    with Session(graph.engine) as session:
        proposal = session.get(PatchProposal, req.proposal_id)
        if proposal is None:
            return {"preview": "Proposal not found."}

        op = proposal.op
        node_id = proposal.node_id
        node_type = proposal.node_type
        new_attrs = proposal.attrs
        new_label = proposal.label

    existing = graph.get_node(node_id)

    lines = [f"--- Proposal: {op.upper()} {node_type} '{node_id}' ---"]

    if op == "add":
        lines.append("+ New node:")
        lines.append(f"  id:    {node_id}")
        lines.append(f"  type:  {node_type}")
        lines.append(f"  label: {new_label or new_attrs.get('label', '')}")
        for k, v in new_attrs.items():
            lines.append(f"  {k}: {v}")

    elif op == "update" and existing:
        lines.append("~ Changes:")
        if new_label and new_label != existing.label:
            lines.append(f"  label: '{existing.label}' → '{new_label}'")
        for k, v in new_attrs.items():
            old_v = existing.attrs.get(k, "<not set>")
            if old_v != v:
                lines.append(f"  {k}:")
                lines.append(f"    - {old_v}")
                lines.append(f"    + {v}")

    elif op == "remove" and existing:
        lines.append(f"- Remove node: {node_id} ({existing.label})")

    elif existing is None and op != "add":
        lines.append(f"  (node '{node_id}' not found in graph)")

    return {"preview": "\n".join(lines)}


@router.post("/graph/explain")
async def explain_node(req: ExplainRequest) -> dict:
    graph = get_graph()
    node = graph.get_node(req.node_id)
    if node is None:
        return {"error": f"Node '{req.node_id}' not found"}

    all_nodes = graph.list_nodes()

    # Dependencies: nodes that this node references
    dependencies = []
    for ref_id in node.attrs.get("entity_refs", []):
        ref_node = graph.get_node(ref_id)
        if ref_node:
            dependencies.append(_node_to_dict(ref_node))

    # Dependents: nodes that reference this node
    dependents = []
    for other in all_nodes:
        if other.id == node.id:
            continue
        refs = other.attrs.get("entity_refs", [])
        if node.id in refs:
            dependents.append(_node_to_dict(other))

    return {
        "node": _node_to_dict(node),
        "dependencies": dependencies,
        "dependents": dependents,
    }


@router.post("/graph/query")
async def query_graph(req: QueryRequest) -> list[dict]:
    graph = get_graph()
    nodes = graph.query(req.q)
    return [_node_to_dict(n) for n in nodes]


@router.get("/proposals")
async def list_proposals() -> list[dict]:
    graph = get_graph()
    with Session(graph.engine) as session:
        stmt = select(PatchProposal).order_by(PatchProposal.created_at.desc())
        proposals = list(session.exec(stmt).all())
    return [
        {
            "id": p.id,
            "op": p.op,
            "node_type": p.node_type,
            "node_id": p.node_id,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
            "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
            "resolved_by": p.resolved_by,
            "policy_results": p.policy_results,
        }
        for p in proposals
    ]


@router.get("/tools")
async def list_tools() -> list[dict]:
    return [
        {
            "name": "graph/list",
            "description": "List nodes in the product graph",
            "method": "POST",
            "path": "/mcp/graph/list",
            "input_schema": {
                "node_type": "optional string: entity|flow|page|policy",
                "filter": "optional string keyword filter",
            },
        },
        {
            "name": "graph/patch",
            "description": "Propose a graph mutation (add/update/remove a node)",
            "method": "POST",
            "path": "/mcp/graph/patch",
            "input_schema": {
                "op": "add|update|remove",
                "node_type": "string",
                "node_id": "string",
                "attrs": "dict",
                "label": "optional string",
            },
        },
        {
            "name": "graph/simulate",
            "description": "Preview a proposal as a before/after diff",
            "method": "POST",
            "path": "/mcp/graph/simulate",
            "input_schema": {"proposal_id": "string"},
        },
        {
            "name": "graph/explain",
            "description": "Explain a node and its dependencies/dependents",
            "method": "POST",
            "path": "/mcp/graph/explain",
            "input_schema": {"node_id": "string"},
        },
        {
            "name": "graph/query",
            "description": "Keyword search across the product graph",
            "method": "POST",
            "path": "/mcp/graph/query",
            "input_schema": {"q": "string"},
        },
        {
            "name": "proposals",
            "description": "List all patch proposals with their status",
            "method": "GET",
            "path": "/mcp/proposals",
        },
    ]


def _apply_proposal(graph: Graph, proposal: PatchProposal) -> None:
    """Apply an approved proposal to the graph. Used internally by auto-approve."""
    if proposal.op == "add":
        label = proposal.label or proposal.attrs.get("label", proposal.node_id)
        graph.add_node(
            proposal.node_type,
            proposal.node_id,
            label,
            proposal.attrs,
            proposal_id=proposal.id,
        )
    elif proposal.op == "update":
        graph.update_node(
            proposal.node_id,
            proposal.attrs,
            label=proposal.label,
            proposal_id=proposal.id,
        )
    elif proposal.op == "remove":
        graph.remove_node(proposal.node_id, proposal_id=proposal.id)
