from datetime import datetime
from typing import Optional
from sqlmodel import Session

from agentframe.graph.store import Graph
from agentframe.runtime.proposals import PatchProposal, ProposalStatus


class Executor:
    def __init__(self, graph: Graph, generator_engine=None):
        self.graph = graph
        self.generator_engine = generator_engine

    def apply(self, proposal_id: str) -> bool:
        """
        1. Double-check proposal status is APPROVED or AUTO_APPROVED
        2. Apply the graph mutation (add/update/remove node)
        3. Run generator engine for blast radius of changed node
        4. Mark proposal resolved_at
        5. Return True on success
        """
        with Session(self.graph.engine) as session:
            proposal = session.get(PatchProposal, proposal_id)
            if proposal is None:
                return False
            if proposal.status not in (ProposalStatus.APPROVED, ProposalStatus.AUTO_APPROVED):
                return False

            op = proposal.op
            node_id = proposal.node_id
            node_type = proposal.node_type
            attrs = proposal.attrs
            label = proposal.label

            proposal.resolved_at = datetime.utcnow()
            session.add(proposal)
            session.commit()

        # Apply graph mutation
        if op == "add":
            effective_label = label or attrs.get("label", node_id)
            self.graph.add_node(node_type, node_id, effective_label, attrs, proposal_id=proposal_id)
        elif op == "update":
            self.graph.update_node(node_id, attrs, label=label, proposal_id=proposal_id)
        elif op == "remove":
            self.graph.remove_node(node_id, proposal_id=proposal_id)

        # Re-run generators for affected nodes
        if self.generator_engine is not None:
            self.generator_engine.run_for_node(node_id)

        return True

    def approve(self, proposal_id: str) -> bool:
        """Mark proposal APPROVED, then apply it."""
        with Session(self.graph.engine) as session:
            proposal = session.get(PatchProposal, proposal_id)
            if proposal is None:
                return False
            if proposal.status != ProposalStatus.PENDING:
                return False
            proposal.status = ProposalStatus.APPROVED
            proposal.resolved_by = "human:approve"
            session.add(proposal)
            session.commit()

        return self.apply(proposal_id)

    def reject(self, proposal_id: str) -> bool:
        """Mark proposal REJECTED. Do not touch the graph."""
        with Session(self.graph.engine) as session:
            proposal = session.get(PatchProposal, proposal_id)
            if proposal is None:
                return False
            proposal.status = ProposalStatus.REJECTED
            proposal.resolved_at = datetime.utcnow()
            proposal.resolved_by = "human:reject"
            session.add(proposal)
            session.commit()
        return True
