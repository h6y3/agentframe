# agentframe/graph/step_schema.py
"""
Step schema normalization and validation for flow nodes.

Supports both legacy string steps and new dict-based steps with types:
- form: User input form
- llm: LLM call step
- display: Result display
"""

from typing import Union

# Step type specifications: required and optional fields
STEP_TYPES = {
    "form": {
        "required": ["name"],
        "optional": ["fields", "validator_fn"],
    },
    "llm": {
        "required": ["name", "integration_ref"],
        "optional": ["system_prompt", "prompt_ref", "tool_schema", "tool_schema_ref", "max_tokens"],
    },
    "display": {
        "required": ["name"],
        "optional": ["template_ref"],
    },
}


def normalize_step(step: Union[str, dict]) -> dict:
    """
    Normalize a step to canonical dict form.

    Legacy string steps become form steps:
        "email_capture" -> {"name": "email_capture", "type": "form", "fields": []}

    Dict steps pass through with defaults applied:
        {"name": "foo", "type": "llm", ...} -> as-is with type defaulting to "form"
    """
    if isinstance(step, str):
        return {"name": step, "type": "form", "fields": []}

    # Ensure type is set (default to form)
    result = dict(step)
    if "type" not in result:
        result["type"] = "form"

    return result


def validate_step(step: dict) -> list[str]:
    """
    Validate a normalized step dict.

    Returns list of error messages (empty if valid).
    """
    errors = []

    step_type = step.get("type", "form")
    step_name = step.get("name", "?")

    if step_type not in STEP_TYPES:
        errors.append(f"Step '{step_name}' has unknown type: {step_type}")
        return errors

    spec = STEP_TYPES[step_type]

    for field in spec["required"]:
        if field not in step:
            errors.append(f"Step '{step_name}' (type={step_type}) missing required field: {field}")

    # Additional validation for specific types
    if step_type == "llm":
        # Must have either system_prompt or prompt_ref
        has_prompt = "system_prompt" in step or "prompt_ref" in step
        if not has_prompt:
            errors.append(f"Step '{step_name}' (type=llm) must have system_prompt or prompt_ref")

    return errors


def normalize_steps(steps: list) -> list[dict]:
    """Normalize a list of steps."""
    return [normalize_step(s) for s in steps]


def validate_steps(steps: list) -> list[str]:
    """Validate a list of steps (normalizes first)."""
    errors = []
    normalized = normalize_steps(steps)
    for step in normalized:
        errors.extend(validate_step(step))
    return errors


def get_step_name(step: Union[str, dict]) -> str:
    """Extract step name from either format."""
    if isinstance(step, str):
        return step
    return step.get("name", "")


def get_step_type(step: Union[str, dict]) -> str:
    """Extract step type from either format."""
    if isinstance(step, str):
        return "form"
    return step.get("type", "form")
