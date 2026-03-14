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


def _class_name(entity_id: str) -> str:
    return "".join(w.title() for w in entity_id.split("_"))


def _render_table(entity) -> str:
    class_name = _class_name(entity.id)
    fields = entity.attrs.get("fields", [])

    field_lines = []
    for f in fields:
        py_type = _TYPE_MAP.get(f.get("type", "str"), "str")
        required = f.get("required", True)
        if py_type == "datetime":
            if required:
                field_lines.append(
                    f"    {f['name']}: datetime = Field(default_factory=datetime.utcnow)"
                )
            else:
                field_lines.append(
                    f"    {f['name']}: Optional[datetime] = Field(default=None)"
                )
        elif required:
            field_lines.append(f"    {f['name']}: {py_type}")
        else:
            field_lines.append(f"    {f['name']}: Optional[{py_type}] = None")

    fields_block = "\n".join(field_lines) if field_lines else "    pass"

    return f"""\
# generated/models/{entity.id}_table.py — DO NOT EDIT
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class {class_name}Table(SQLModel, table=True):
    __tablename__ = "{entity.id}s"
    id: Optional[int] = Field(default=None, primary_key=True)
{fields_block}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
"""


def _render_crud_router(entity) -> str:
    class_name = _class_name(entity.id)
    eid = entity.id

    return f"""\
# generated/routes/{eid}_crud.py — DO NOT EDIT
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from agentframe.database.session import get_session
from generated.models.{eid}_table import {class_name}Table

router = APIRouter(prefix="/api/{eid}s", tags=["{eid}"])


@router.get("/", response_model=list[{class_name}Table])
def list_{eid}s(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select({class_name}Table).offset(skip).limit(limit)).all()


@router.post("/", response_model={class_name}Table, status_code=201)
def create_{eid}(item: {class_name}Table, session: Session = Depends(get_session)):
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/{{id}}", response_model={class_name}Table)
def get_{eid}(id: int, session: Session = Depends(get_session)):
    obj = session.get({class_name}Table, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.put("/{{id}}", response_model={class_name}Table)
def update_{eid}(id: int, item: {class_name}Table, session: Session = Depends(get_session)):
    existing = session.get({class_name}Table, id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in item.model_dump(exclude_unset=True).items():
        setattr(existing, k, v)
    existing.updated_at = datetime.utcnow()
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


@router.delete("/{{id}}", status_code=204)
def delete_{eid}(id: int, session: Session = Depends(get_session)):
    obj = session.get({class_name}Table, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(obj)
    session.commit()
"""


class CRUDGenerator(BaseGenerator):
    def generate(self, graph: Graph) -> dict[str, str]:
        files: dict[str, str] = {}
        for entity in graph.list_nodes("entity"):
            files[f"models/{entity.id}_table.py"] = _render_table(entity)
            files[f"routes/{entity.id}_crud.py"] = _render_crud_router(entity)
        return files
