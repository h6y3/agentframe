import pytest
from pathlib import Path
from agentframe.graph.store import Graph
from agentframe.generators.route_gen import RouteGenerator
from agentframe.generators.schema_gen import SchemaGenerator
from agentframe.generators.ui_gen import UIGenerator
from agentframe.generators.engine import GeneratorEngine


@pytest.fixture
def graph(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    g.add_node("entity", "user", "User", attrs={
        "fields": [
            {"name": "email", "type": "str", "pii": True, "required": True},
            {"name": "name", "type": "str", "pii": False, "required": False},
        ],
        "requires_auth": True,
    })
    g.add_node("flow", "signup", "Sign Up", attrs={
        "steps": ["email_capture", "plan_select", "confirm"],
        "entity_refs": ["user"],
    })
    g.add_node("page", "dashboard", "Dashboard", attrs={
        "widgets": ["feed", "chart"],
        "requires_auth": True,
        "entity_refs": ["user"],
    })
    return g


def test_route_gen_produces_file(graph, tmp_path):
    gen = RouteGenerator()
    files = gen.generate(graph)

    assert "routes/signup_flow.py" in files
    content = files["routes/signup_flow.py"]
    assert "router = APIRouter" in content
    assert 'prefix="/signup"' in content
    assert "signup_start" in content


def test_route_gen_all_steps_present(graph, tmp_path):
    gen = RouteGenerator()
    files = gen.generate(graph)
    content = files["routes/signup_flow.py"]

    assert "/step/email_capture" in content
    assert "/step/plan_select" in content
    assert "/step/confirm" in content
    assert "/start" in content
    assert "/complete" in content


def test_schema_gen_produces_model(graph, tmp_path):
    gen = SchemaGenerator()
    files = gen.generate(graph)

    assert "models/user.py" in files
    content = files["models/user.py"]
    assert "class User(BaseModel)" in content
    assert "email: str" in content
    assert "PII" in content


def test_schema_gen_init_imports(graph, tmp_path):
    gen = SchemaGenerator()
    files = gen.generate(graph)

    assert "models/__init__.py" in files
    init_content = files["models/__init__.py"]
    assert "from .user import User" in init_content


def test_deterministic(graph):
    """Same graph always produces byte-for-byte identical output."""
    gen = RouteGenerator()
    first = gen.generate(graph)
    second = gen.generate(graph)
    assert first == second

    gen2 = SchemaGenerator()
    first2 = gen2.generate(graph)
    second2 = gen2.generate(graph)
    assert first2 == second2


def test_blast_radius_flow_node(graph, tmp_path):
    """Changing a FlowNode should trigger UIGenerator but not SchemaGenerator."""
    engine = GeneratorEngine(graph, tmp_path / "generated")
    affected = engine._compute_blast_radius("signup")

    assert "UIGenerator" in affected
    assert "RouteGenerator" in affected
    assert "SchemaGenerator" not in affected


def test_blast_radius_entity_node(graph, tmp_path):
    """Changing an EntityNode triggers SchemaGenerator + UIGenerator."""
    engine = GeneratorEngine(graph, tmp_path / "generated")
    affected = engine._compute_blast_radius("user")

    assert "SchemaGenerator" in affected
    assert "UIGenerator" in affected


def test_engine_run_all_writes_files(graph, tmp_path):
    engine = GeneratorEngine(graph, tmp_path / "generated")
    summary = engine.run_all()

    route_file = tmp_path / "generated" / "routes" / "signup_flow.py"
    assert route_file.exists()

    model_file = tmp_path / "generated" / "models" / "user.py"
    assert model_file.exists()

    base_html = tmp_path / "generated" / "templates" / "base.html"
    assert base_html.exists()


def test_ui_gen_flow_templates(graph):
    gen = UIGenerator()
    files = gen.generate(graph)

    assert "templates/signup/email_capture.html" in files
    assert "templates/signup/plan_select.html" in files
    assert "templates/signup/confirm.html" in files
    assert "templates/signup/complete.html" in files
    assert "templates/base.html" in files


def test_ui_gen_page_templates(graph):
    gen = UIGenerator()
    files = gen.generate(graph)

    assert "templates/dashboard.html" in files
    content = files["templates/dashboard.html"]
    assert "Dashboard" in content
    assert "feed" in content.lower() or "Feed" in content
