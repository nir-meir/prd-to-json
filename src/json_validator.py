"""
JSON Validator - Comprehensive validation for INSAIT platform JSON.

Validates generated JSON against the exact INSAIT platform schema requirements
to catch issues before import fails with 400 Bad Request errors.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ValidationCategory(Enum):
    """Categories of validation issues."""
    STRUCTURAL = "Structural Issues"
    REFERENCE = "Reference Issues"
    DATA_TYPE = "Data Type Issues"
    UNIQUENESS = "Uniqueness Issues"


@dataclass
class ValidationIssue:
    """A single validation issue."""
    category: ValidationCategory
    message: str
    path: str = ""
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationReport:
    """Comprehensive validation report."""
    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_error(self, category: ValidationCategory, message: str, path: str = "") -> None:
        """Add an error."""
        self.issues.append(ValidationIssue(category, message, path, "error"))
        self.is_valid = False

    def add_warning(self, category: ValidationCategory, message: str, path: str = "") -> None:
        """Add a warning."""
        self.issues.append(ValidationIssue(category, message, path, "warning"))

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only errors."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warnings."""
        return [i for i in self.issues if i.severity == "warning"]

    def get_by_category(self, category: ValidationCategory) -> list[ValidationIssue]:
        """Get issues by category."""
        return [i for i in self.issues if i.category == category]

    def format_report(self) -> str:
        """Format the validation report for display."""
        if self.is_valid and not self.warnings:
            return "Validation passed"

        lines = []

        if not self.is_valid:
            lines.append("Validation Failed")
        else:
            lines.append("Validation passed with warnings")

        lines.append("")

        # Group by category
        for category in ValidationCategory:
            category_issues = self.get_by_category(category)
            if category_issues:
                lines.append(f"{category.value}:")
                for issue in category_issues:
                    prefix = "-" if issue.severity == "error" else "~"
                    if issue.path:
                        lines.append(f"  {prefix} {issue.path}: {issue.message}")
                    else:
                        lines.append(f"  {prefix} {issue.message}")
                lines.append("")

        return "\n".join(lines)


