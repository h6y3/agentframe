from agentframe.policies.base import policy, PolicyResult
from agentframe.runtime.proposals import PatchProposal
from agentframe.graph.store import Graph


@policy("auth_required_on_sensitive_pages")
def check(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Any PageNode that references an EntityNode with PII fields
    must have requires_auth: True.
    """
    rule = "auth_required_on_sensitive_pages"

    if proposal.node_type != "page":
        return PolicyResult.pass_(rule)

    if proposal.op == "remove":
        return PolicyResult.pass_(rule)

    attrs = proposal.attrs

    # For updates, merge with existing
    if proposal.op == "update":
        existing = graph.get_node(proposal.node_id)
        if existing:
            attrs = {**existing.attrs, **attrs}

    entity_refs: list[str] = attrs.get("entity_refs", [])
    requires_auth: bool = attrs.get("requires_auth", False)

    # Check if any referenced entity has PII fields
    for entity_id in entity_refs:
        entity = graph.get_node(entity_id)
        if entity is None:
            continue
        fields = entity.attrs.get("fields", [])
        has_pii = any(f.get("pii", False) for f in fields)
        if has_pii and not requires_auth:
            return PolicyResult.fail(
                rule,
                f"Page '{proposal.node_id}' references entity '{entity_id}' which has PII fields, "
                "but requires_auth is False. Set requires_auth: true.",
                severity="error",
            )

    return PolicyResult.pass_(rule)
