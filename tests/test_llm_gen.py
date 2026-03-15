# tests/test_llm_gen.py
"""Tests for LLM generator and related functionality."""

import pytest
from agentframe.graph.store import Graph
from agentframe.graph.step_schema import (
    normalize_step,
    normalize_steps,
    validate_step,
    validate_steps,
    get_step_name,
    get_step_type,
)
from agentframe.generators.llm_gen import LLMGenerator
from agentframe.generators.route_gen import RouteGenerator
from agentframe.generators.ui_gen import UIGenerator
from agentframe.generators.engine import GeneratorEngine
from agentframe.policies.engine import PolicyEngine
from agentframe.runtime.proposals import PatchProposal


# --- Step Schema Tests ---


def test_normalize_string_step():
    """String steps normalize to form steps."""
    result = normalize_step("email_capture")
    assert result == {"name": "email_capture", "type": "form", "fields": []}


def test_normalize_dict_step_with_type():
    """Dict steps with type pass through."""
    step = {"name": "generate", "type": "llm", "integration_ref": "anthropic"}
    result = normalize_step(step)
    assert result["type"] == "llm"
    assert result["name"] == "generate"


def test_normalize_dict_step_without_type():
    """Dict steps without type default to form."""
    step = {"name": "input", "fields": []}
    result = normalize_step(step)
    assert result["type"] == "form"


def test_validate_form_step():
    """Valid form step passes validation."""
    step = {"name": "input", "type": "form", "fields": []}
    errors = validate_step(step)
    assert errors == []


def test_validate_llm_step_valid():
    """Valid LLM step passes validation."""
    step = {
        "name": "generate",
        "type": "llm",
        "integration_ref": "anthropic",
        "system_prompt": "You are helpful.",
    }
    errors = validate_step(step)
    assert errors == []


def test_validate_llm_step_missing_ref():
    """LLM step without integration_ref fails."""
    step = {"name": "generate", "type": "llm", "system_prompt": "You are helpful."}
    errors = validate_step(step)
    assert any("integration_ref" in e for e in errors)


def test_validate_llm_step_missing_prompt():
    """LLM step without system_prompt or prompt_ref fails."""
    step = {"name": "generate", "type": "llm", "integration_ref": "anthropic"}
    errors = validate_step(step)
    assert any("system_prompt" in e or "prompt_ref" in e for e in errors)


def test_validate_unknown_step_type():
    """Unknown step type fails validation."""
    step = {"name": "foo", "type": "unknown"}
    errors = validate_step(step)
    assert any("unknown" in e for e in errors)


def test_get_step_name_string():
    """get_step_name works for strings."""
    assert get_step_name("email_capture") == "email_capture"


def test_get_step_name_dict():
    """get_step_name works for dicts."""
    assert get_step_name({"name": "input", "type": "form"}) == "input"


def test_get_step_type_string():
    """get_step_type returns form for strings."""
    assert get_step_type("email_capture") == "form"


def test_get_step_type_dict():
    """get_step_type returns the type from dict."""
    assert get_step_type({"name": "gen", "type": "llm"}) == "llm"


# --- LLM Generator Tests ---


@pytest.fixture
def graph_with_llm(tmp_path):
    """Graph with LLM integration and flow."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    g.add_node(
        "integration",
        "anthropic_llm",
        "Anthropic LLM",
        attrs={
            "provider_type": "llm",
            "provider": "anthropic",
            "default_model": "claude-3-haiku-20240307",
            "env_var": "ANTHROPIC_API_KEY",
        },
    )
    g.add_node(
        "flow",
        "reflect",
        "Reflect",
        attrs={
            "steps": [
                {"name": "input", "type": "form", "fields": [{"name": "query", "type": "textarea"}]},
                {
                    "name": "generate",
                    "type": "llm",
                    "integration_ref": "anthropic_llm",
                    "system_prompt": "You are helpful.",
                },
                {"name": "result", "type": "display"},
            ],
        },
    )
    return g


def test_llm_gen_produces_client(graph_with_llm):
    """LLMGenerator produces llm_client.py when LLM integration exists."""
    gen = LLMGenerator()
    files = gen.generate(graph_with_llm)

    assert "services/llm_client.py" in files
    assert "services/anthropic_adapter.py" in files


def test_llm_gen_client_has_adapters(graph_with_llm):
    """Generated client has adapter imports and map."""
    gen = LLMGenerator()
    files = gen.generate(graph_with_llm)
    client = files["services/llm_client.py"]

    assert "AnthropicAdapter" in client
    assert "_anthropic_adapter" in client
    assert '"anthropic"' in client


def test_llm_gen_adapter_has_call_method(graph_with_llm):
    """Generated adapter has async call method."""
    gen = LLMGenerator()
    files = gen.generate(graph_with_llm)
    adapter = files["services/anthropic_adapter.py"]

    assert "async def call" in adapter
    assert "async def stream" in adapter


def test_llm_gen_no_output_without_llm(tmp_path):
    """LLMGenerator produces nothing without LLM integrations."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    g.add_node("entity", "user", "User", attrs={"fields": []})

    gen = LLMGenerator()
    files = gen.generate(g)

    assert files == {}


