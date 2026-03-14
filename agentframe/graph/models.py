from datetime import datetime
from typing import Optional, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON


class Node(SQLModel, table=True):
    """Single table for all node types, discriminated by node_type."""

    __tablename__ = "nodes"

    id: str = Field(primary_key=True)
    node_type: str  # "entity", "flow", "page", "policy", "widget"
    label: str
    attrs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GraphEvent(SQLModel, table=True):
    """Append-only event log for all graph mutations."""

    __tablename__ = "graph_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_type: str  # "ADD_NODE", "UPDATE_NODE", "REMOVE_NODE"
    node_id: str
    node_type: str
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    proposal_id: Optional[str] = Field(default=None)
