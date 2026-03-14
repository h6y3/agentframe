from dataclasses import dataclass
from typing import Callable


@dataclass
class PolicyResult:
    passed: bool
    rule: str
    reason: str = ""
    severity: str = "error"  # "error" | "warn"

    @classmethod
    def pass_(cls, rule: str) -> "PolicyResult":
        return cls(passed=True, rule=rule)

    @classmethod
    def fail(cls, rule: str, reason: str, severity: str = "error") -> "PolicyResult":
        return cls(passed=False, rule=rule, reason=reason, severity=severity)


# Registry
_policies: list[Callable] = []


def policy(name: str):
    """Decorator to register a policy function."""
    def decorator(fn):
        fn._policy_name = name
        _policies.append(fn)
        return fn
    return decorator


def get_all_policies() -> list[Callable]:
    return _policies
