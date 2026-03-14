"""
Demo: Agent adds a password reset flow via the MCP protocol.
Run this while the server is running:
    python demo_app/demo_agent.py
"""
import httpx
import json

BASE = "http://localhost:8000/mcp"


def run():
    print("=== AgentFrame POC Demo ===\n")

    # Step 1: Agent discovers available tools
    r = httpx.get(f"{BASE}/tools")
    r.raise_for_status()
    print(f"[1] Available tools: {[t['name'] for t in r.json()]}\n")

    # Step 2: Agent explores the graph
    r = httpx.post(f"{BASE}/graph/list", json={"node_type": "flow"})
    r.raise_for_status()
    flows = r.json()
    print(f"[2] Existing flows: {[f['id'] for f in flows]}\n")

    # Step 3: Agent queries for context
    r = httpx.post(f"{BASE}/graph/query", json={"q": "user entity"})
    r.raise_for_status()
    results = r.json()
    print(f"[3] User entity found: {results[0]['id'] if results else 'not found'}\n")

    # Step 4: Agent proposes adding a password reset flow
    patch = {
        "op": "add",
        "node_type": "flow",
        "node_id": "password_reset",
        "label": "Password Reset",
        "attrs": {
            "steps": ["email_lookup", "send_token", "new_password", "confirm"],
            "entity_refs": ["user"],
        },
    }
    r = httpx.post(f"{BASE}/graph/patch", json=patch)
    r.raise_for_status()
    result = r.json()
    proposal_id = result["proposal_id"]
    print(f"[4] Patch proposal created: {proposal_id}")
    print(f"    Status: {result['status']}\n")

    # Step 5: Agent simulates the change
    r = httpx.post(f"{BASE}/graph/simulate", json={"proposal_id": proposal_id})
    r.raise_for_status()
    print(f"[5] Simulation preview:\n{r.json()['preview']}\n")

    # Step 6: Agent explains the user node
    r = httpx.post(f"{BASE}/graph/explain", json={"node_id": "user"})
    r.raise_for_status()
    explain = r.json()
    print(f"[6] User node has {len(explain['dependents'])} dependent(s)\n")

    # Step 7: Show all pending proposals
    r = httpx.get(f"{BASE}/proposals")
    r.raise_for_status()
    pending = [p for p in r.json() if p["status"] == "pending"]
    print(f"[7] Pending proposals: {len(pending)}\n")

    print("=== Done ===")
    print("Open http://localhost:8000/_console/proposals to approve the change.")
    print(f"Direct link: http://localhost:8000/_console/proposals/{proposal_id}")


if __name__ == "__main__":
    run()
