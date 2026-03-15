# agentframe/policies/builtin/llm_policies.py
"""
LLM-specific policies for validating graph mutations.

Policies:
- flow_steps_valid: Validate step schema in flow nodes
- llm_has_prompt: Ensure LLM steps have system_prompt or prompt_ref
- llm_integration_valid: Validate LLM integration nodes
"""

from agentframe.policies.base import policy, PolicyResult
from agentframe.runtime.proposals import PatchProposal
from agentframe.graph.store import Graph
from agentframe.graph.step_schema import normalize_steps, validate_steps, get_step_type


@policy("flow_steps_valid")
def check_flow_steps(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Validate that all steps in a flow node have valid schema.

    Catches:
    - Unknown step types
    - Missing required fields for each step type
    - LLM steps without prompts
    """
    rule = "flow_steps_valid"

    # Only relevant for flow nodes
    if proposal.node_type != "flow":
        return PolicyResult.pass_(rule)

    if proposal.op == "remove":
        return PolicyResult.pass_(rule)

    # Get the attrs that will be in effect after the proposal
    attrs = proposal.attrs

    # For updates, merge with existing node attrs
    if proposal.op == "update":
        existing = graph.get_node(proposal.node_id)
        if existing:
            merged = {**existing.attrs, **attrs}
            attrs = merged

    steps = attrs.get("steps", [])
    if not steps:
        return PolicyResult.pass_(rule)

    errors = validate_steps(steps)

    if errors:
        return PolicyResult.fail(
            rule,
            f"Flow '{proposal.node_id}' has invalid steps: {'; '.join(errors)}",
            severity="error",
        )

    return PolicyResult.pass_(rule)


@policy("llm_integration_ref_exists")
def check_llm_integration_ref(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Validate that LLM steps reference existing integration nodes.
    """
    rule = "llm_integration_ref_exists"

    # Only relevant for flow nodes
    if proposal.node_type != "flow":
        return PolicyResult.pass_(rule)

    if proposal.op == "remove":
        return PolicyResult.pass_(rule)

    attrs = proposal.attrs
    if proposal.op == "update":
        existing = graph.get_node(proposal.node_id)
        if existing:
            attrs = {**existing.attrs, **attrs}

    steps = attrs.get("steps", [])
    normalized = normalize_steps(steps)

    missing_refs = []
    for step in normalized:
        if get_step_type(step) == "llm":
            ref = step.get("integration_ref")
            if ref:
                integration = graph.get_node(ref)
                if integration is None:
                    missing_refs.append(f"Step '{step.get('name')}' references non-existent integration: {ref}")
                elif integration.attrs.get("provider_type") != "llm":
                    missing_refs.append(
                        f"Step '{step.get('name')}' references integration '{ref}' "
                        f"but it has provider_type='{integration.attrs.get('provider_type')}', expected 'llm'"
                    )

    if missing_refs:
        return PolicyResult.fail(
            rule,
            f"Flow '{proposal.node_id}' has invalid integration refs: {'; '.join(missing_refs)}",
            severity="error",
        )

    return PolicyResult.pass_(rule)


@policy("llm_integration_valid")
def check_llm_integration(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Validate LLM integration nodes have required fields.
    """
    rule = "llm_integration_valid"

    # Only relevant for integration nodes
    if proposal.node_type != "integration":
        return PolicyResult.pass_(rule)

    if proposal.op == "remove":
        return PolicyResult.pass_(rule)

    attrs = proposal.attrs
    if proposal.op == "update":
        existing = graph.get_node(proposal.node_id)
        if existing:
            attrs = {**existing.attrs, **attrs}

    # Only validate LLM integrations
    if attrs.get("provider_type") != "llm":
        return PolicyResult.pass_(rule)

    errors = []

    if not attrs.get("provider"):
        errors.append("provider is required")

    provider = attrs.get("provider", "").lower()
    valid_providers = ["anthropic", "openai"]
    if provider and provider not in valid_providers:
        errors.append(f"provider '{provider}' not supported. Valid: {valid_providers}")

    if not attrs.get("env_var"):
        errors.append("env_var is required (e.g., ANTHROPIC_API_KEY)")

    if errors:
        return PolicyResult.fail(
            rule,
            f"LLM integration '{proposal.node_id}' is invalid: {'; '.join(errors)}",
            severity="error",
        )

    return PolicyResult.pass_(rule)


@policy("flow_steps_modern_format")
def check_modern_format(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Warn if flow uses legacy string step format.

    This is a warning, not an error - legacy format is still supported
    but dict format is recommended for new flows.
    """
    rule = "flow_steps_modern_format"

    if proposal.node_type != "flow":
        return PolicyResult.pass_(rule)

    if proposal.op == "remove":
        return PolicyResult.pass_(rule)

    attrs = proposal.attrs
    if proposal.op == "update":
        existing = graph.get_node(proposal.node_id)
        if existing:
            attrs = {**existing.attrs, **attrs}

    steps = attrs.get("steps", [])
    has_string_steps = any(isinstance(s, str) for s in steps)

    if has_string_steps:
        return PolicyResult.fail(
            rule,
            f"Flow '{proposal.node_id}' uses legacy string step format. "
            "Consider migrating to dict format for LLM support.",
            severity="warn",
        )

    return PolicyResult.pass_(rule)
