"""
Node Builders - Specialized builders for each INSAIT node type.

Each builder encapsulates the logic for creating a specific node type
with proper defaults, validation, and INSAIT-specific configurations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...utils.id_generator import generate_uuid
from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NodeConfig:
    """Base configuration for node creation."""
    name: str
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNodeBuilder(ABC):
    """Abstract base class for node builders."""

    @property
    @abstractmethod
    def node_type(self) -> str:
        """Return the node type identifier."""
        pass

    @abstractmethod
    def build(self, config: NodeConfig, **kwargs) -> Dict[str, Any]:
        """Build the node JSON."""
        pass

    def _create_base_node(self, config: NodeConfig) -> Dict[str, Any]:
        """Create base node structure common to all nodes."""
        return {
            "id": generate_uuid(),
            "type": self.node_type,
            "name": config.name,
            "position": config.position,
            "data": {},
        }


class StartNodeBuilder(BaseNodeBuilder):
    """Builder for start nodes."""

    @property
    def node_type(self) -> str:
        return "start"

    def build(
        self,
        config: NodeConfig,
        initial_message: str = "",
        system_prompt: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build a start node.

        Args:
            config: Base node configuration
            initial_message: Message to display when conversation starts
            system_prompt: System prompt for the agent

        Returns:
            Start node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "initial_message": initial_message,
            "system_prompt": system_prompt,
        }
        return node


class EndNodeBuilder(BaseNodeBuilder):
    """Builder for end nodes."""

    @property
    def node_type(self) -> str:
        return "end"

    def build(
        self,
        config: NodeConfig,
        end_type: str = "end_call",
        message: str = "",
        transfer_target: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build an end node.

        Args:
            config: Base node configuration
            end_type: Type of ending (end_call, transfer, voicemail)
            message: Final message to user
            transfer_target: Target for transfer (if applicable)

        Returns:
            End node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "end_type": end_type,
            "message": message,
        }

        if transfer_target:
            node["data"]["transfer_target"] = transfer_target

        return node


class CollectNodeBuilder(BaseNodeBuilder):
    """Builder for collect nodes (gather user input)."""

    @property
    def node_type(self) -> str:
        return "collect"

    def build(
        self,
        config: NodeConfig,
        variable_name: str,
        prompt: str,
        variable_type: str = "string",
        validation: Optional[Dict[str, Any]] = None,
        options: Optional[List[str]] = None,
        retry_count: int = 3,
        retry_message: str = "",
        timeout_seconds: int = 30,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build a collect node.

        Args:
            config: Base node configuration
            variable_name: Variable to store collected value
            prompt: Prompt message to user
            variable_type: Type of variable (string, number, boolean)
            validation: Validation rules
            options: List of valid options (for selection)
            retry_count: Number of retries on invalid input
            retry_message: Message on invalid input
            timeout_seconds: Input timeout

        Returns:
            Collect node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "variable_name": variable_name,
            "variable_type": variable_type,
            "prompt": prompt,
            "validation": validation or {},
            "options": options or [],
            "retry_count": retry_count,
            "retry_message": retry_message,
            "timeout_seconds": timeout_seconds,
        }
        return node


class ConversationNodeBuilder(BaseNodeBuilder):
    """Builder for conversation nodes (AI responses)."""

    @property
    def node_type(self) -> str:
        return "conversation"

    def build(
        self,
        config: NodeConfig,
        message: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 500,
        allow_interruption: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build a conversation node.

        Args:
            config: Base node configuration
            message: Message template (can include {{variables}})
            system_prompt: Optional system prompt override
            temperature: LLM temperature for response generation
            max_tokens: Maximum tokens in response
            allow_interruption: Whether user can interrupt

        Returns:
            Conversation node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "message": message,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "allow_interruption": allow_interruption,
        }
        return node


class APINodeBuilder(BaseNodeBuilder):
    """Builder for API nodes (external service calls)."""

    @property
    def node_type(self) -> str:
        return "api"

    def build(
        self,
        config: NodeConfig,
        tool_id: str,
        parameters: Optional[Dict[str, str]] = None,
        extractions: Optional[List[Dict[str, str]]] = None,
        timeout_seconds: int = 30,
        retry_count: int = 1,
        error_handling: str = "continue",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build an API node.

        Args:
            config: Base node configuration
            tool_id: ID of the tool to call
            parameters: Parameter mappings {param_name: variable_or_value}
            extractions: Response extraction rules
            timeout_seconds: API call timeout
            retry_count: Number of retries on failure
            error_handling: How to handle errors (continue, abort, retry)

        Returns:
            API node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "tool_id": tool_id,
            "parameters": parameters or {},
            "extractions": extractions or [],
            "timeout_seconds": timeout_seconds,
            "retry_count": retry_count,
            "error_handling": error_handling,
        }
        return node


class ConditionNodeBuilder(BaseNodeBuilder):
    """Builder for condition nodes (branching logic)."""

    @property
    def node_type(self) -> str:
        return "condition"

    def build(
        self,
        config: NodeConfig,
        conditions: List[Dict[str, Any]],
        default_exit: str = "else",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build a condition node.

        Args:
            config: Base node configuration
            conditions: List of condition rules
            default_exit: Name of default/else exit

        Condition format:
            {
                "expression": "{{variable}} == 'value'",
                "exit_name": "Exit name for this branch",
                "priority": 1
            }

        Returns:
            Condition node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "conditions": conditions,
            "default_exit": default_exit,
        }
        return node


class SetVariablesNodeBuilder(BaseNodeBuilder):
    """Builder for set_variables nodes."""

    @property
    def node_type(self) -> str:
        return "set_variables"

    def build(
        self,
        config: NodeConfig,
        assignments: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build a set_variables node.

        Args:
            config: Base node configuration
            assignments: Variable assignments {name: value}

        Returns:
            Set variables node JSON
        """
        node = self._create_base_node(config)
        node["data"] = {
            "assignments": [
                {"variable": k, "value": v}
                for k, v in assignments.items()
            ],
        }
        return node


# Builder registry
_BUILDERS: Dict[str, BaseNodeBuilder] = {
    "start": StartNodeBuilder(),
    "end": EndNodeBuilder(),
    "collect": CollectNodeBuilder(),
    "conversation": ConversationNodeBuilder(),
    "api": APINodeBuilder(),
    "condition": ConditionNodeBuilder(),
    "set_variables": SetVariablesNodeBuilder(),
}


def get_builder(node_type: str) -> BaseNodeBuilder:
    """
    Get the appropriate builder for a node type.

    Args:
        node_type: Type of node to build

    Returns:
        Builder instance for the node type

    Raises:
        ValueError: If node type is not supported
    """
    builder = _BUILDERS.get(node_type)
    if not builder:
        raise ValueError(f"Unknown node type: {node_type}. Available: {list(_BUILDERS.keys())}")
    return builder


def build_node(node_type: str, config: NodeConfig, **kwargs) -> Dict[str, Any]:
    """
    Build a node of the specified type.

    Args:
        node_type: Type of node to build
        config: Node configuration
        **kwargs: Type-specific parameters

    Returns:
        Node JSON
    """
    builder = get_builder(node_type)
    return builder.build(config, **kwargs)
