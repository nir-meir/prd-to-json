"""
Node Factory - Factory for creating INSAIT JSON nodes.

Provides a centralized way to create different node types with
proper ID generation, positioning, and default values.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..core.context import GenerationContext
from ..utils.id_generator import generate_uuid, generate_node_id
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NodeType(Enum):
    """INSAIT node types."""
    START = "start"
    END = "end"
    COLLECT = "collect"
    CONVERSATION = "conversation"
    API = "api"
    CONDITION = "condition"
    SET_VARIABLES = "set_variables"


@dataclass
class NodePosition:
    """Position of a node in the canvas."""
    x: float
    y: float

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}


class NodeFactory:
    """
    Factory for creating INSAIT-compatible nodes.

    Handles:
    - UUID generation
    - Node ID formatting
    - Position calculation
    - Default value injection
    """

    # Node spacing constants
    HORIZONTAL_SPACING = 300
    VERTICAL_SPACING = 200
    START_X = 100
    START_Y = 100

    def __init__(self, context: GenerationContext):
        """
        Initialize the node factory.

        Args:
            context: Generation context for tracking nodes
        """
        self.context = context
        self._row = 0
        self._col = 0
        self._max_col = 0

    def create_start_node(
        self,
        name: str = "Start",
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create a start node.

        Args:
            name: Node name
            position: Optional position override

        Returns:
            Start node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.START.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "initial_message": "",
                "system_prompt": "",
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created start node: {name}")
        return node

    def create_end_node(
        self,
        name: str = "End",
        end_type: str = "end_call",
        message: str = "",
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create an end node.

        Args:
            name: Node name
            end_type: Type of ending (end_call, transfer, etc.)
            message: Ending message
            position: Optional position override

        Returns:
            End node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.END.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "end_type": end_type,
                "message": message,
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created end node: {name}")
        return node

    def create_collect_node(
        self,
        name: str,
        variable_name: str,
        prompt: str,
        validation: Optional[Dict[str, Any]] = None,
        options: Optional[List[str]] = None,
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create a collect node for gathering user input.

        Args:
            name: Node name
            variable_name: Variable to store collected value
            prompt: Prompt message to user
            validation: Optional validation rules
            options: Optional list of valid options
            position: Optional position override

        Returns:
            Collect node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.COLLECT.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "variable_name": variable_name,
                "prompt": prompt,
                "validation": validation or {},
                "options": options or [],
                "retry_count": 3,
                "retry_message": "",
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created collect node: {name} -> {variable_name}")
        return node

    def create_conversation_node(
        self,
        name: str,
        message: str,
        system_prompt: Optional[str] = None,
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create a conversation node for AI responses.

        Args:
            name: Node name
            message: Message template (can include {{variables}})
            system_prompt: Optional system prompt for this node
            position: Optional position override

        Returns:
            Conversation node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.CONVERSATION.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "message": message,
                "system_prompt": system_prompt or "",
                "temperature": 0.7,
                "max_tokens": 500,
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created conversation node: {name}")
        return node

    def create_api_node(
        self,
        name: str,
        tool_id: str,
        parameters: Optional[Dict[str, str]] = None,
        extractions: Optional[List[Dict[str, str]]] = None,
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create an API node for external service calls.

        Args:
            name: Node name
            tool_id: ID of the tool to call
            parameters: Parameter mappings {param_name: variable_or_value}
            extractions: Response extraction rules
            position: Optional position override

        Returns:
            API node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.API.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "tool_id": tool_id,
                "parameters": parameters or {},
                "extractions": extractions or [],
                "timeout": 30,
                "retry_count": 1,
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created API node: {name} -> {tool_id}")
        return node

    def create_condition_node(
        self,
        name: str,
        conditions: List[Dict[str, Any]],
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create a condition node for branching logic.

        Args:
            name: Node name
            conditions: List of condition rules with exits
            position: Optional position override

        Returns:
            Condition node JSON

        Condition format:
            {
                "expression": "{{variable}} == 'value'",
                "exit_name": "Exit name for this branch"
            }
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.CONDITION.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "conditions": conditions,
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created condition node: {name}")
        return node

    def create_set_variables_node(
        self,
        name: str,
        assignments: Dict[str, Any],
        position: Optional[NodePosition] = None,
    ) -> Dict[str, Any]:
        """
        Create a set_variables node for setting variable values.

        Args:
            name: Node name
            assignments: Variable assignments {name: value}
            position: Optional position override

        Returns:
            Set variables node JSON
        """
        node_id = generate_uuid()
        pos = position or self._next_position()

        node = {
            "id": node_id,
            "type": NodeType.SET_VARIABLES.value,
            "name": name,
            "position": pos.to_dict(),
            "data": {
                "assignments": [
                    {"variable": k, "value": v}
                    for k, v in assignments.items()
                ],
            },
        }

        self.context.register_node(node)
        logger.debug(f"Created set_variables node: {name}")
        return node

    def create_exit(
        self,
        source_node_id: str,
        target_node_id: str,
        name: str = "default",
        condition: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an exit (edge) between nodes.

        Args:
            source_node_id: Source node UUID
            target_node_id: Target node UUID
            name: Exit name (e.g., "success", "failure", "default")
            condition: Optional condition expression

        Returns:
            Exit JSON
        """
        exit_id = generate_uuid()

        exit_data = {
            "id": exit_id,
            "source": source_node_id,
            "target": target_node_id,
            "name": name,
            "condition": condition,
        }

        self.context.add_exit(source_node_id, target_node_id, name)
        logger.debug(f"Created exit: {name} ({source_node_id[:8]}... -> {target_node_id[:8]}...)")
        return exit_data

    def create_tool(
        self,
        name: str,
        function_name: str,
        description: str,
        method: str = "POST",
        endpoint: str = "",
        parameters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a tool definition.

        Args:
            name: Tool display name
            function_name: Function identifier (tool_id)
            description: Tool description
            method: HTTP method
            endpoint: API endpoint
            parameters: Parameter definitions

        Returns:
            Tool JSON
        """
        tool_id = function_name  # Use function name as ID

        tool = {
            "id": tool_id,
            "name": name,
            "description": description,
            "type": "api",
            "config": {
                "method": method,
                "endpoint": endpoint,
                "headers": {},
                "body_template": "",
            },
            "parameters": parameters or [],
        }

        # Format tool for context registration
        tool_json_for_context = {
            "original_id": tool_id,
            "name": name,
            "function_definition": {
                "name": function_name,
                "description": description,
                "parameters": parameters or [],
            },
        }
        self.context.register_tool(tool_json_for_context)
        logger.debug(f"Created tool: {name} ({tool_id})")
        return tool

    def _next_position(self) -> NodePosition:
        """
        Calculate the next node position.

        Uses a grid layout with automatic row advancement.
        """
        x = self.START_X + (self._col * self.HORIZONTAL_SPACING)
        y = self.START_Y + (self._row * self.VERTICAL_SPACING)

        self._col += 1
        if self._col > self._max_col:
            self._max_col = self._col

        return NodePosition(x=x, y=y)

    def advance_row(self) -> None:
        """Move to the next row, reset column."""
        self._row += 1
        self._col = 0

    def reset_position(self) -> None:
        """Reset position to start."""
        self._row = 0
        self._col = 0
        self._max_col = 0

    def set_position(self, row: int, col: int) -> None:
        """Set explicit row and column."""
        self._row = row
        self._col = col
