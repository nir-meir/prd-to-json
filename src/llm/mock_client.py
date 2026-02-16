"""
Mock LLM Client for testing.

Provides configurable mock responses without making actual API calls.
"""

from typing import Optional, Iterator, List, Dict, Callable, Any
import time
import json

from .base import BaseLLMClient, LLMConfig, LLMResponse


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for testing.

    Can be configured with:
    - Static responses
    - Response sequences
    - Custom response functions
    - Simulated delays
    - Error simulation
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        default_response: str = "This is a mock response.",
        delay: float = 0.0,
    ):
        """
        Initialize the mock client.

        Args:
            config: LLM configuration
            default_response: Default response when no specific response is set
            delay: Simulated delay in seconds
        """
        super().__init__(config)
        self.default_response = default_response
        self.delay = delay

        # Response configuration
        self._responses: List[str] = []
        self._response_index = 0
        self._response_function: Optional[Callable[[str], str]] = None
        self._error_after: Optional[int] = None  # Fail after N calls
        self._call_count = 0

        # Call tracking
        self.calls: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def set_responses(self, responses: List[str]) -> None:
        """
        Set a sequence of responses to return.

        Responses are returned in order, then cycle back to the beginning.

        Args:
            responses: List of response strings
        """
        self._responses = responses
        self._response_index = 0

    def set_response_function(self, func: Callable[[str], str]) -> None:
        """
        Set a function to generate responses.

        The function receives the prompt and returns the response.

        Args:
            func: Response generator function
        """
        self._response_function = func

    def set_error_after(self, n: int) -> None:
        """
        Configure to return an error after N successful calls.

        Args:
            n: Number of successful calls before error
        """
        self._error_after = n

    def reset(self) -> None:
        """Reset call tracking and response index."""
        self._response_index = 0
        self._call_count = 0
        self.calls.clear()

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a mock response.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            **kwargs: Additional options (ignored)

        Returns:
            LLMResponse with mock content or simulated error
        """
        # Track the call
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "kwargs": kwargs,
        })

        # Simulate delay
        if self.delay > 0:
            time.sleep(self.delay)

        self._call_count += 1

        # Check for simulated error
        if self._error_after is not None and self._call_count > self._error_after:
            return LLMResponse.error("Simulated error after N calls")

        # Generate response
        if self._response_function:
            content = self._response_function(prompt)
        elif self._responses:
            content = self._responses[self._response_index % len(self._responses)]
            self._response_index += 1
        else:
            content = self.default_response

        # Estimate tokens (rough approximation)
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(content.split()) * 1.3

        return LLMResponse(
            content=content,
            success=True,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            total_tokens=int(input_tokens + output_tokens),
            model_id="mock-model",
            finish_reason="end_turn",
        )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Generate a mock streaming response.

        Yields the response word by word with optional delay.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            **kwargs: Additional options

        Yields:
            Text chunks (words)
        """
        response = self.generate(prompt, system_prompt, **kwargs)

        if not response.success:
            raise RuntimeError(response.error_message)

        # Stream word by word
        words = response.content.split()
        for i, word in enumerate(words):
            if self.delay > 0:
                time.sleep(self.delay / len(words))

            # Add space before word (except first)
            if i > 0:
                yield " "
            yield word

    def is_available(self) -> bool:
        """Mock is always available."""
        return True

    @property
    def last_call(self) -> Optional[Dict[str, Any]]:
        """Get the most recent call."""
        return self.calls[-1] if self.calls else None

    @property
    def call_count(self) -> int:
        """Get total number of calls."""
        return len(self.calls)


class JSONMockLLMClient(MockLLMClient):
    """
    Mock LLM client specialized for JSON generation testing.

    Automatically wraps responses in valid JSON format.
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        json_response: Optional[Dict[str, Any]] = None,
        delay: float = 0.0,
    ):
        """
        Initialize the JSON mock client.

        Args:
            config: LLM configuration
            json_response: JSON object to return
            delay: Simulated delay
        """
        super().__init__(config, delay=delay)
        self._json_responses: List[Dict[str, Any]] = []
        if json_response:
            self._json_responses.append(json_response)

    def set_json_responses(self, responses: List[Dict[str, Any]]) -> None:
        """
        Set JSON responses to return.

        Args:
            responses: List of JSON objects
        """
        self._json_responses = responses
        self._response_index = 0

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate a mock JSON response."""
        # Track the call
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "kwargs": kwargs,
        })

        if self.delay > 0:
            time.sleep(self.delay)

        self._call_count += 1

        if self._error_after is not None and self._call_count > self._error_after:
            return LLMResponse.error("Simulated error")

        # Get JSON response
        if self._json_responses:
            json_obj = self._json_responses[self._response_index % len(self._json_responses)]
            self._response_index += 1
            content = json.dumps(json_obj, indent=2)
        else:
            # Return minimal valid INSAIT JSON
            content = json.dumps({
                "metadata": {
                    "export_version": "1.1",
                    "validation_status": "success"
                },
                "agent": {"name": "Mock Agent"},
                "flow_definition": {
                    "flow": {
                        "start_node_id": "start-node",
                        "nodes": {},
                        "exits": []
                    }
                },
                "tools": []
            }, indent=2)

        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(content.split()) * 1.3

        return LLMResponse(
            content=content,
            success=True,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            total_tokens=int(input_tokens + output_tokens),
            model_id="mock-json-model",
            finish_reason="end_turn",
        )
