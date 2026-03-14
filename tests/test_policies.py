import pytest
from agentframe.graph.store import Graph
from agentframe.runtime.proposals import PatchProposal, ProposalStatus
from agentframe.policies.engine import PolicyEngine
from agentframe.policies.base import get_all_policies


@pytest.fixture
def graph(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    return Graph(db_url=db_url)


def _make_proposal(op, node_type, node_id, attrs, label=None):
    return PatchProposal(
        op=op,
        node_type=node_type,
        node_id=node_id,
        attrs=attrs,
        label=label,
        status=ProposalStatus.PENDING,
    )


def test_pii_without_auth_fails(graph):
    """EntityNode with pii=True and requires_auth=False → policy error."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "entity", "profile",
        attrs={
            "fields": [{"name": "ssn", "type": "str", "pii": True, "required": True}],
            "requires_auth": False,
        },
    )
    results = engine.validate(proposal)
    pii_results = [r for r in results if r.rule == "no_public_pii"]
    assert len(pii_results) == 1
    assert not pii_results[0].passed
    assert pii_results[0].severity == "error"
    assert not engine.is_approved(results)


def test_pii_with_auth_passes(graph):
    """EntityNode with pii=True and requires_auth=True → policy pass."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "entity", "profile",
        attrs={
            "fields": [{"name": "email", "type": "str", "pii": True, "required": True}],
            "requires_auth": True,
        },
    )
    results = engine.validate(proposal)
    pii_results = [r for r in results if r.rule == "no_public_pii"]
    assert len(pii_results) == 1
    assert pii_results[0].passed
    assert engine.is_approved(results)


def test_no_pii_fields_passes_regardless_of_auth(graph):
    """EntityNode with no PII → passes regardless of requires_auth."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "entity", "plan",
        attrs={
            "fields": [{"name": "name", "type": "str", "pii": False, "required": True}],
            "requires_auth": False,
        },
    )
    results = engine.validate(proposal)
    pii_results = [r for r in results if r.rule == "no_public_pii"]
    assert pii_results[0].passed


def test_widget_limit_warn(graph):
    """PageNode with 9 widgets → warning (not error), proposal still approvable."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "page", "megapage",
        attrs={
            "widgets": [f"widget_{i}" for i in range(9)],
            "requires_auth": False,
            "entity_refs": [],
        },
    )
    results = engine.validate(proposal)
    widget_results = [r for r in results if r.rule == "widget_limit"]
    assert len(widget_results) == 1
    assert not widget_results[0].passed
    assert widget_results[0].severity == "warn"
    # Warning does not block approval
    assert engine.is_approved(results)


def test_widget_limit_ok(graph):
    """PageNode with 8 widgets → passes."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "page", "page8",
        attrs={
            "widgets": [f"w{i}" for i in range(8)],
            "requires_auth": False,
            "entity_refs": [],
        },
    )
    results = engine.validate(proposal)
    widget_results = [r for r in results if r.rule == "widget_limit"]
    assert widget_results[0].passed


def test_auth_required_on_page_with_pii_entity(graph):
    """Page referencing a PII entity must have requires_auth=True."""
    # Add the entity first
    graph.add_node("entity", "user", "User", attrs={
        "fields": [{"name": "email", "type": "str", "pii": True, "required": True}],
        "requires_auth": True,
    })

    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "page", "public_profile",
        attrs={
            "widgets": ["user_card"],
            "requires_auth": False,
            "entity_refs": ["user"],
        },
    )
    results = engine.validate(proposal)
    auth_results = [r for r in results if r.rule == "auth_required_on_sensitive_pages"]
    assert len(auth_results) == 1
    assert not auth_results[0].passed
    assert auth_results[0].severity == "error"
    assert not engine.is_approved(results)


def test_non_entity_proposals_pass_pii_policy(graph):
    """A flow proposal is irrelevant to PII policy."""
    engine = PolicyEngine(graph)
    proposal = _make_proposal(
        "add", "flow", "signup",
        attrs={"steps": ["a", "b"], "entity_refs": []},
    )
    results = engine.validate(proposal)
    pii_results = [r for r in results if r.rule == "no_public_pii"]
    assert pii_results[0].passed
