from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph

_TYPE_MAP = {
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "datetime": "datetime",
    "list": "list",
    "dict": "dict",
}

_MODEL_TEMPLATE = '''\
# generated/models/{entity_id}.py — DO NOT EDIT
from pydantic import BaseModel
from typing import Optional


class {class_name}(BaseModel):
{fields}
'''

_INIT_TEMPLATE = '''\
# generated/models/__init__.py — DO NOT EDIT
{imports}
'''


def _to_class_name(entity_id: str) -> str:
    return "".join(part.capitalize() for part in entity_id.replace("-", "_").split("_"))


class SchemaGenerator(BaseGenerator):
    output_dir = Path("models")

    def generate(self, graph: Graph) -> dict[str, str]:
        entities = graph.list_nodes("entity")
        files: dict[str, str] = {}
        class_names: list[str] = []

        for entity in sorted(entities, key=lambda n: n.id):
            fields_def = entity.attrs.get("fields", [])
            class_name = _to_class_name(entity.id)
            class_names.append((entity.id, class_name))

            field_lines: list[str] = []
            for f in fields_def:
                name = f["name"]
                raw_type = f.get("type", "str")
                py_type = _TYPE_MAP.get(raw_type, "str")
                required = f.get("required", True)
                pii = f.get("pii", False)

                comment = "  # PII: handle with care" if pii else ""
                if required:
                    field_lines.append(f"    {name}: {py_type}{comment}")
                else:
                    field_lines.append(
                        f"    {name}: Optional[{py_type}] = None{comment}"
                    )

            if not field_lines:
                field_lines = ["    pass"]

            content = _MODEL_TEMPLATE.format(
                entity_id=entity.id,
                class_name=class_name,
                fields="\n".join(field_lines),
            )
            files[f"models/{entity.id}.py"] = content

        # Generate __init__.py
        if class_names:
            imports = "\n".join(
                f"from .{eid} import {cname}" for eid, cname in sorted(class_names)
            )
        else:
            imports = ""
        files["models/__init__.py"] = _INIT_TEMPLATE.format(imports=imports)

        return files
