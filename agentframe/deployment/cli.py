import os
import subprocess
import sys
from pathlib import Path

try:
    import typer
except ImportError:
    print("typer not installed. Run: pip install typer")
    sys.exit(1)

app = typer.Typer(help="AgentFrame CLI — manage your app's graph, generators, and deployments.")


def _get_graph_and_engine():
    """Load graph and generator engine from the demo_app (or current project)."""
    from agentframe.graph.store import Graph
    from agentframe.generators.engine import GeneratorEngine
    graph = Graph()
    gen_engine = GeneratorEngine(graph, Path("generated"))
    return graph, gen_engine


@app.command()
def dev():
    """Start the development server (full stack: graph + MCP + console + generated routes)."""
    typer.echo("Starting AgentFrame dev server...")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "demo_app.main:app", "--reload"],
        check=False,
    )


@app.command()
def build():
    """Run all generators and write output to generated/."""
    typer.echo("Running all generators...")
    _, gen_engine = _get_graph_and_engine()
    summary = gen_engine.run_all()
    total = sum(len(v) for v in summary.values())
    for gen_name, files in summary.items():
        typer.echo(f"  {gen_name}: {len(files)} files")
    typer.echo(f"Done. {total} files written to generated/")


@app.command()
def migrate(
    message: str = typer.Option("auto", "--message", "-m", help="Migration message"),
    run: bool = typer.Option(False, "--run", help="Also apply the migration immediately"),
):
    """Generate an Alembic migration for current schema changes."""
    from agentframe.database.migrations import generate_migration, run_pending_migrations

    if not Path("alembic.ini").exists():
        typer.echo("Alembic not initialised. Run `agentframe build` first.")
        raise typer.Exit(1)

    typer.echo(f"Generating migration: '{message}'...")
    try:
        generate_migration(message)
        typer.echo("Migration script created in alembic/versions/")
    except Exception as e:
        typer.echo(f"Error generating migration: {e}", err=True)
        raise typer.Exit(1)

    if run:
        typer.echo("Applying migration...")
        try:
            run_pending_migrations()
            typer.echo("Migration applied.")
        except Exception as e:
            typer.echo(f"Error applying migration: {e}", err=True)
            raise typer.Exit(1)


@app.command()
def deploy(
    target: str = typer.Option(..., "--target", "-t", help="Deployment target: gcp or aws"),
    skip_build: bool = typer.Option(False, "--skip-build", help="Skip generator run"),
    skip_migrate: bool = typer.Option(False, "--skip-migrate", help="Skip migration generation"),
):
    """Build, migrate, and deploy the application.

    Runs: build → generate migration → docker build+push → cloud deploy.
    The container calls alembic upgrade head on startup automatically.
    """
    if target not in ("gcp", "aws"):
        typer.echo(f"Unknown target: {target}. Use --target gcp or --target aws")
        raise typer.Exit(1)

    # Step 1: Build
    if not skip_build:
        typer.echo("Step 1/4: Running generators...")
        _, gen_engine = _get_graph_and_engine()
        gen_engine.run_all()
        typer.echo("  Generators done.")

    # Step 2: Generate migration
    if not skip_migrate and Path("alembic.ini").exists():
        typer.echo("Step 2/4: Generating migration...")
        from agentframe.database.migrations import generate_migration
        try:
            generate_migration("auto")
            typer.echo("  Migration script created.")
        except Exception as e:
            typer.echo(f"  Warning: migration generation failed: {e}")
    else:
        typer.echo("Step 2/4: Skipping migration.")

    # Step 3: Docker build+push
    deploy_script = f"deploy/deploy_{target}.sh"
    if not Path(deploy_script).exists():
        typer.echo(
            f"Deploy script not found: {deploy_script}\n"
            "Run `agentframe build` first, or add a deployment integration node to the graph."
        )
        raise typer.Exit(1)

    typer.echo(f"Step 3/4 + 4/4: Running deploy script for {target}...")
    result = subprocess.run(["bash", deploy_script], check=False)
    if result.returncode != 0:
        typer.echo(f"Deploy script failed with exit code {result.returncode}", err=True)
        raise typer.Exit(result.returncode)

    typer.echo(f"\nDeployment to {target} complete.")
    typer.echo("The container will run 'alembic upgrade head' on startup automatically.")


@app.command("secrets")
def secrets_cmd(
    action: str = typer.Argument(..., help="Action: list | set | delete"),
    secret_id: str = typer.Argument(None, help="Secret ID (required for set and delete)"),
):
    """Manage encrypted secrets in the vault.

    \b
    agentframe secrets list            — show all declared secrets
    agentframe secrets set <id>        — prompt for value and store encrypted
    agentframe secrets delete <id>     — remove a secret from the vault
    """
    from agentframe.secrets.vault import EncryptedVault
    from agentframe.database.connection import get_engine

    engine = get_engine()
    vault = EncryptedVault(engine)

    if action == "list":
        secrets = vault.list_all()
        if not secrets:
            typer.echo("No secrets declared. Secrets are auto-declared by generators.")
            return
        typer.echo(f"{'ID':<30} {'ENV_VAR':<30} {'VALUE SET':<10} DESCRIPTION")
        typer.echo("-" * 80)
        for s in secrets:
            value_set = "✓" if s.encrypted_value is not None else "✗"
            typer.echo(f"{s.id:<30} {s.env_var:<30} {value_set:<10} {s.description}")

    elif action == "set":
        if not secret_id:
            typer.echo("secret_id required for 'set'. Usage: agentframe secrets set <id>")
            raise typer.Exit(1)
        value = typer.prompt(f"Value for '{secret_id}'", hide_input=True)
        try:
            vault.set_value(secret_id, value)
            typer.echo(f"Secret '{secret_id}' stored (encrypted).")
        except KeyError:
            typer.echo(
                f"Secret '{secret_id}' not declared. Generators declare secrets automatically on build."
            )
            raise typer.Exit(1)

    elif action == "delete":
        if not secret_id:
            typer.echo("secret_id required for 'delete'.")
            raise typer.Exit(1)
        vault.delete(secret_id)
        typer.echo(f"Secret '{secret_id}' deleted.")

    else:
        typer.echo(f"Unknown action: {action}. Use list, set, or delete.")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
