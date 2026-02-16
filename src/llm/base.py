"""
Abstract base class for LLM clients.

Defines the interface that all LLM providers must implement,
enabling easy swapping between providers (Bedrock, OpenAI, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Iterator, Dict, Any, List


@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # "user", "assistant", or "system"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    success: bool = True
    error_message: Optional[str] = None

    # Token usage
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # Model info
    model_id: Optional[str] = None
    finish_reason: Optional[str] = None  # "end_turn", "max_tokens", "stop_sequence"

    # Raw response for debugging
    raw_response: Optional[Dict[str, Any]] = None

    @classmethod
    def error(cls, message: str) -> 'LLMResponse':
        """Create an error response."""
        return cls(content="", success=False, error_message=message)

    @property
    def token_usage(self) -> Dict[str, Optional[int]]:
        """Get token usage as a dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMConfig:
    """Configuration for LLM calls."""
    model_id: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 64000
    timeout: int = 300  # seconds
    stop_sequences: List[str] = field(default_factory=list)

    # Retry settings
    max_retries: int = 2
    retry_delay: float = 1.0


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.

    All LLM provider implementations must inherit from this class
    and implement the required methods.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize the LLM client.

        Args:
            config: LLM configuration (uses defaults if None)
        """
        self.config = config or LLMConfig()

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            prompt: The user prompt/message
            system_prompt: Optional system instructions
            **kwargs: Additional provider-specific options

        Returns:
            LLMResponse with generated content or error
        """
        pass

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Generate a streaming response from the LLM.

        Args:
            prompt: The user prompt/message
            system_prompt: Optional system instructions
            **kwargs: Additional provider-specific options

        Yields:
            Text chunks as they arrive
        """
        pass

    def chat(
        self,
        messages: List[LLMMessage],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Multi-turn chat with the LLM.

        Default implementation converts messages to a single prompt.
        Override for providers with native multi-turn support.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system instructions
            **kwargs: Additional provider-specific options

        Returns:
            LLMResponse with generated content or error
        """
        # Default: concatenate messages into a single prompt
        prompt_parts = []
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}")

        prompt = "\n\n".join(prompt_parts)
        if messages and messages[-1].role == "user":
            prompt += "\n\nAssistant:"

        return self.generate(prompt, system_prompt=system_prompt, **kwargs)

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the LLM service is available.

        Returns:
            True if service is reachable and credentials are valid
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name (e.g., 'bedrock', 'openai')."""
        pass

    @property
    def model_id(self) -> str:
        """Get the configured model ID."""
        return self.config.model_id or "default"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_id})"
