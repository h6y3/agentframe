import os


def run_pending_migrations(alembic_cfg_path: str = "alembic.ini") -> None:
    """Run alembic upgrade head programmatically.

    Called on app startup in production (via main_prod.py lifespan handler).
    Safe to call even when no pending migrations exist.
    """
    if not os.path.exists(alembic_cfg_path):
        return  # Alembic not yet set up — skip silently
    from alembic import command
    from alembic.config import Config
    cfg = Config(alembic_cfg_path)
    command.upgrade(cfg, "head")


def generate_migration(message: str, alembic_cfg_path: str = "alembic.ini") -> None:
    """Auto-generate a migration script based on current model state.

    Called by `agentframe migrate` and the deploy pipeline.
    Requires alembic project to be initialised first (MigrationGenerator).
    """
    from alembic import command
    from alembic.config import Config
    cfg = Config(alembic_cfg_path)
    command.revision(cfg, autogenerate=True, message=message)
