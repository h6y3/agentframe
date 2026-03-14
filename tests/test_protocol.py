import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlmodel import Session, select

from agentframe.graph.store import Graph
from agentframe.runtime.proposals import PatchProposal, ProposalStatus
from agentframe.protocol.server import router as mcp_router, set_graph
from agentframe.generators.engine import GeneratorEngine
from agentframe.runtime.executor import Executor
from agentframe.console.router import router as console_router, set_dependencies
from demo_app.graph_seed import seed


@pytest.fixture
def seeded_app(tmp_path):
    """Create a fresh app with seeded graph for each test."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    graph = Graph(db_url=db_url)
    seed(graph)

    gen_engine = GeneratorEngine(graph, tmp_path / "generated")
    executor = Executor(graph, gen_engine)

    set_graph(graph)
    set_dependencies(graph, executor, gen_engine)

    app = FastAPI()
    app.include_router(mcp_router)
    app.include_router(console_router)

    gen_engine.run_all()

    return app, graph


@pytest.mark.anyio
async def test_list_flows(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/list", json={"node_type": "flow"})
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "signup" in ids
    assert "login" in ids


@pytest.mark.anyio
async def test_list_all_nodes(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/list", json={})
    assert r.status_code == 200
    assert len(r.json()) >= 7  # 2 entities, 2 flows, 2 pages, 1 policy


@pytest.mark.anyio
async def test_patch_creates_proposal(seeded_app):
    """POST /mcp/graph/patch creates proposal in PENDING state."""
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/patch", json={
            "op": "add",
            "node_type": "flow",
            "node_id": "password_reset",
            "label": "Password Reset",
            "attrs": {
                "steps": ["email_lookup", "send_token", "new_password"],
                "entity_refs": ["user"],
            },
        })
    assert r.status_code == 200
    data = r.json()
    assert "proposal_id" in data
    assert data["status"] == ProposalStatus.PENDING

    # Verify it's in the DB
    with Session(graph.engine) as session:
        proposal = session.get(PatchProposal, data["proposal_id"])
        assert proposal is not None
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.node_id == "password_reset"


@pytest.mark.anyio
async def test_auto_approve_copy_change(seeded_app):
    """Patch that only changes label gets AUTO_APPROVED immediately."""
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/patch", json={
            "op": "update",
            "node_type": "page",
            "node_id": "pricing",
            "label": "Updated Pricing Page",
            "attrs": {"description": "New copy"},  # short string, no structural change
        })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == ProposalStatus.AUTO_APPROVED


@pytest.mark.anyio
async def test_structural_change_pending(seeded_app):
    """Patch that adds a new step stays PENDING for human review."""
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/patch", json={
            "op": "update",
            "node_type": "flow",
            "node_id": "signup",
            "attrs": {
                "steps": ["email_capture", "plan_select", "confirm", "welcome_tour"],
            },
        })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == ProposalStatus.PENDING


@pytest.mark.anyio
async def test_simulate_proposal(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a proposal first
        r = await client.post("/mcp/graph/patch", json={
            "op": "add",
            "node_type": "flow",
            "node_id": "onboarding",
            "label": "Onboarding",
            "attrs": {"steps": ["step1"], "entity_refs": []},
        })
        proposal_id = r.json()["proposal_id"]

        r = await client.post("/mcp/graph/simulate", json={"proposal_id": proposal_id})
    assert r.status_code == 200
    preview = r.json()["preview"]
    assert "ADD" in preview
    assert "onboarding" in preview


@pytest.mark.anyio
async def test_explain_node(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/explain", json={"node_id": "user"})
    assert r.status_code == 200
    data = r.json()
    assert data["node"]["id"] == "user"
    # signup and login flows reference user
    dependent_ids = [d["id"] for d in data["dependents"]]
    assert "signup" in dependent_ids or "login" in dependent_ids or "dashboard" in dependent_ids


@pytest.mark.anyio
async def test_query_graph(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/query", json={"q": "sign"})
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "signup" in ids


@pytest.mark.anyio
async def test_list_tools(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/mcp/tools")
    assert r.status_code == 200
    tools = r.json()
    names = [t["name"] for t in tools]
    assert "graph/list" in names
    assert "graph/patch" in names


@pytest.mark.anyio
async def test_proposals_endpoint(seeded_app):
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a proposal
        await client.post("/mcp/graph/patch", json={
            "op": "add",
            "node_type": "flow",
            "node_id": "test_flow",
            "attrs": {"steps": ["s1"], "entity_refs": []},
        })
        r = await client.get("/mcp/proposals")
    assert r.status_code == 200
    proposals = r.json()
    assert len(proposals) >= 1
    assert any(p["node_id"] == "test_flow" for p in proposals)


@pytest.mark.anyio
async def test_pii_policy_blocks_proposal(seeded_app):
    """A proposal adding a PII entity without auth should have a failing policy result."""
    app, graph = seeded_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/graph/patch", json={
            "op": "add",
            "node_type": "entity",
            "node_id": "secrets",
            "attrs": {
                "fields": [{"name": "ssn", "type": "str", "pii": True, "required": True}],
                "requires_auth": False,
            },
        })
    assert r.status_code == 200
    data = r.json()
    # Should be PENDING (not auto-approved) because policy fails
    assert data["status"] == ProposalStatus.PENDING

    # Check the proposal has failed policy results
    with Session(graph.engine) as session:
        proposal = session.get(PatchProposal, data["proposal_id"])
        failed = [r for r in proposal.policy_results if not r["passed"] and r["severity"] == "error"]
        assert len(failed) > 0