class INSAITValidator:
    """
    Comprehensive validator for INSAIT platform JSON.

    Validates:
    - Structure: All required fields exist with correct types
    - References: All IDs reference existing entities
    - Data types: UUIDs, enums, numbers, etc. are valid
    - Uniqueness: No duplicate IDs
    """

    # Valid channel values
    VALID_CHANNELS = {"voice", "chat"}

    # Valid node types
    VALID_NODE_TYPES = {
        "start", "collect", "conversation", "api",
        "set_variables", "code", "end", "transfer",
        "message", "condition", "input", "ai", "action"
    }

    # System tool types that don't need to exist in tools array
    SYSTEM_TOOL_TYPES = {"transfer_to_human", "end_call", "schedule_appointment", "adjust_speech_rate"}

    # Required tool fields
    REQUIRED_TOOL_FIELDS = ["original_id", "name", "type", "function_definition", "execution_config"]

    # UUID regex pattern
    UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    # Variable reference pattern in expressions
    VAR_REFERENCE_PATTERN = re.compile(r'\{\{(\w+)\}\}')

    def validate(self, json_data: dict | str) -> ValidationReport:
        """
        Validate JSON data against INSAIT platform schema.

        Args:
            json_data: JSON data as dict or string

        Returns:
            ValidationReport with all issues found
        """
        report = ValidationReport()

        # Parse JSON if string
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except json.JSONDecodeError as e:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Invalid JSON syntax: {e}"
                )
                return report

        if not isinstance(json_data, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "JSON root must be an object"
            )
            return report

        # Run all validations
        self._validate_structure(json_data, report)
        self._validate_data_types(json_data, report)
        self._validate_references(json_data, report)
        self._validate_uniqueness(json_data, report)

        return report

    def _validate_structure(self, data: dict, report: ValidationReport) -> None:
        """Validate structural requirements."""
        # Top-level keys
        required_top_level = ["metadata", "agent", "flow_definition"]
        for key in required_top_level:
            if key not in data:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Missing required top-level key: '{key}'"
                )

        # Recommended top-level arrays
        if "tools" not in data:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing top-level 'tools' array"
            )
        if "filler_sentences" not in data:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing top-level 'filler_sentences' array"
            )
        if "nikud_replacements" not in data:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing top-level 'nikud_replacements' array"
            )

        # Metadata structure
        if "metadata" in data:
            self._validate_metadata_structure(data["metadata"], report)

        # Agent structure
        if "agent" in data:
            self._validate_agent_structure(data["agent"], report)

        # Flow definition structure
        if "flow_definition" in data:
            self._validate_flow_definition_structure(data["flow_definition"], report)

    def _validate_metadata_structure(self, metadata: Any, report: ValidationReport) -> None:
        """Validate metadata structure."""
        if not isinstance(metadata, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'metadata' must be an object",
                "metadata"
            )
            return

        # Recommended fields
        recommended = ["export_version", "exported_at"]
        for key in recommended:
            if key not in metadata:
                report.add_warning(
                    ValidationCategory.STRUCTURAL,
                    f"Missing recommended field: '{key}'",
                    f"metadata.{key}"
                )

    def _validate_agent_structure(self, agent: Any, report: ValidationReport) -> None:
        """Validate agent structure."""
        if not isinstance(agent, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'agent' must be an object",
                "agent"
            )
            return

        required = ["name", "channel"]
        for key in required:
            if key not in agent:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Missing required field: '{key}'",
                    f"agent.{key}"
                )

        # Store agent name for stats
        report.stats["agent_name"] = agent.get("name", "Unknown")

    def _validate_flow_definition_structure(self, flow_def: Any, report: ValidationReport) -> None:
        """Validate flow_definition structure."""
        if not isinstance(flow_def, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'flow_definition' must be an object",
                "flow_definition"
            )
            return

        # Required fields
        required = ["id", "name", "version", "channel", "global_settings", "flow"]
        for key in required:
            if key not in flow_def:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Missing required field: '{key}'",
                    f"flow_definition.{key}"
                )

        # Validate global_settings
        if "global_settings" in flow_def:
            self._validate_global_settings_structure(
                flow_def["global_settings"], report
            )

        # Validate flow
        if "flow" in flow_def:
            self._validate_flow_structure(flow_def["flow"], report)

        # Validate variables array
        if "variables" in flow_def:
            if not isinstance(flow_def["variables"], list):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "'variables' must be an array",
                    "flow_definition.variables"
                )
            else:
                self._validate_variables_structure(flow_def["variables"], report)

        # Validate flow_definition.tools object
        if "tools" in flow_def:
            self._validate_flow_definition_tools(flow_def["tools"], report)
        else:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing 'tools' object in flow_definition",
                "flow_definition.tools"
            )

    def _validate_global_settings_structure(self, settings: Any, report: ValidationReport) -> None:
        """Validate global_settings structure."""
        if not isinstance(settings, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'global_settings' must be an object",
                "flow_definition.global_settings"
            )
            return

        # Required fields
        required = ["system_prompt", "llm_provider", "llm_model"]
        for key in required:
            if key not in settings:
                report.add_warning(
                    ValidationCategory.STRUCTURAL,
                    f"Missing recommended field: '{key}'",
                    f"flow_definition.global_settings.{key}"
                )

    def _validate_flow_structure(self, flow: Any, report: ValidationReport) -> None:
        """Validate flow structure (nodes and exits)."""
        if not isinstance(flow, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'flow' must be an object",
                "flow_definition.flow"
            )
            return

        # Required fields
        required = ["start_node_id", "nodes"]
        for key in required:
            if key not in flow:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Missing required field: '{key}'",
                    f"flow_definition.flow.{key}"
                )

        # Nodes must be an object (not array)
        if "nodes" in flow:
            nodes = flow["nodes"]
            if isinstance(nodes, list):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "'nodes' must be an object (dict), not an array. "
                    "The INSAIT platform expects nodes as {node_id: node_data}",
                    "flow_definition.flow.nodes"
                )
            elif not isinstance(nodes, dict):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "'nodes' must be an object",
                    "flow_definition.flow.nodes"
                )
            else:
                self._validate_nodes_structure(nodes, report)
                report.stats["node_count"] = len(nodes)

        # Exits must be an array
        if "exits" in flow:
            exits = flow["exits"]
            if not isinstance(exits, list):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "'exits' must be an array",
                    "flow_definition.flow.exits"
                )
            else:
                self._validate_exits_structure(exits, report)
                report.stats["exit_count"] = len(exits)

    def _validate_nodes_structure(self, nodes: dict, report: ValidationReport) -> None:
        """Validate nodes structure."""
        node_types: dict[str, int] = {}

        for node_id, node in nodes.items():
            path = f"flow_definition.flow.nodes.{node_id}"

            if not isinstance(node, dict):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Node must be an object",
                    path
                )
                continue

            # Required fields
            required = ["id", "type", "name", "data"]
            for key in required:
                if key not in node:
                    report.add_error(
                        ValidationCategory.STRUCTURAL,
                        f"Missing required field: '{key}'",
                        f"{path}.{key}"
                    )

            # ID must match key
            if "id" in node and node["id"] != node_id:
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    f"Node ID '{node['id']}' doesn't match key '{node_id}'",
                    path
                )

            # Track types
            node_type = node.get("type", "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1

            # Validate node data based on type
            if "data" in node and isinstance(node["data"], dict):
                self._validate_node_data(node_type, node["data"], path, report)

        report.stats["node_types"] = node_types

    def _validate_node_data(
        self,
        node_type: str,
        data: dict,
        path: str,
        report: ValidationReport
    ) -> None:
        """Validate node data based on type."""
        if node_type == "api":
            if "tool_id" not in data:
                report.add_warning(
                    ValidationCategory.STRUCTURAL,
                    "API node missing 'tool_id'",
                    f"{path}.data.tool_id"
                )

        elif node_type == "collect":
            if "fields" not in data:
                report.add_warning(
                    ValidationCategory.STRUCTURAL,
                    "Collect node missing 'fields'",
                    f"{path}.data.fields"
                )

        elif node_type == "set_variables":
            if "assignments" not in data:
                report.add_warning(
                    ValidationCategory.STRUCTURAL,
                    "Set variables node missing 'assignments'",
                    f"{path}.data.assignments"
                )

    def _validate_exits_structure(self, exits: list, report: ValidationReport) -> None:
        """Validate exits/edges structure."""
        for i, exit_obj in enumerate(exits):
            path = f"flow_definition.flow.exits[{i}]"

            if not isinstance(exit_obj, dict):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "Exit must be an object",
                    path
                )
                continue

            # Required fields
            required = ["id", "source_node_id", "target_node_id"]
            for key in required:
                if key not in exit_obj:
                    report.add_error(
                        ValidationCategory.STRUCTURAL,
                        f"Missing required field: '{key}'",
                        f"{path}.{key}"
                    )

    def _validate_variables_structure(self, variables: list, report: ValidationReport) -> None:
        """Validate variables structure."""
        required_fields = ["name", "type", "persist", "source"]
        recommended_fields = [
            "source_node_id", "collection_mode", "validation_rules",
            "options", "allowed_file_types", "max_file_size_mb"
        ]

        for i, var in enumerate(variables):
            path = f"flow_definition.variables[{i}]"

            if not isinstance(var, dict):
                report.add_error(
                    ValidationCategory.STRUCTURAL,
                    "Variable must be an object",
                    path
                )
                continue

            var_name = var.get("name", f"index_{i}")

            # Check required fields
            for field in required_fields:
                if field not in var:
                    report.add_warning(
                        ValidationCategory.STRUCTURAL,
                        f"Variable '{var_name}' missing field: '{field}'",
                        f"{path}.{field}"
                    )

            # Check recommended fields
            for field in recommended_fields:
                if field not in var:
                    report.add_warning(
                        ValidationCategory.STRUCTURAL,
                        f"Variable '{var_name}' missing recommended field: '{field}'",
                        f"{path}.{field}"
                    )

        report.stats["variable_count"] = len(variables)

    def _validate_flow_definition_tools(self, tools: Any, report: ValidationReport) -> None:
        """Validate flow_definition.tools object."""
        if not isinstance(tools, dict):
            report.add_error(
                ValidationCategory.STRUCTURAL,
                "'flow_definition.tools' must be an object",
                "flow_definition.tools"
            )
            return

        # Check for built_in_tools
        if "built_in_tools" not in tools:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing 'built_in_tools' in flow_definition.tools",
                "flow_definition.tools.built_in_tools"
            )
        elif isinstance(tools["built_in_tools"], dict):
            expected = ["transfer_to_human", "end_call", "schedule_appointment"]
            for tool_name in expected:
                if tool_name not in tools["built_in_tools"]:
                    report.add_warning(
                        ValidationCategory.STRUCTURAL,
                        f"Missing built-in tool setting: '{tool_name}'",
                        f"flow_definition.tools.built_in_tools.{tool_name}"
                    )

        # Check for global_tools
        if "global_tools" not in tools:
            report.add_warning(
                ValidationCategory.STRUCTURAL,
                "Missing 'global_tools' in flow_definition.tools",
                "flow_definition.tools.global_tools"
            )

    def _validate_data_types(self, data: dict, report: ValidationReport) -> None:
        """Validate data types (UUIDs, enums, etc.)."""

        # Validate channel enum
        agent_channel = data.get("agent", {}).get("channel")
        if agent_channel and agent_channel not in self.VALID_CHANNELS:
            report.add_error(
                ValidationCategory.DATA_TYPE,
                f"Invalid channel value '{agent_channel}', expected: {', '.join(self.VALID_CHANNELS)}",
                "agent.channel"
            )

        flow_def = data.get("flow_definition", {})

        # Validate flow_definition.id as UUID
        flow_id = flow_def.get("id")
        if flow_id and not self._is_valid_uuid(flow_id):
            report.add_warning(
                ValidationCategory.DATA_TYPE,
                f"'id' should be a valid UUID: '{flow_id}'",
                "flow_definition.id"
            )

        # Validate flow_definition.channel
        flow_channel = flow_def.get("channel")
        if flow_channel and flow_channel not in self.VALID_CHANNELS:
            report.add_error(
                ValidationCategory.DATA_TYPE,
                f"Invalid channel value '{flow_channel}', expected: {', '.join(self.VALID_CHANNELS)}",
                "flow_definition.channel"
            )

        # Validate version is a number
        version = flow_def.get("version")
        if version is not None and not isinstance(version, (int, float)):
            report.add_error(
                ValidationCategory.DATA_TYPE,
                f"'version' must be a number, got {type(version).__name__}",
                "flow_definition.version"
            )

        # Validate node types
        flow = flow_def.get("flow", {})
        nodes = flow.get("nodes", {})
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if isinstance(node, dict):
                    node_type = node.get("type")
                    if node_type and node_type not in self.VALID_NODE_TYPES:
                        report.add_warning(
                            ValidationCategory.DATA_TYPE,
                            f"Unknown node type '{node_type}'",
                            f"flow_definition.flow.nodes.{node_id}.type"
                        )

    def _validate_references(self, data: dict, report: ValidationReport) -> None:
        """Validate all ID references."""
        flow_def = data.get("flow_definition", {})
        flow = flow_def.get("flow", {})
        nodes = flow.get("nodes", {})
        exits = flow.get("exits", [])

        # Get all node IDs
        if isinstance(nodes, dict):
            node_ids = set(nodes.keys())
        elif isinstance(nodes, list):
            # Handle case where nodes is incorrectly an array
            node_ids = {n.get("id") for n in nodes if isinstance(n, dict) and n.get("id")}
        else:
            node_ids = set()

        # Validate start_node_id
        start_node_id = flow.get("start_node_id")
        if start_node_id and node_ids and start_node_id not in node_ids:
            report.add_error(
                ValidationCategory.REFERENCE,
                f"'start_node_id' references non-existent node: '{start_node_id}'",
                "flow_definition.flow.start_node_id"
            )

        # Validate exit references
        if isinstance(exits, list):
            for i, exit_obj in enumerate(exits):
                if not isinstance(exit_obj, dict):
                    continue

                source = exit_obj.get("source_node_id")
                target = exit_obj.get("target_node_id")
                exit_id = exit_obj.get("id", f"index_{i}")

                if source and node_ids and source not in node_ids:
                    report.add_error(
                        ValidationCategory.REFERENCE,
                        f"Exit '{exit_id}' references non-existent source node: '{source}'",
                        f"flow_definition.flow.exits[{i}].source_node_id"
                    )

                if target and node_ids and target not in node_ids:
                    report.add_error(
                        ValidationCategory.REFERENCE,
                        f"Exit '{exit_id}' references non-existent target node: '{target}'",
                        f"flow_definition.flow.exits[{i}].target_node_id"
                    )

                # Validate variable references in expressions
                condition = exit_obj.get("condition", {})
                if isinstance(condition, dict):
                    expression = condition.get("expression", "")
                    self._validate_expression_variables(
                        expression,
                        flow_def.get("variables", []),
                        f"flow_definition.flow.exits[{i}].condition.expression",
                        report
                    )

        # Validate tool references in API nodes
        # Tool references use function_definition.name, not original_id
        tools = data.get("tools", [])
        tool_function_names = set()
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    func_def = tool.get("function_definition", {})
                    if isinstance(func_def, dict):
                        func_name = func_def.get("name")
                        if func_name:
                            tool_function_names.add(func_name)

        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                if node.get("type") == "api":
                    tool_id = node.get("data", {}).get("tool_id")
                    if tool_id and tool_id not in tool_function_names and tool_id not in self.SYSTEM_TOOL_TYPES:
                        report.add_warning(
                            ValidationCategory.REFERENCE,
                            f"API node references tool not in tools array: '{tool_id}' "
                            f"(should match function_definition.name)",
                            f"flow_definition.flow.nodes.{node_id}.data.tool_id"
                        )

    def _validate_expression_variables(
        self,
        expression: str,
        variables: list,
        path: str,
        report: ValidationReport
    ) -> None:
        """Validate variable references in expressions."""
        if not expression:
            return

        # Get defined variable names
        var_names = set()
        if isinstance(variables, list):
            for var in variables:
                if isinstance(var, dict) and "name" in var:
                    var_names.add(var["name"])

        # Find referenced variables
        referenced = self.VAR_REFERENCE_PATTERN.findall(expression)

        for var_name in referenced:
            if var_names and var_name not in var_names:
                report.add_warning(
                    ValidationCategory.REFERENCE,
                    f"Expression references undefined variable: '{var_name}'",
                    path
                )

    def _validate_uniqueness(self, data: dict, report: ValidationReport) -> None:
        """Validate uniqueness of IDs."""
        flow_def = data.get("flow_definition", {})
        flow = flow_def.get("flow", {})

        # Check node ID uniqueness (nodes is a dict, so keys are unique by design)
        nodes = flow.get("nodes", {})
        if isinstance(nodes, list):
            # If nodes is incorrectly an array, check for duplicates
            seen_ids: set[str] = set()
            for node in nodes:
                if isinstance(node, dict):
                    node_id = node.get("id")
                    if node_id:
                        if node_id in seen_ids:
                            report.add_error(
                                ValidationCategory.UNIQUENESS,
                                f"Duplicate node ID: '{node_id}'",
                                "flow_definition.flow.nodes"
                            )
                        seen_ids.add(node_id)

        # Check exit ID uniqueness
        exits = flow.get("exits", [])
        if isinstance(exits, list):
            seen_exit_ids: set[str] = set()
            for i, exit_obj in enumerate(exits):
                if isinstance(exit_obj, dict):
                    exit_id = exit_obj.get("id")
                    if exit_id:
                        if exit_id in seen_exit_ids:
                            report.add_error(
                                ValidationCategory.UNIQUENESS,
                                f"Duplicate exit ID: '{exit_id}'",
                                f"flow_definition.flow.exits[{i}]"
                            )
                        seen_exit_ids.add(exit_id)

        # Check variable name uniqueness
        variables = flow_def.get("variables", [])
        if isinstance(variables, list):
            seen_var_names: dict[str, int] = {}
            for var in variables:
                if isinstance(var, dict):
                    var_name = var.get("name")
                    if var_name:
                        seen_var_names[var_name] = seen_var_names.get(var_name, 0) + 1

            for var_name, count in seen_var_names.items():
                if count > 1:
                    report.add_error(
                        ValidationCategory.UNIQUENESS,
                        f"Duplicate variable name: '{var_name}' appears {count} times",
                        "flow_definition.variables"
                    )

        # Check tool ID and function name uniqueness
        tools = data.get("tools", [])
        if isinstance(tools, list):
            seen_tool_ids: set[str] = set()
            seen_func_names: set[str] = set()
            for i, tool in enumerate(tools):
                if isinstance(tool, dict):
                    # Check original_id uniqueness
                    tool_id = tool.get("original_id")
                    if tool_id:
                        if tool_id in seen_tool_ids:
                            report.add_error(
                                ValidationCategory.UNIQUENESS,
                                f"Duplicate tool original_id: '{tool_id}'",
                                f"tools[{i}]"
                            )
                        seen_tool_ids.add(tool_id)

                    # Check function name uniqueness
                    func_def = tool.get("function_definition", {})
                    if isinstance(func_def, dict):
                        func_name = func_def.get("name")
                        if func_name:
                            if func_name in seen_func_names:
                                report.add_error(
                                    ValidationCategory.UNIQUENESS,
                                    f"Duplicate function name: '{func_name}'",
                                    f"tools[{i}].function_definition.name"
                                )
                            seen_func_names.add(func_name)

                    # Check required tool fields
                    for field in self.REQUIRED_TOOL_FIELDS:
                        if field not in tool:
                            report.add_error(
                                ValidationCategory.STRUCTURAL,
                                f"Tool missing required field: '{field}'",
                                f"tools[{i}].{field}"
                            )

    def _is_valid_uuid(self, value: str) -> bool:
        """Check if a string is a valid UUID."""
        if not isinstance(value, str):
            return False
        return bool(self.UUID_PATTERN.match(value))


def validate_insait_json(json_data: dict | str) -> ValidationReport:
    """
    Validate JSON against INSAIT platform schema.

    Args:
        json_data: JSON data as dict or string

    Returns:
        ValidationReport with all issues found
    """
    validator = INSAITValidator()
    return validator.validate(json_data)


def validate_json_file(file_path: str) -> ValidationReport:
    """
    Validate a JSON file against INSAIT platform schema.

    Args:
        file_path: Path to the JSON file

    Returns:
        ValidationReport with all issues found
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        report = ValidationReport()
        report.add_error(
            ValidationCategory.STRUCTURAL,
            f"File not found: {file_path}"
        )
        return report
    except Exception as e:
        report = ValidationReport()
        report.add_error(
            ValidationCategory.STRUCTURAL,
            f"Error reading file: {e}"
        )
        return report

    return validate_insait_json(content)
