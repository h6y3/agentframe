from agentframe.policies.base import policy, PolicyResult
from agentframe.runtime.proposals import PatchProposal
from agentframe.graph.store import Graph

MAX_WIDGETS = 8


@policy("widget_limit")
def check(proposal: PatchProposal, graph: Graph) -> PolicyResult:
    """
    Any PageNode with more than 8 widgets fails with a warning (not error).
    """
    rule = "widget_limit"

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

    widgets = attrs.get("widgets", [])

    if len(widgets) > MAX_WIDGETS:
        return PolicyResult.fail(
            rule,
            f"Page '{proposal.node_id}' has {len(widgets)} widgets (max {MAX_WIDGETS}). "
            "Consider splitting into multiple pages.",
            severity="warn",
        )

    return PolicyResult.pass_(rule)
