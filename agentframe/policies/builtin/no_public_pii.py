from agentframe.policies.base import policy, PolicyResult
from agentframe.runtime.proposals import PatchProposal
from agentframe.graph.store import Graph


@policy("no_public_pii")
def check(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Any EntityNode field marked pii: True must also have requires_auth: True.
    Fail with error if PII is publicly accessible.
    """
    rule = "no_public_pii"

    # Only relevant for entity nodes
    if proposal.node_type != "entity":
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

    fields = attrs.get("fields", [])
    requires_auth = attrs.get("requires_auth", False)

    has_pii = any(f.get("pii", False) for f in fields)

    if has_pii and not requires_auth:
        return PolicyResult.fail(
            rule,
            f"Entity '{proposal.node_id}' has PII fields but requires_auth is False. "
            "Set requires_auth: true to protect PII.",
            severity="error",
        )

    return PolicyResult.pass_(rule)
