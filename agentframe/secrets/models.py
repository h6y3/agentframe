from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON


class SecretNode(SQLModel, table=True):
    __tablename__ = "secret_nodes"
    id: str = Field(primary_key=True)       # e.g. "openai_api_key"
    env_var: str                              # e.g. "OPENAI_API_KEY"
    description: str = ""
    encrypted_value: Optional[str] = None    # Fernet-encrypted; None = not yet set
    required_by: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
