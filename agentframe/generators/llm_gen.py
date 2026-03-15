# agentframe/generators/llm_gen.py
"""
LLM Generator - produces LLM client code and provider adapters.

Triggers on:
- integration nodes with provider_type: "llm"
- flow nodes with steps of type: "llm"

Generates:
- services/llm_client.py - provider-agnostic interface
- services/{provider}_adapter.py - provider-specific implementation
"""

from pathlib import Path
from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph
from agentframe.graph.step_schema import normalize_steps, get_step_type


_LLM_CLIENT_TEMPLATE = '''\
# generated/services/llm_client.py — DO NOT EDIT
"""Provider-agnostic LLM client interface."""

from dataclasses import dataclass
from typing import AsyncIterator, Any
import os

{adapter_imports}


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: dict[str, Any]
    raw_response: Any = None


@dataclass
class LLMConfig:
    """Configuration for an LLM call."""
    provider: str
    model: str
    system_prompt: str
    tool_schema: dict | None = None
    max_tokens: int = 4096


{adapter_instances}


async def call_llm(config: LLMConfig, user_input: str) -> LLMResponse:
    """Make a synchronous LLM call and return structured response."""
    adapter = _get_adapter(config.provider)
    return await adapter.call(config, user_input)


async def stream_llm(config: LLMConfig, user_input: str) -> AsyncIterator[str]:
    """Stream LLM response chunks."""
    adapter = _get_adapter(config.provider)
    async for chunk in adapter.stream(config, user_input):
        yield chunk


def _get_adapter(provider: str):
    """Get the adapter for a provider."""
    adapters = {{{adapter_map}}}
    if provider not in adapters:
        raise ValueError(f"Unknown LLM provider: {{provider}}. Available: {{list(adapters.keys())}}")
    return adapters[provider]
'''


_ANTHROPIC_ADAPTER_TEMPLATE = '''\
# generated/services/anthropic_adapter.py — DO NOT EDIT
"""Anthropic Claude adapter for LLM calls."""

import os
from typing import AsyncIterator, Any

try:
    from anthropic import Anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


class AnthropicAdapter:
    """Adapter for Anthropic's Claude models."""

    def __init__(self, env_var: str = "ANTHROPIC_API_KEY"):
        self.env_var = env_var

    def _get_client(self) -> "Anthropic":
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        api_key = os.environ.get(self.env_var)
        if not api_key:
            raise ValueError(f"{{self.env_var}} environment variable is required")
        return Anthropic(api_key=api_key)

    async def call(self, config, user_input: str) -> Any:
        """Make a synchronous LLM call with tool use for structured output."""
        from services.llm_client import LLMResponse

        client = self._get_client()

        messages = [{"role": "user", "content": user_input}]

        kwargs = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "system": config.system_prompt,
            "messages": messages,
        }

        # If tool schema is provided, use tool calling for structured output
        if config.tool_schema:
            tool = {
                "name": "structured_output",
                "description": "Provide structured output matching the schema",
                "input_schema": config.tool_schema,
            }
            kwargs["tools"] = [tool]
            kwargs["tool_choice"] = {"type": "tool", "name": "structured_output"}

            response = client.messages.create(**kwargs)

            # Extract tool use result
            tool_use = next(
                (block for block in response.content if block.type == "tool_use"),
                None
            )
            if tool_use:
                return LLMResponse(content=tool_use.input, raw_response=response)
            else:
                # Fallback to text content
                text = response.content[0].text if response.content else ""
                return LLMResponse(content={"text": text}, raw_response=response)
        else:
            response = client.messages.create(**kwargs)
            text = response.content[0].text if response.content else ""
            return LLMResponse(content={"text": text}, raw_response=response)

    async def stream(self, config, user_input: str) -> AsyncIterator[str]:
        """Stream LLM response chunks."""
        client = self._get_client()

        messages = [{"role": "user", "content": user_input}]

        with client.messages.stream(
            model=config.model,
            max_tokens=config.max_tokens,
            system=config.system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
'''