def test_llm_gen_openai_adapter(tmp_path):
    """LLMGenerator produces OpenAI adapter when provider is openai."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    g.add_node(
        "integration",
        "openai_llm",
        "OpenAI LLM",
        attrs={
            "provider_type": "llm",
            "provider": "openai",
            "default_model": "gpt-4o",
            "env_var": "OPENAI_API_KEY",
        },
    )

    gen = LLMGenerator()
    files = gen.generate(g)

    assert "services/openai_adapter.py" in files
    assert "OpenAIAdapter" in files["services/llm_client.py"]


# --- Route Generator LLM Step Tests ---


def test_route_gen_llm_step_produces_sse(graph_with_llm):
    """RouteGenerator produces SSE routes for LLM steps."""
    gen = RouteGenerator()
    files = gen.generate(graph_with_llm)

    content = files["routes/reflect_flow.py"]

    assert "StreamingResponse" in content
    assert "/stream/" in content
    assert "text/event-stream" in content


def test_route_gen_llm_step_has_result_route(graph_with_llm):
    """RouteGenerator produces result route for LLM steps."""
    gen = RouteGenerator()
    files = gen.generate(graph_with_llm)

    content = files["routes/reflect_flow.py"]

    assert "/result/" in content


def test_route_gen_backward_compatible(tmp_path):
    """RouteGenerator still works with legacy string steps."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    g.add_node(
        "flow",
        "signup",
        "Sign Up",
        attrs={"steps": ["email", "confirm"]},
    )

    gen = RouteGenerator()
    files = gen.generate(g)

    content = files["routes/signup_flow.py"]
    assert "/step/email" in content
    assert "/step/confirm" in content


# --- UI Generator LLM Step Tests ---


def test_ui_gen_llm_step_produces_loading_template(graph_with_llm):
    """UIGenerator produces loading template for LLM steps."""
    gen = UIGenerator()
    files = gen.generate(graph_with_llm)

    assert "templates/reflect/generate_loading.html" in files
    loading = files["templates/reflect/generate_loading.html"]
    assert "EventSource" in loading
    assert "loading-spinner" in loading


def test_ui_gen_display_step_template(graph_with_llm):
    """UIGenerator produces display template for display steps."""
    gen = UIGenerator()
    files = gen.generate(graph_with_llm)

    assert "templates/reflect/result.html" in files
    display = files["templates/reflect/result.html"]
    assert "result" in display


def test_ui_gen_form_step_with_fields(graph_with_llm):
    """UIGenerator produces form with specified fields."""
    gen = UIGenerator()
    files = gen.generate(graph_with_llm)

    form = files["templates/reflect/input.html"]
    assert 'name="query"' in form
    assert "textarea" in form


# --- Policy Tests ---


def test_policy_flow_steps_valid_passes(tmp_path):
    """Valid flow steps pass policy."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    proposal = PatchProposal(
        op="add",
        node_type="flow",
        node_id="test",
        label="Test",
        attrs={
            "steps": [
                {"name": "input", "type": "form", "fields": []},
                {
                    "name": "gen",
                    "type": "llm",
                    "integration_ref": "anthropic",
                    "system_prompt": "Hello",
                },
            ]
        },
    )

    engine = PolicyEngine(g)
    results = engine.validate(proposal)

    # Find the flow_steps_valid result
    steps_result = next((r for r in results if r.rule == "flow_steps_valid"), None)
    assert steps_result is not None
    assert steps_result.passed


def test_policy_flow_steps_invalid_fails(tmp_path):
    """Invalid flow steps fail policy."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    proposal = PatchProposal(
        op="add",
        node_type="flow",
        node_id="test",
        label="Test",
        attrs={
            "steps": [
                {"name": "gen", "type": "llm"}  # missing integration_ref and prompt
            ]
        },
    )

    engine = PolicyEngine(g)
    results = engine.validate(proposal)

    steps_result = next((r for r in results if r.rule == "flow_steps_valid"), None)
    assert steps_result is not None
    assert not steps_result.passed


def test_policy_llm_integration_valid_passes(tmp_path):
    """Valid LLM integration passes policy."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    proposal = PatchProposal(
        op="add",
        node_type="integration",
        node_id="anthropic_llm",
        label="Anthropic",
        attrs={
            "provider_type": "llm",
            "provider": "anthropic",
            "env_var": "ANTHROPIC_API_KEY",
        },
    )

    engine = PolicyEngine(g)
    results = engine.validate(proposal)

    llm_result = next((r for r in results if r.rule == "llm_integration_valid"), None)
    assert llm_result is not None
    assert llm_result.passed


def test_policy_llm_integration_invalid_fails(tmp_path):
    """LLM integration without required fields fails."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    proposal = PatchProposal(
        op="add",
        node_type="integration",
        node_id="bad_llm",
        label="Bad LLM",
        attrs={
            "provider_type": "llm",
            # missing provider and env_var
        },
    )

    engine = PolicyEngine(g)
    results = engine.validate(proposal)

    llm_result = next((r for r in results if r.rule == "llm_integration_valid"), None)
    assert llm_result is not None
    assert not llm_result.passed


def test_policy_modern_format_warns(tmp_path):
    """Legacy string steps trigger warning."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    g = Graph(db_url=db_url)
    proposal = PatchProposal(
        op="add",
        node_type="flow",
        node_id="legacy",
        label="Legacy",
        attrs={"steps": ["step1", "step2"]},
    )

    engine = PolicyEngine(g)
    results = engine.validate(proposal)

    format_result = next((r for r in results if r.rule == "flow_steps_modern_format"), None)
    assert format_result is not None
    assert not format_result.passed
    assert format_result.severity == "warn"  # warning, not error
