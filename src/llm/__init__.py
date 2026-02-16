"""
LLM module - Abstractions for Large Language Model interactions.

Provides a unified interface for different LLM providers:
- AWS Bedrock (Claude)
- Mock (for testing)
"""

from .base import (
    BaseLLMClient,
    LLMConfig,
    LLMResponse,
    LLMMessage,
)
from .bedrock_client import BedrockClient
from .mock_client import MockLLMClient, JSONMockLLMClient

__all__ = [
    # Base classes
    'BaseLLMClient',
    'LLMConfig',
    'LLMResponse',
    'LLMMessage',
    # Implementations
    'BedrockClient',
    'MockLLMClient',
    'JSONMockLLMClient',
]


def create_client(provider: str = "bedrock", **kwargs) -> BaseLLMClient:
    """
    Factory function to create an LLM client.

    Args:
        provider: Provider name ("bedrock", "mock", "json_mock")
        **kwargs: Provider-specific configuration

    Returns:
        Configured LLM client instance

    Raises:
        ValueError: If provider is not supported
    """
    providers = {
        "bedrock": BedrockClient,
        "mock": MockLLMClient,
        "json_mock": JSONMockLLMClient,
    }

    if provider not in providers:
        raise ValueError(f"Unsupported provider: {provider}. Available: {list(providers.keys())}")

    return providers[provider](**kwargs)
