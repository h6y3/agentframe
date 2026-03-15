from agentframe.graph.store import Graph
from agentframe.policies.base import PolicyResult, get_all_policies
from agentframe.runtime.proposals import PatchProposal

# Import builtin policies to register them
import agentframe.policies.builtin.no_public_pii  # noqa: F401
import agentframe.policies.builtin.auth_required  # noqa: F401
import agentframe.policies.builtin.widget_limit  # noqa: F401
import agentframe.policies.builtin.llm_policies  # noqa: F401


class PolicyEngine:
    def __init__(self, graph: Graph):
        self.graph = graph

    def validate(self, proposal: PatchProposal) -> list[PolicyResult]:
        """Run all registered policies. Return all results (pass + fail)."""
        results = []
        for policy_fn in get_all_policies():
            result = policy_fn(proposal, self.graph)
            results.append(result)
        return results

    def is_approved(self, results: list[PolicyResult]) -> bool:
        """True only if no ERROR-severity failures."""
        return all(r.passed or r.severity != "error" for r in results)
