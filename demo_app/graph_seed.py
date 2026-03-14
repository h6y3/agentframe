import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentframe.graph.store import Graph


def seed(graph: Graph):
    # Entities
    graph.add_node(
        "entity",
        "user",
        "User",
        attrs={
            "fields": [
                {"name": "email", "type": "str", "pii": True, "required": True},
                {"name": "name", "type": "str", "pii": False, "required": True},
                {"name": "role", "type": "str", "pii": False, "required": False},
            ],
            "requires_auth": True,
        },
    )
    graph.add_node(
        "entity",
        "plan",
        "Subscription Plan",
        attrs={
            "fields": [
                {"name": "name", "type": "str", "pii": False, "required": True},
                {"name": "price", "type": "float", "pii": False, "required": True},
            ],
            "requires_auth": False,
        },
    )

    # Flows
    graph.add_node(
        "flow",
        "signup",
        "Sign Up",
        attrs={
            "steps": ["email_capture", "plan_select", "confirm"],
            "entity_refs": ["user", "plan"],
        },
    )
    graph.add_node(
        "flow",
        "login",
        "Log In",
        attrs={
            "steps": ["credentials", "mfa"],
            "entity_refs": ["user"],
        },
    )

    # Pages
    graph.add_node(
        "page",
        "dashboard",
        "Dashboard",
        attrs={
            "widgets": ["activity_feed", "usage_chart", "quick_actions"],
            "requires_auth": True,
            "entity_refs": ["user"],
        },
    )
    graph.add_node(
        "page",
        "pricing",
        "Pricing",
        attrs={
            "widgets": ["plan_cards", "faq"],
            "requires_auth": False,
            "entity_refs": ["plan"],
        },
    )

    # Policies (metadata — actual enforcement is in policy functions)
    graph.add_node(
        "policy",
        "no_public_pii",
        "No Public PII",
        attrs={
            "rule_fn": "agentframe.policies.builtin.no_public_pii.check",
            "severity": "error",
        },
    )

    # Auth integrations
    graph.add_node(
        "integration",
        "google_auth",
        "Google Login",
        attrs={
            "provider": "google_oauth",
            "scopes": ["openid", "email", "profile"],
        },
    )
    graph.add_node(
        "integration",
        "email_auth",
        "Email Magic Link",
        attrs={
            "provider": "email_magic_link",
            "from_email": "noreply@example.com",
        },
    )

    # Deployment targets (uncomment and configure for your environment)
    # graph.add_node(
    #     "integration",
    #     "deploy_gcp",
    #     "Deploy: GCP Cloud Run",
    #     attrs={
    #         "provider": "gcp_cloudrun",
    #         "project_id": "my-gcp-project",
    #         "region": "us-central1",
    #     },
    # )
    # graph.add_node(
    #     "integration",
    #     "deploy_aws",
    #     "Deploy: AWS App Runner",
    #     attrs={
    #         "provider": "aws_apprunner",
    #         "region": "us-east-1",
    #     },
    # )


if __name__ == "__main__":
    g = Graph()
    seed(g)
    print("Graph seeded.")
