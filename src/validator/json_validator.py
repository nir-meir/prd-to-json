"""
JSON Validator - Validates INSAIT JSON output for correctness.

Performs multiple validation passes:
1. Schema validation - Required fields and types
2. Reference validation - Node/tool/variable references
3. Flow validation - Graph connectivity
4. Semantic validation - Business logic constraints
"""

from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"       # Must be fixed
    WARNING = "warning"   # Should be fixed
    INFO = "info"         # Informational


@dataclass
class ValidationIssue:
    """A single validation issue."""
    code: str
    message: str
    severity: ValidationSeverity
    path: str = ""  # JSON path to the issue
    context: Dict[str, Any] = field(default_factory=dict)
    auto_fixable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "path": self.path,
            "context": self.context,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class ValidationResult:
    """Result of validation process."""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def auto_fixable_count(self) -> int:
        return sum(1 for i in self.issues if i.auto_fixable)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "auto_fixable_count": self.auto_fixable_count,
            "issues": [i.to_dict() for i in self.issues],
        }


class INSAITValidator:
    """
    Validator for INSAIT JSON format.

    Validates:
    - Required fields present
    - Field types correct
    - Node/tool/variable references valid
    - Flow graph connected (no orphans)
    - Business constraints met
    """

    # Required top-level fields
    REQUIRED_TOP_LEVEL = ["name", "flow"]

    # Required flow fields
    REQUIRED_FLOW = ["start_node_id", "nodes"]

    # Required node fields by type
    NODE_REQUIRED_FIELDS = {
        "start": ["id", "type", "name", "position", "data"],
        "end": ["id", "type", "name", "position", "data"],
        "collect": ["id", "type", "name", "position", "data"],
        "conversation": ["id", "type", "name", "position", "data"],
        "api": ["id", "type", "name", "position", "data"],
        "condition": ["id", "type", "name", "position", "data"],
        "set_variables": ["id", "type", "name", "position", "data"],
    }

    def __init__(self, strict_mode: bool = False):
        """
        Initialize validator.

        Args:
            strict_mode: If True, warnings are treated as errors
        """
        self.strict_mode = strict_mode

    def validate(self, json_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate INSAIT JSON data.

        Args:
            json_data: The JSON data to validate

        Returns:
            ValidationResult with all issues found
        """
        issues: List[ValidationIssue] = []

        # Stage 1: Schema validation
        issues.extend(self._validate_schema(json_data))

        # Stage 2: Reference validation
        issues.extend(self._validate_references(json_data))

        # Stage 3: Flow validation
        issues.extend(self._validate_flow(json_data))

        # Stage 4: Semantic validation
        issues.extend(self._validate_semantics(json_data))

        # Determine overall validity
        has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
        has_warnings = any(i.severity == ValidationSeverity.WARNING for i in issues)

        valid = not has_errors
        if self.strict_mode and has_warnings:
            valid = False

        return ValidationResult(valid=valid, issues=issues)

    def _validate_schema(self, data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate JSON schema/structure."""
        issues = []

        # Top-level fields
        for field in self.REQUIRED_TOP_LEVEL:
            if field not in data:
                issues.append(ValidationIssue(
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Missing required top-level field: {field}",
                    severity=ValidationSeverity.ERROR,
                    path=f"$.{field}",
                    auto_fixable=False,
                ))

        # Flow fields
        flow = data.get("flow", {})
        if flow:
            for field in self.REQUIRED_FLOW:
                if field not in flow:
                    issues.append(ValidationIssue(
                        code="MISSING_FLOW_FIELD",
                        message=f"Missing required flow field: {field}",
                        severity=ValidationSeverity.ERROR,
                        path=f"$.flow.{field}",
                        auto_fixable=field == "start_node_id",
                    ))

            # Validate nodes
            nodes = flow.get("nodes", {})
            if isinstance(nodes, dict):
                issues.extend(self._validate_nodes(nodes))
            elif isinstance(nodes, list):
                # Convert list to dict for validation
                for i, node in enumerate(nodes):
                    issues.extend(self._validate_node(node, f"$.flow.nodes[{i}]"))

        # Validate tools
        tools = data.get("tools", [])
        for i, tool in enumerate(tools):
            issues.extend(self._validate_tool(tool, f"$.tools[{i}]"))

        # Validate variables
        variables = data.get("variables", [])
        for i, var in enumerate(variables):
            issues.extend(self._validate_variable(var, f"$.variables[{i}]"))

        return issues

    def _validate_nodes(self, nodes: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate all nodes in the nodes dict."""
        issues = []
        for node_id, node in nodes.items():
            path = f"$.flow.nodes.{node_id}"
            issues.extend(self._validate_node(node, path))
        return issues

    def _validate_node(self, node: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate a single node."""
        issues = []

        # Check required fields
        node_type = node.get("type", "unknown")
        required = self.NODE_REQUIRED_FIELDS.get(node_type, ["id", "type", "name"])

        for field in required:
            if field not in node:
                issues.append(ValidationIssue(
                    code="MISSING_NODE_FIELD",
                    message=f"Node missing required field: {field}",
                    severity=ValidationSeverity.ERROR,
                    path=f"{path}.{field}",
                    context={"node_type": node_type, "field": field},
                    auto_fixable=field in ("position", "data"),
                ))

        # Validate node ID
        if "id" in node and not node["id"]:
            issues.append(ValidationIssue(
                code="EMPTY_NODE_ID",
                message="Node has empty ID",
                severity=ValidationSeverity.ERROR,
                path=f"{path}.id",
                auto_fixable=True,
            ))

        # Type-specific validation
        if node_type == "collect":
            issues.extend(self._validate_collect_node(node, path))
        elif node_type == "api":
            issues.extend(self._validate_api_node(node, path))
        elif node_type == "condition":
            issues.extend(self._validate_condition_node(node, path))

        return issues

    def _validate_collect_node(self, node: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate collect node specifics."""
        issues = []
        data = node.get("data", {})

        if not data.get("variable_name"):
            issues.append(ValidationIssue(
                code="COLLECT_NO_VARIABLE",
                message="Collect node missing variable_name",
                severity=ValidationSeverity.ERROR,
                path=f"{path}.data.variable_name",
                auto_fixable=False,
            ))

        if not data.get("prompt"):
            issues.append(ValidationIssue(
                code="COLLECT_NO_PROMPT",
                message="Collect node missing prompt",
                severity=ValidationSeverity.WARNING,
                path=f"{path}.data.prompt",
                auto_fixable=True,
            ))

        return issues

    def _validate_api_node(self, node: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate API node specifics."""
        issues = []
        data = node.get("data", {})

        if not data.get("tool_id"):
            issues.append(ValidationIssue(
                code="API_NO_TOOL_ID",
                message="API node missing tool_id",
                severity=ValidationSeverity.ERROR,
                path=f"{path}.data.tool_id",
                auto_fixable=False,
            ))

        return issues

    def _validate_condition_node(self, node: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate condition node specifics."""
        issues = []
        data = node.get("data", {})

        conditions = data.get("conditions", [])
        if not conditions:
            issues.append(ValidationIssue(
                code="CONDITION_NO_CONDITIONS",
                message="Condition node has no conditions defined",
                severity=ValidationSeverity.WARNING,
                path=f"{path}.data.conditions",
                auto_fixable=False,
            ))

        return issues

    def _validate_tool(self, tool: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate a tool definition."""
        issues = []

        required = ["id", "name"]
        for field in required:
            if field not in tool:
                issues.append(ValidationIssue(
                    code="MISSING_TOOL_FIELD",
                    message=f"Tool missing required field: {field}",
                    severity=ValidationSeverity.ERROR,
                    path=f"{path}.{field}",
                    auto_fixable=False,
                ))

        return issues

    def _validate_variable(self, var: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate a variable definition."""
        issues = []

        if not var.get("name"):
            issues.append(ValidationIssue(
                code="VARIABLE_NO_NAME",
                message="Variable missing name",
                severity=ValidationSeverity.ERROR,
                path=f"{path}.name",
                auto_fixable=False,
            ))

        return issues

    def _validate_references(self, data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate cross-references between components."""
        issues = []

        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})
        exits = flow.get("exits", [])
        tools = data.get("tools", [])

        # Get all IDs
        node_ids = set()
        if isinstance(nodes, dict):
            node_ids = set(nodes.keys())
        elif isinstance(nodes, list):
            node_ids = {n.get("id") for n in nodes if n.get("id")}

        tool_ids = {t.get("id") for t in tools if t.get("id")}
        tool_ids.update({t.get("function_definition", {}).get("name") for t in tools})

        # Validate start_node_id
        start_id = flow.get("start_node_id")
        if start_id and start_id not in node_ids:
            issues.append(ValidationIssue(
                code="INVALID_START_NODE",
                message=f"start_node_id references non-existent node: {start_id}",
                severity=ValidationSeverity.ERROR,
                path="$.flow.start_node_id",
                context={"start_node_id": start_id},
                auto_fixable=True,
            ))

        # Validate exit references
        for i, exit_data in enumerate(exits):
            source = exit_data.get("source_node_id") or exit_data.get("source")
            target = exit_data.get("target_node_id") or exit_data.get("target")

            if source and source not in node_ids:
                issues.append(ValidationIssue(
                    code="INVALID_EXIT_SOURCE",
                    message=f"Exit references non-existent source node: {source}",
                    severity=ValidationSeverity.ERROR,
                    path=f"$.flow.exits[{i}].source",
                    context={"source": source},
                    auto_fixable=False,
                ))

            if target and target not in node_ids:
                issues.append(ValidationIssue(
                    code="INVALID_EXIT_TARGET",
                    message=f"Exit references non-existent target node: {target}",
                    severity=ValidationSeverity.ERROR,
                    path=f"$.flow.exits[{i}].target",
                    context={"target": target},
                    auto_fixable=False,
                ))

        # Validate API node tool references
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if node.get("type") == "api":
                    tool_id = node.get("data", {}).get("tool_id")
                    if tool_id and tool_id not in tool_ids:
                        issues.append(ValidationIssue(
                            code="INVALID_TOOL_REFERENCE",
                            message=f"API node references non-existent tool: {tool_id}",
                            severity=ValidationSeverity.ERROR,
                            path=f"$.flow.nodes.{node_id}.data.tool_id",
                            context={"tool_id": tool_id, "node_id": node_id},
                            auto_fixable=False,
                        ))

        return issues

    def _validate_flow(self, data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate flow connectivity."""
        issues = []

        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})
        exits = flow.get("exits", [])
        start_id = flow.get("start_node_id")

        if not nodes or not start_id:
            return issues

        # Build adjacency list
        node_ids = set()
        if isinstance(nodes, dict):
            node_ids = set(nodes.keys())
        elif isinstance(nodes, list):
            node_ids = {n.get("id") for n in nodes if n.get("id")}

        # Find reachable nodes from start
        reachable = self._find_reachable_nodes(start_id, exits)

        # Find orphaned nodes
        orphaned = node_ids - reachable - {start_id}
        for node_id in orphaned:
            issues.append(ValidationIssue(
                code="ORPHANED_NODE",
                message=f"Node is not reachable from start: {node_id}",
                severity=ValidationSeverity.WARNING,
                path=f"$.flow.nodes.{node_id}",
                context={"node_id": node_id},
                auto_fixable=True,
            ))

        # Find dead-end nodes (non-end nodes with no outgoing exits)
        end_node_ids = self._find_end_nodes(nodes)
        dead_ends = self._find_dead_ends(node_ids, exits, end_node_ids)

        for node_id in dead_ends:
            issues.append(ValidationIssue(
                code="DEAD_END_NODE",
                message=f"Node has no outgoing exits: {node_id}",
                severity=ValidationSeverity.WARNING,
                path=f"$.flow.nodes.{node_id}",
                context={"node_id": node_id},
                auto_fixable=True,
            ))

        return issues

    def _find_reachable_nodes(
        self,
        start_id: str,
        exits: List[Dict[str, Any]]
    ) -> Set[str]:
        """Find all nodes reachable from start using BFS."""
        reachable = {start_id}
        queue = [start_id]

        # Build adjacency from exits
        adj: Dict[str, List[str]] = {}
        for exit_data in exits:
            source = exit_data.get("source_node_id") or exit_data.get("source")
            target = exit_data.get("target_node_id") or exit_data.get("target")
            if source and target:
                adj.setdefault(source, []).append(target)

        while queue:
            current = queue.pop(0)
            for neighbor in adj.get(current, []):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)

        return reachable

    def _find_end_nodes(self, nodes: Dict[str, Any] | List) -> Set[str]:
        """Find all end nodes."""
        end_ids = set()
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if node.get("type") == "end":
                    end_ids.add(node_id)
        elif isinstance(nodes, list):
            for node in nodes:
                if node.get("type") == "end":
                    end_ids.add(node.get("id"))
        return end_ids

    def _find_dead_ends(
        self,
        node_ids: Set[str],
        exits: List[Dict[str, Any]],
        end_node_ids: Set[str]
    ) -> Set[str]:
        """Find non-end nodes with no outgoing exits."""
        # Collect nodes that have outgoing exits
        nodes_with_exits = set()
        for exit_data in exits:
            source = exit_data.get("source_node_id") or exit_data.get("source")
            if source:
                nodes_with_exits.add(source)

        # Dead ends are nodes that aren't end nodes and have no exits
        dead_ends = node_ids - nodes_with_exits - end_node_ids
        return dead_ends

    def _validate_semantics(self, data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate semantic/business constraints."""
        issues = []

        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})

        # Check for at least one start node
        has_start = False
        if isinstance(nodes, dict):
            has_start = any(n.get("type") == "start" for n in nodes.values())
        elif isinstance(nodes, list):
            has_start = any(n.get("type") == "start" for n in nodes)

        if not has_start:
            issues.append(ValidationIssue(
                code="NO_START_NODE",
                message="Flow has no start node",
                severity=ValidationSeverity.ERROR,
                path="$.flow.nodes",
                auto_fixable=True,
            ))

        # Check for at least one end node
        has_end = False
        if isinstance(nodes, dict):
            has_end = any(n.get("type") == "end" for n in nodes.values())
        elif isinstance(nodes, list):
            has_end = any(n.get("type") == "end" for n in nodes)

        if not has_end:
            issues.append(ValidationIssue(
                code="NO_END_NODE",
                message="Flow has no end node",
                severity=ValidationSeverity.WARNING,
                path="$.flow.nodes",
                auto_fixable=True,
            ))

        return issues
