from typing import Generator
from sqlmodel import Session
from agentframe.database.connection import get_app_engine


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends() target — yields a SQLModel Session for app data tables."""
    with Session(get_app_engine()) as session:
        yield session
