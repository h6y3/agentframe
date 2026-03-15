from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON


class ProposalStatus(str, Enum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class PatchProposal(SQLModel, table=True):
    __tablename__ = "patch_proposals"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    op: str  # "add", "update", "remove"
    node_type: str
    node_id: str
    attrs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    label: Optional[str] = Field(default=None)
    intent: Optional[str] = Field(default=None)  # Why this change is being made
    status: ProposalStatus = Field(default=ProposalStatus.PENDING)
    policy_results: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(default=None)
    resolved_by: str = Field(default="pending")  # "auto" | "human:approve" | "human:reject"
