import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI

from agentframe.graph.store import Graph
from agentframe.generators.engine import GeneratorEngine
from agentframe.runtime.executor import Executor
from agentframe.protocol.server import router as mcp_router, set_graph
from agentframe.console.router import router as console_router, set_dependencies
from agentframe.secrets.vault import EncryptedVault

app = FastAPI(title="AgentFrame Demo")

# Core objects
graph = Graph()
gen_engine = GeneratorEngine(graph, Path("generated"))
executor = Executor(graph, gen_engine)
vault = EncryptedVault(graph.engine)

# Wire dependencies
set_graph(graph)
set_dependencies(graph, executor, gen_engine, vault=vault)

# Mount sub-apps
app.include_router(mcp_router)
app.include_router(console_router)


def _load_generated_routes():
    generated_routes = Path("generated/routes")
    if not generated_routes.exists():
        return
    for route_file in sorted(generated_routes.glob("*.py")):
        module_name = f"_generated_route_{route_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, route_file)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"Warning: failed to load {route_file}: {e}")
            continue
        if hasattr(mod, "router"):
            app.include_router(mod.router)


@app.on_event("startup")
async def startup():
    gen_engine.run_all()
    _load_generated_routes()


@app.get("/")
async def index():
    return {
        "status": "AgentFrame running",
        "console": "/_console",
        "mcp_tools": "/mcp/tools",
    }
