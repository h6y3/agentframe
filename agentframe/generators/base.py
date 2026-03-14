from abc import ABC, abstractmethod
from pathlib import Path
from agentframe.graph.store import Graph


class BaseGenerator(ABC):
    output_dir: Path

    @abstractmethod
    def generate(self, graph: Graph) -> dict[str, str]:
        """
        Pure function. Takes graph, returns {filepath: file_content}.
        Must be deterministic — same graph always produces same output.
        """

    def write(self, graph: Graph, base_path: Path) -> list[Path]:
        """Calls generate(), writes files, returns written paths."""
        files = self.generate(graph)
        written = []
        for rel_path, content in files.items():
            full_path = base_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
