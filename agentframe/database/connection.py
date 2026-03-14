import os
from sqlalchemy import Engine
from sqlmodel import create_engine


def get_engine(db_url: str | None = None) -> Engine:
    """Create an engine for the given URL (or DATABASE_URL env, or SQLite default)."""
    url = db_url or os.environ.get("DATABASE_URL", "sqlite:///./agentframe.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs: dict = {"pool_pre_ping": True} if "postgresql" in url else {}
    return create_engine(url, connect_args=connect_args, **kwargs)


def get_app_engine() -> Engine:
    """Engine for app data tables (user entities, etc.).

    Reads APP_DATABASE_URL first, falls back to DATABASE_URL, then SQLite.
    """
    url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    return get_engine(url)
