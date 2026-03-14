import pytest
from agentframe.graph.store import Graph


@pytest.fixture
def graph(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    return Graph(db_url=db_url)


def test_add_node(graph):
    node = graph.add_node(
        "entity",
        "user",
        "User",
        attrs={"fields": [{"name": "email", "type": "str", "pii": True, "required": True}]},
    )
    assert node.id == "user"
    assert node.label == "User"
    assert node.node_type == "entity"

    retrieved = graph.get_node("user")
    assert retrieved is not None
    assert retrieved.attrs["fields"][0]["name"] == "email"


def test_event_log_appends(graph):
    graph.add_node("entity", "user", "User", attrs={})
    events = graph.get_event_log()
    assert len(events) == 1
    assert events[0].event_type == "ADD_NODE"
    assert events[0].node_id == "user"


def test_event_log_update_and_remove(graph):
    graph.add_node("entity", "user", "User", attrs={"foo": "bar"})
    graph.update_node("user", {"foo": "baz"})
    graph.remove_node("user")

    events = graph.get_event_log()
    assert len(events) == 3
    assert [e.event_type for e in events] == ["ADD_NODE", "UPDATE_NODE", "REMOVE_NODE"]

    # Node should be gone
    assert graph.get_node("user") is None


def test_query_by_entity_ref(graph):
    """query('pages that reference user') should return dashboard-like pages."""
    graph.add_node("entity", "user", "User", attrs={})
    graph.add_node(
        "page",
        "dashboard",
        "Dashboard",
        attrs={"entity_refs": ["user"], "widgets": [], "requires_auth": True},
    )
    graph.add_node(
        "page",
        "pricing",
        "Pricing",
        attrs={"entity_refs": ["plan"], "widgets": [], "requires_auth": False},
    )

    results = graph.query("user")
    ids = [n.id for n in results]
    assert "user" in ids
    assert "dashboard" in ids
    assert "pricing" not in ids


def test_replay(graph):
    """Replay to first event — second node should not be present."""
    graph.add_node("entity", "user", "User", attrs={})
    events_after_first = graph.get_event_log()
    first_event_id = events_after_first[0].id

    graph.add_node("entity", "plan", "Plan", attrs={})

    # Replay to the first event only
    replayed = graph.replay_to(first_event_id)
    assert replayed.get_node("user") is not None
    assert replayed.get_node("plan") is None


def test_list_nodes_by_type(graph):
    graph.add_node("entity", "user", "User", attrs={})
    graph.add_node("flow", "signup", "Sign Up", attrs={"steps": [], "entity_refs": []})
    graph.add_node("page", "dashboard", "Dashboard", attrs={})

    entities = graph.list_nodes("entity")
    flows = graph.list_nodes("flow")
    all_nodes = graph.list_nodes()

    assert len(entities) == 1
    assert entities[0].id == "user"
    assert len(flows) == 1
    assert len(all_nodes) == 3


def test_update_node_merges_attrs(graph):
    graph.add_node("entity", "user", "User", attrs={"a": 1, "b": 2})
    graph.update_node("user", {"b": 99, "c": 3})
    node = graph.get_node("user")
    assert node.attrs["a"] == 1
    assert node.attrs["b"] == 99
    assert node.attrs["c"] == 3