_OPENAI_ADAPTER_TEMPLATE = '''\
# generated/services/openai_adapter.py — DO NOT EDIT
"""OpenAI adapter for LLM calls."""

import os
import json
from typing import AsyncIterator, Any

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


class OpenAIAdapter:
    """Adapter for OpenAI models."""

    def __init__(self, env_var: str = "OPENAI_API_KEY"):
        self.env_var = env_var

    def _get_client(self) -> "OpenAI":
        if not _OPENAI_AVAILABLE:
            raise ImportError("openai package not installed. Run: pip install openai")
        api_key = os.environ.get(self.env_var)
        if not api_key:
            raise ValueError(f"{{self.env_var}} environment variable is required")
        return OpenAI(api_key=api_key)

    async def call(self, config, user_input: str) -> Any:
        """Make a synchronous LLM call with function calling for structured output."""
        from services.llm_client import LLMResponse

        client = self._get_client()

        messages = [
            {"role": "system", "content": config.system_prompt},
            {"role": "user", "content": user_input},
        ]

        kwargs = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": messages,
        }

        # If tool schema is provided, use function calling
        if config.tool_schema:
            function = {
                "name": "structured_output",
                "description": "Provide structured output matching the schema",
                "parameters": config.tool_schema,
            }
            kwargs["tools"] = [{"type": "function", "function": function}]
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "structured_output"}}

            response = client.chat.completions.create(**kwargs)

            # Extract function call result
            if response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                content = json.loads(tool_call.function.arguments)
                return LLMResponse(content=content, raw_response=response)
            else:
                text = response.choices[0].message.content or ""
                return LLMResponse(content={"text": text}, raw_response=response)
        else:
            response = client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
            return LLMResponse(content={"text": text}, raw_response=response)

    async def stream(self, config, user_input: str) -> AsyncIterator[str]:
        """Stream LLM response chunks."""
        client = self._get_client()

        messages = [
            {"role": "system", "content": config.system_prompt},
            {"role": "user", "content": user_input},
        ]

        stream = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=messages,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
'''


def _get_llm_integrations(graph: Graph) -> list:
    """Find all integration nodes with provider_type: llm."""
    return [
        n for n in graph.list_nodes("integration")
        if n.attrs.get("provider_type") == "llm"
    ]


def _flows_use_llm(graph: Graph) -> bool:
    """Check if any flow has an LLM step."""
    for flow in graph.list_nodes("flow"):
        steps = flow.attrs.get("steps", [])
        normalized = normalize_steps(steps)
        if any(get_step_type(s) == "llm" for s in normalized):
            return True
    return False


class LLMGenerator(BaseGenerator):
    """
    Generates LLM client and provider adapters.

    Only generates files if there are LLM integrations or LLM steps in flows.
    """

    output_dir = Path("services")

    def generate(self, graph: Graph) -> dict[str, str]:
        files: dict[str, str] = {}

        llm_integrations = _get_llm_integrations(graph)
        has_llm_flows = _flows_use_llm(graph)

        # Only generate if there are LLM integrations or LLM steps
        if not llm_integrations and not has_llm_flows:
            return files

        # Collect unique providers
        providers = set()
        for integration in llm_integrations:
            provider = integration.attrs.get("provider", "").lower()
            if provider:
                providers.add(provider)

        # Also check flow steps for integration refs
        for flow in graph.list_nodes("flow"):
            steps = flow.attrs.get("steps", [])
            for step in normalize_steps(steps):
                if get_step_type(step) == "llm":
                    ref = step.get("integration_ref")
                    if ref:
                        integration = graph.get_node(ref)
                        if integration:
                            provider = integration.attrs.get("provider", "").lower()
                            if provider:
                                providers.add(provider)

        # Generate provider-specific adapters
        adapter_imports = []
        adapter_instances = []
        adapter_map_items = []

        if "anthropic" in providers:
            files["services/anthropic_adapter.py"] = _ANTHROPIC_ADAPTER_TEMPLATE
            adapter_imports.append("from services.anthropic_adapter import AnthropicAdapter")
            # Find the env_var for anthropic
            env_var = "ANTHROPIC_API_KEY"
            for integration in llm_integrations:
                if integration.attrs.get("provider", "").lower() == "anthropic":
                    env_var = integration.attrs.get("env_var", env_var)
                    break
            adapter_instances.append(f'_anthropic_adapter = AnthropicAdapter(env_var="{env_var}")')
            adapter_map_items.append('"anthropic": _anthropic_adapter')

        if "openai" in providers:
            files["services/openai_adapter.py"] = _OPENAI_ADAPTER_TEMPLATE
            adapter_imports.append("from services.openai_adapter import OpenAIAdapter")
            env_var = "OPENAI_API_KEY"
            for integration in llm_integrations:
                if integration.attrs.get("provider", "").lower() == "openai":
                    env_var = integration.attrs.get("env_var", env_var)
                    break
            adapter_instances.append(f'_openai_adapter = OpenAIAdapter(env_var="{env_var}")')
            adapter_map_items.append('"openai": _openai_adapter')

        # Generate main client file
        client_content = _LLM_CLIENT_TEMPLATE.format(
            adapter_imports="\n".join(adapter_imports) if adapter_imports else "# No adapters configured",
            adapter_instances="\n".join(adapter_instances) if adapter_instances else "# No adapters configured",
            adapter_map=", ".join(adapter_map_items) if adapter_map_items else "",
        )
        files["services/llm_client.py"] = client_content

        return files
