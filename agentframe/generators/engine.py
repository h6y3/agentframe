from pathlib import Path
from agentframe.graph.store import Graph
from agentframe.generators.route_gen import RouteGenerator
from agentframe.generators.schema_gen import SchemaGenerator
from agentframe.generators.ui_gen import UIGenerator
from agentframe.generators.crud_gen import CRUDGenerator
from agentframe.generators.auth_gen import AuthGenerator
from agentframe.generators.migration_gen import MigrationGenerator
from agentframe.generators.docker_gen import DockerfileGenerator
from agentframe.generators.deploy_gen import DeploymentGenerator
from agentframe.generators.prod_gen import ProdGenerator


# Map generator names to which node types trigger them
_GENERATOR_TRIGGERS: dict[str, list[str]] = {
    "RouteGenerator":       ["flow"],
    "SchemaGenerator":      ["entity"],
    "UIGenerator":          ["flow", "page", "entity"],
    "CRUDGenerator":        ["entity"],
    "AuthGenerator":        ["integration"],
    "MigrationGenerator":   ["entity"],
    "DockerfileGenerator":  ["entity", "flow", "integration"],
    "DeploymentGenerator":  ["integration"],
    "ProdGenerator":        ["entity", "flow", "integration"],
}


class GeneratorEngine:
    def __init__(self, graph: Graph, output_path: Path):
        self.graph = graph
        self.output_path = output_path
        self.generators = [
            RouteGenerator(),
            SchemaGenerator(),
            UIGenerator(),
            CRUDGenerator(),
            AuthGenerator(),
            MigrationGenerator(),
            DockerfileGenerator(),
            DeploymentGenerator(),
            ProdGenerator(),
        ]

    def run_all(self) -> dict:
        """Run all generators, return summary of files written."""
        summary: dict[str, list[str]] = {}
        for gen in self.generators:
            name = type(gen).__name__
            written = gen.write(self.graph, self.output_path)
            summary[name] = [str(p) for p in written]
        return summary

    def run_for_node(self, node_id: str) -> dict:
        """
        Compute blast radius: which generators are affected by a change
        to this node, then run only those.
        """
        affected_names = self._compute_blast_radius(node_id)
        summary: dict[str, list[str]] = {}
        for gen in self.generators:
            name = type(gen).__name__
            if name in affected_names:
                written = gen.write(self.graph, self.output_path)
                summary[name] = [str(p) for p in written]
        return summary

    def _compute_blast_radius(self, node_id: str) -> list[str]:
        """
        Returns list of generator names that need to re-run.
        E.g. changing an EntityNode triggers SchemaGenerator + UIGenerator
             for any FlowNode that references that entity.
        """
        node = self.graph.get_node(node_id)
        if node is None:
            return []

        affected = set()
        direct_type = node.node_type

        # Direct triggers based on node type
        for gen_name, triggers in _GENERATOR_TRIGGERS.items():
            if direct_type in triggers:
                affected.add(gen_name)

        # If an entity changes, also trigger generators for flows/pages that reference it
        if direct_type == "entity":
            for other in self.graph.list_nodes():
                refs = other.attrs.get("entity_refs", [])
                if node_id in refs:
                    for gen_name, triggers in _GENERATOR_TRIGGERS.items():
                        if other.node_type in triggers:
                            affected.add(gen_name)

        return list(affected)
