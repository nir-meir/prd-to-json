"""
Generation Context - State management throughout the pipeline.

The GenerationContext maintains state as the PRD moves through parsing,
generation, validation, and output stages. It tracks generated artifacts,
coordinates node IDs, manages positions, and collects errors/warnings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Callable
from enum import Enum
import uuid

from ..parser.models import ParsedPRD
from .config import AppConfig


class GenerationPhase(Enum):
    """Current phase of the generation pipeline."""
    INITIALIZED = "initialized"
    PARSING = "parsing"
    PLANNING = "planning"
    GENERATING = "generating"
    VALIDATING = "validating"
    FIXING = "fixing"
    COMPOSING = "composing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class NodeReference:
    """
    Reference to a generated node.

    Used to track nodes during generation for cross-referencing
    and flow connectivity.
    """
    node_id: str
    node_type: str
    name: str = ""
    feature_id: Optional[str] = None
    position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})

    # Connection tracking
    incoming_exits: List[str] = field(default_factory=list)  # Exit IDs pointing to this node
    outgoing_exits: List[str] = field(default_factory=list)  # Exit IDs from this node


@dataclass
class ExitReference:
    """
    Reference to a generated exit/edge.

    Tracks connections between nodes.
    """
    exit_id: str
    source_node_id: str
    target_node_id: str
    name: str = "Next"
    condition_type: str = "always"
    priority: int = 0


@dataclass
class ToolReference:
    """
    Reference to a generated tool definition.

    Tracks API tools for node reference resolution.
    """
    tool_id: str  # original_id
    function_name: str  # tool_id in API nodes
    name: str
    api_endpoint_name: Optional[str] = None  # Reference to APIEndpoint


@dataclass
class GenerationStats:
    """Statistics from the generation process."""
    total_nodes: int = 0
    nodes_by_type: Dict[str, int] = field(default_factory=dict)
    total_exits: int = 0
    total_tools: int = 0
    total_variables: int = 0

    # LLM usage
    llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Timing
    parse_time_seconds: float = 0.0
    generation_time_seconds: float = 0.0
    validation_time_seconds: float = 0.0
    total_time_seconds: float = 0.0


@dataclass
class GenerationContext:
    """
    Maintains state throughout the generation pipeline.

    This context is passed between all pipeline components and tracks:
    - The parsed PRD being processed
    - All generated artifacts (nodes, exits, tools, variables)
    - ID generation and uniqueness
    - Node positioning for visual layout
    - Errors and warnings
    - Progress tracking
    """

    # Input
    parsed_prd: Optional[ParsedPRD] = None
    config: AppConfig = field(default_factory=AppConfig)

    # Pipeline state
    phase: GenerationPhase = GenerationPhase.INITIALIZED
    current_feature_id: Optional[str] = None
    current_strategy: Optional[str] = None

    # Generated artifacts - nodes
    nodes: Dict[str, NodeReference] = field(default_factory=dict)
    nodes_json: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Full JSON for each node

    # Generated artifacts - exits
    exits: List[ExitReference] = field(default_factory=list)
    exits_json: List[Dict[str, Any]] = field(default_factory=list)

    # Generated artifacts - tools
    tools: Dict[str, ToolReference] = field(default_factory=dict)
    tools_json: List[Dict[str, Any]] = field(default_factory=list)

    # Generated artifacts - variables
    variables_json: List[Dict[str, Any]] = field(default_factory=list)

    # ID tracking
    _node_id_counter: int = 0
    _exit_id_counter: int = 0
    _used_node_ids: Set[str] = field(default_factory=set)
    _used_exit_ids: Set[str] = field(default_factory=set)

    # Feature tracking
    feature_start_nodes: Dict[str, str] = field(default_factory=dict)  # feature_id -> start node_id
    feature_end_nodes: Dict[str, List[str]] = field(default_factory=dict)  # feature_id -> end node_ids
    feature_chunks: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # feature_id -> generated chunk

    # Position tracking for layout
    _current_x: int = 0
    _current_y: int = 0
    row_height: int = 150
    column_width: int = 250
    feature_row_gap: int = 300  # Gap between feature rows

    # Start node ID (required by INSAIT)
    start_node_id: Optional[str] = None

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Statistics
    stats: GenerationStats = field(default_factory=GenerationStats)

    # Progress callback
    progress_callback: Optional[Callable[[str, float], None]] = None

    # --- ID Generation ---

    def generate_node_id(self, prefix: str = "node") -> str:
        """
        Generate a unique node ID.

        Args:
            prefix: Prefix for the node ID (e.g., "start", "collect", "api")

        Returns:
            Unique node ID in kebab-case
        """
        while True:
            node_id = f"{prefix}-{self._node_id_counter}"
            self._node_id_counter += 1
            if node_id not in self._used_node_ids:
                self._used_node_ids.add(node_id)
                return node_id

    def generate_exit_id(self, source_id: str, target_id: str) -> str:
        """
        Generate a unique exit ID.

        Args:
            source_id: Source node ID
            target_id: Target node ID

        Returns:
            Unique exit ID
        """
        base_id = f"exit-{source_id}-to-{target_id}"
        if base_id not in self._used_exit_ids:
            self._used_exit_ids.add(base_id)
            return base_id

        # If collision, add counter
        while True:
            exit_id = f"{base_id}-{self._exit_id_counter}"
            self._exit_id_counter += 1
            if exit_id not in self._used_exit_ids:
                self._used_exit_ids.add(exit_id)
                return exit_id

    def generate_uuid(self) -> str:
        """Generate a UUID for tool IDs and flow definition ID."""
        return str(uuid.uuid4())

    def reserve_node_id(self, node_id: str) -> bool:
        """
        Reserve a specific node ID.

        Args:
            node_id: The node ID to reserve

        Returns:
            True if reserved successfully, False if already taken
        """
        if node_id in self._used_node_ids:
            return False
        self._used_node_ids.add(node_id)
        return True

    # --- Position Management ---

    def get_next_position(self, new_row: bool = False) -> Dict[str, int]:
        """
        Get the next position for a node in the visual layout.

        Args:
            new_row: If True, move to a new row

        Returns:
            Position dict with x and y coordinates
        """
        if new_row:
            self._current_x = 0
            self._current_y += self.row_height
        else:
            self._current_x += self.column_width

        return {"x": self._current_x, "y": self._current_y}

    def start_new_feature_row(self) -> Dict[str, int]:
        """
        Start a new row for a new feature.

        Returns:
            Position dict for the first node in the new feature
        """
        self._current_x = 0
        self._current_y += self.feature_row_gap
        return {"x": self._current_x, "y": self._current_y}

    def get_current_position(self) -> Dict[str, int]:
        """Get current position without advancing."""
        return {"x": self._current_x, "y": self._current_y}

    def set_position(self, x: int, y: int) -> None:
        """Set the current position explicitly."""
        self._current_x = x
        self._current_y = y

    # --- Node Management ---

    def register_node(
        self,
        node_json: Dict[str, Any],
        feature_id: Optional[str] = None
    ) -> NodeReference:
        """
        Register a generated node.

        Args:
            node_json: The full node JSON
            feature_id: Optional feature ID this node belongs to

        Returns:
            NodeReference for the registered node
        """
        node_id = node_json["id"]
        node_type = node_json["type"]
        name = node_json.get("name", "")
        position = node_json.get("position", {"x": 0, "y": 0})

        ref = NodeReference(
            node_id=node_id,
            node_type=node_type,
            name=name,
            feature_id=feature_id,
            position=position,
        )

        self.nodes[node_id] = ref
        self.nodes_json[node_id] = node_json
        self._used_node_ids.add(node_id)

        # Update stats
        self.stats.total_nodes += 1
        self.stats.nodes_by_type[node_type] = self.stats.nodes_by_type.get(node_type, 0) + 1

        # Track start node
        if node_type == "start" and self.start_node_id is None:
            self.start_node_id = node_id

        return ref

    def get_node(self, node_id: str) -> Optional[NodeReference]:
        """Get a node reference by ID."""
        return self.nodes.get(node_id)

    def get_nodes_by_type(self, node_type: str) -> List[NodeReference]:
        """Get all nodes of a specific type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def get_nodes_by_feature(self, feature_id: str) -> List[NodeReference]:
        """Get all nodes belonging to a feature."""
        return [n for n in self.nodes.values() if n.feature_id == feature_id]

    def node_exists(self, node_id: str) -> bool:
        """Check if a node ID exists."""
        return node_id in self.nodes

    # --- Exit Management ---

    def add_exit(
        self,
        source_id: str,
        target_id: str,
        name: str = "Next",
        condition: Optional[Dict[str, Any]] = None,
        priority: Optional[int] = None
    ) -> ExitReference:
        """
        Add an exit/edge between nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            name: Display name for the exit
            condition: Condition for this exit (default: always)
            priority: Priority (default: auto-increment)

        Returns:
            ExitReference for the added exit
        """
        exit_id = self.generate_exit_id(source_id, target_id)

        if priority is None:
            priority = len(self.exits)

        condition = condition or {"type": "always"}
        condition_type = condition.get("type", "always")

        ref = ExitReference(
            exit_id=exit_id,
            source_node_id=source_id,
            target_node_id=target_id,
            name=name,
            condition_type=condition_type,
            priority=priority,
        )
        self.exits.append(ref)

        exit_json = {
            "id": exit_id,
            "name": name,
            "source_node_id": source_id,
            "target_node_id": target_id,
            "priority": priority,
            "condition": condition,
        }
        self.exits_json.append(exit_json)

        # Update node references
        if source_id in self.nodes:
            self.nodes[source_id].outgoing_exits.append(exit_id)
        if target_id in self.nodes:
            self.nodes[target_id].incoming_exits.append(exit_id)

        self.stats.total_exits += 1

        return ref

    def get_exits_from_node(self, node_id: str) -> List[ExitReference]:
        """Get all exits originating from a node."""
        return [e for e in self.exits if e.source_node_id == node_id]

    def get_exits_to_node(self, node_id: str) -> List[ExitReference]:
        """Get all exits pointing to a node."""
        return [e for e in self.exits if e.target_node_id == node_id]

    # --- Tool Management ---

    def register_tool(
        self,
        tool_json: Dict[str, Any],
        api_endpoint_name: Optional[str] = None
    ) -> ToolReference:
        """
        Register a generated tool.

        Args:
            tool_json: The full tool JSON
            api_endpoint_name: Optional name of the APIEndpoint this tool implements

        Returns:
            ToolReference for the registered tool
        """
        tool_id = tool_json["original_id"]
        function_name = tool_json["function_definition"]["name"]
        name = tool_json["name"]

        ref = ToolReference(
            tool_id=tool_id,
            function_name=function_name,
            name=name,
            api_endpoint_name=api_endpoint_name,
        )

        self.tools[function_name] = ref
        self.tools_json.append(tool_json)
        self.stats.total_tools += 1

        return ref

    def get_tool_by_function_name(self, function_name: str) -> Optional[ToolReference]:
        """Get a tool reference by function name."""
        return self.tools.get(function_name)

    def tool_exists(self, function_name: str) -> bool:
        """Check if a tool with the given function name exists."""
        return function_name in self.tools

    # --- Variable Management ---

    def add_variable(self, variable_json: Dict[str, Any]) -> None:
        """Add a variable to the flow definition."""
        self.variables_json.append(variable_json)
        self.stats.total_variables += 1

    # --- Feature Tracking ---

    def set_feature_start_node(self, feature_id: str, node_id: str) -> None:
        """Set the start node for a feature."""
        self.feature_start_nodes[feature_id] = node_id

    def add_feature_end_node(self, feature_id: str, node_id: str) -> None:
        """Add an end node for a feature."""
        if feature_id not in self.feature_end_nodes:
            self.feature_end_nodes[feature_id] = []
        self.feature_end_nodes[feature_id].append(node_id)

    def store_feature_chunk(self, feature_id: str, chunk: Dict[str, Any]) -> None:
        """Store a generated feature chunk for later composition."""
        self.feature_chunks[feature_id] = chunk

    # --- Error/Warning Management ---

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    # --- Progress Reporting ---

    def report_progress(self, message: str, progress: float) -> None:
        """
        Report progress to the callback if set.

        Args:
            message: Progress message
            progress: Progress percentage (0.0 to 1.0)
        """
        if self.progress_callback:
            self.progress_callback(message, progress)

    # --- Output Generation ---

    def get_flow_json(self) -> Dict[str, Any]:
        """
        Get the flow section of the INSAIT JSON.

        Returns:
            Flow dict with start_node_id, nodes, and exits
        """
        return {
            "start_node_id": self.start_node_id or "start-node",
            "nodes": self.nodes_json,
            "exits": self.exits_json,
        }

    def get_tools_json(self) -> List[Dict[str, Any]]:
        """Get the tools array for the INSAIT JSON."""
        return self.tools_json

    def get_variables_json(self) -> List[Dict[str, Any]]:
        """Get the variables array for the INSAIT JSON."""
        return self.variables_json

    # --- Validation Helpers ---

    def get_orphaned_nodes(self) -> List[str]:
        """
        Find nodes that are not connected to the flow.

        Returns:
            List of orphaned node IDs
        """
        if not self.start_node_id:
            return list(self.nodes.keys())

        # BFS from start node
        connected = {self.start_node_id}
        queue = [self.start_node_id]

        while queue:
            node_id = queue.pop(0)
            for exit_ref in self.get_exits_from_node(node_id):
                if exit_ref.target_node_id not in connected:
                    connected.add(exit_ref.target_node_id)
                    queue.append(exit_ref.target_node_id)

        return [nid for nid in self.nodes.keys() if nid not in connected]

    def get_dead_end_nodes(self) -> List[str]:
        """
        Find non-end nodes that have no outgoing exits.

        Returns:
            List of dead-end node IDs
        """
        dead_ends = []
        for node_id, node_ref in self.nodes.items():
            if node_ref.node_type != "end" and not node_ref.outgoing_exits:
                dead_ends.append(node_id)
        return dead_ends

    def get_invalid_exits(self) -> List[str]:
        """
        Find exits that reference non-existent nodes.

        Returns:
            List of invalid exit IDs
        """
        invalid = []
        for exit_ref in self.exits:
            if exit_ref.source_node_id not in self.nodes:
                invalid.append(exit_ref.exit_id)
            elif exit_ref.target_node_id not in self.nodes:
                invalid.append(exit_ref.exit_id)
        return invalid

    # --- Reset ---

    def reset(self) -> None:
        """Reset context for a fresh generation."""
        self.phase = GenerationPhase.INITIALIZED
        self.current_feature_id = None
        self.nodes.clear()
        self.nodes_json.clear()
        self.exits.clear()
        self.exits_json.clear()
        self.tools.clear()
        self.tools_json.clear()
        self.variables_json.clear()
        self._node_id_counter = 0
        self._exit_id_counter = 0
        self._used_node_ids.clear()
        self._used_exit_ids.clear()
        self.feature_start_nodes.clear()
        self.feature_end_nodes.clear()
        self.feature_chunks.clear()
        self._current_x = 0
        self._current_y = 0
        self.start_node_id = None
        self.errors.clear()
        self.warnings.clear()
        self.stats = GenerationStats()
