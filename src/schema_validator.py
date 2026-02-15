"""
Schema Validator - Validates generated JSON against INSAIT platform schema.

Ensures the generated JSON has the correct structure, valid node IDs,
and properly connected exits.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SchemaValidationResult:
    """Result of schema validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


class SchemaValidator:
    """
    Validates JSON against INSAIT platform schema.

    Checks for:
    - Required top-level structure (metadata, agent, flow_definition, tools)
    - Valid node IDs (unique)
    - Valid exit references (source_node_id/target_node_id exist)
    - Required node properties
    - Proper tool structure
    """

    REQUIRED_TOP_LEVEL_KEYS = ['metadata', 'agent', 'flow_definition']
    REQUIRED_METADATA_KEYS = ['export_version', 'exported_at', 'validation_status']
    REQUIRED_AGENT_KEYS = ['name', 'description', 'channel', 'agent_mode', 'agent_language', 'is_active']
    REQUIRED_FLOW_DEFINITION_KEYS = ['id', 'name', 'version', 'channel', 'global_settings', 'flow']
    REQUIRED_FLOW_KEYS = ['start_node_id', 'nodes', 'exits']
    REQUIRED_NODE_KEYS = ['id', 'type', 'name', 'data', 'exits', 'position']
    REQUIRED_EXIT_KEYS = ['id', 'name', 'source_node_id', 'target_node_id', 'priority']
    REQUIRED_VARIABLE_KEYS = ['name', 'type', 'persist', 'source']
    REQUIRED_TOOL_KEYS = ['original_id', 'name', 'type', 'function_definition', 'execution_config']

    def validate(self, json_data: dict | str) -> SchemaValidationResult:
        """
        Validate JSON data against INSAIT schema.

        Args:
            json_data: JSON data as dict or string

        Returns:
            SchemaValidationResult with errors, warnings, and stats
        """
        result = SchemaValidationResult(is_valid=True)

        # Parse JSON if string
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except json.JSONDecodeError as e:
                result.add_error(f"Invalid JSON syntax: {e}")
                return result

        if not isinstance(json_data, dict):
            result.add_error("JSON root must be an object")
            return result

        # Validate structure
        self._validate_top_level(json_data, result)

        if not result.is_valid:
            return result

        # Validate metadata
        if 'metadata' in json_data:
            self._validate_metadata(json_data['metadata'], result)

        # Validate agent
        if 'agent' in json_data:
            self._validate_agent(json_data['agent'], result)

        # Validate flow definition
        if 'flow_definition' in json_data:
            self._validate_flow_definition(json_data['flow_definition'], result)

        # Validate top-level tools array
        if 'tools' in json_data:
            self._validate_tools(json_data['tools'], result)

        return result

    def _validate_top_level(
        self,
        data: dict,
        result: SchemaValidationResult
    ) -> None:
        """Validate top-level structure."""
        for key in self.REQUIRED_TOP_LEVEL_KEYS:
            if key not in data:
                result.add_error(f"Missing required top-level key: '{key}'")

        # Check for recommended top-level keys
        if 'tools' not in data:
            result.add_warning("Missing top-level 'tools' array")
        if 'filler_sentences' not in data:
            result.add_warning("Missing top-level 'filler_sentences' array")
        if 'nikud_replacements' not in data:
            result.add_warning("Missing top-level 'nikud_replacements' array")

    def _validate_metadata(
        self,
        metadata: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate metadata section."""
        if not isinstance(metadata, dict):
            result.add_error("'metadata' must be an object")
            return

        for key in self.REQUIRED_METADATA_KEYS:
            if key not in metadata:
                result.add_warning(f"Missing recommended metadata key: '{key}'")

        # Check export version
        export_version = metadata.get('export_version')
        if export_version and export_version != '1.1':
            result.add_warning(f"Export version '{export_version}' may not be current (expected '1.1')")

        # Record stats
        result.stats['export_version'] = metadata.get('export_version', 'Unknown')
        result.stats['validation_status'] = metadata.get('validation_status', 'Unknown')

    def _validate_agent(
        self,
        agent: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate agent section."""
        if not isinstance(agent, dict):
            result.add_error("'agent' must be an object")
            return

        for key in self.REQUIRED_AGENT_KEYS:
            if key not in agent:
                result.add_warning(f"Missing recommended agent key: '{key}'")

        # Check for webhook fields
        webhook_fields = [
            'webhook_enabled', 'webhook_endpoint_url', 'webhook_include_recording',
            'webhook_include_transcription', 'webhook_include_call_meta',
            'webhook_include_dynamic_fields'
        ]
        for field in webhook_fields:
            if field not in agent:
                result.add_warning(f"Missing agent webhook field: '{field}'")

        result.stats['agent_name'] = agent.get('name', 'Unknown')
        result.stats['channel'] = agent.get('channel', 'Unknown')

    def _validate_flow_definition(
        self,
        flow_def: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate flow_definition section."""
        if not isinstance(flow_def, dict):
            result.add_error("'flow_definition' must be an object")
            return

        for key in self.REQUIRED_FLOW_DEFINITION_KEYS:
            if key not in flow_def:
                result.add_error(f"Missing required flow_definition key: '{key}'")

        # Check for flow_definition.tools object
        if 'tools' in flow_def:
            self._validate_flow_definition_tools(flow_def['tools'], result)
        else:
            result.add_warning("Missing 'tools' object in flow_definition")

        # Validate variables
        if 'variables' in flow_def:
            self._validate_variables(flow_def['variables'], result)

        # Validate flow
        if 'flow' not in flow_def:
            return

        flow = flow_def['flow']
        if not isinstance(flow, dict):
            result.add_error("'flow_definition.flow' must be an object")
            return

        for key in self.REQUIRED_FLOW_KEYS:
            if key not in flow:
                result.add_error(f"Missing required flow key: '{key}'")

        if 'nodes' not in flow or 'exits' not in flow:
            return

        # Validate nodes (must be an OBJECT, not array)
        nodes = flow['nodes']
        if not isinstance(nodes, dict):
            result.add_error("'flow.nodes' must be an object (not an array)")
            return

        node_ids = self._validate_nodes(nodes, result)

        # Validate start_node_id reference
        start_node_id = flow.get('start_node_id')
        if start_node_id and start_node_id not in node_ids:
            result.add_error(f"'start_node_id' references non-existent node: '{start_node_id}'")

        # Validate exits
        exits = flow['exits']
        if not isinstance(exits, list):
            result.add_error("'flow.exits' must be an array")
            return

        self._validate_exits(exits, node_ids, result)

        # Record stats
        result.stats['node_count'] = len(nodes)
        result.stats['exit_count'] = len(exits)

    def _validate_flow_definition_tools(
        self,
        tools: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate flow_definition.tools object."""
        if not isinstance(tools, dict):
            result.add_error("'flow_definition.tools' must be an object")
            return

        # Check for built_in_tools
        if 'built_in_tools' not in tools:
            result.add_warning("Missing 'built_in_tools' in flow_definition.tools")
        elif isinstance(tools['built_in_tools'], dict):
            built_in = tools['built_in_tools']
            expected_tools = ['transfer_to_human', 'end_call', 'schedule_appointment']
            for tool in expected_tools:
                if tool not in built_in:
                    result.add_warning(f"Missing built-in tool setting: '{tool}'")

        if 'global_tools' not in tools:
            result.add_warning("Missing 'global_tools' in flow_definition.tools")

    def _validate_variables(
        self,
        variables: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate variables array."""
        if not isinstance(variables, list):
            result.add_error("'variables' must be an array")
            return

        var_names: set[str] = set()
        for i, var in enumerate(variables):
            if not isinstance(var, dict):
                result.add_error(f"Variable at index {i} must be an object")
                continue

            # Check required keys
            for key in self.REQUIRED_VARIABLE_KEYS:
                if key not in var:
                    result.add_warning(f"Variable at index {i} missing key: '{key}'")

            # Check for duplicate names
            var_name = var.get('name')
            if var_name:
                if var_name in var_names:
                    result.add_error(f"Duplicate variable name: '{var_name}'")
                else:
                    var_names.add(var_name)

            # Check for recommended fields
            recommended_fields = [
                'source_node_id', 'collection_mode', 'validation_rules',
                'options', 'allowed_file_types', 'max_file_size_mb'
            ]
            for field in recommended_fields:
                if field not in var:
                    result.add_warning(f"Variable '{var_name}' missing field: '{field}'")

        result.stats['variable_count'] = len(variables)

    def _validate_nodes(
        self,
        nodes: dict,
        result: SchemaValidationResult
    ) -> set[str]:
        """
        Validate nodes object.

        Returns:
            Set of valid node IDs
        """
        node_ids: set[str] = set()
        node_types: dict[str, int] = {}

        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                result.add_error(f"Node '{node_id}' must be an object")
                continue

            # Check that key matches id field
            if node.get('id') != node_id:
                result.add_warning(f"Node key '{node_id}' doesn't match id field '{node.get('id')}'")

            # Check required keys
            for key in self.REQUIRED_NODE_KEYS:
                if key not in node:
                    result.add_error(f"Node '{node_id}' missing required key: '{key}'")

            node_ids.add(node_id)

            # Track node types
            node_type = node.get('type', 'unknown')
            node_types[node_type] = node_types.get(node_type, 0) + 1

            # Validate node-specific data
            self._validate_node_data(node_id, node, result)

        result.stats['node_types'] = node_types

        # Check for start node
        start_nodes = [nid for nid, n in nodes.items() if n.get('type') == 'start']
        if not start_nodes:
            result.add_error("No 'start' node found in flow")
        elif len(start_nodes) > 1:
            result.add_warning("Multiple 'start' nodes found")

        # Check for end node
        end_nodes = [nid for nid, n in nodes.items() if n.get('type') == 'end']
        if not end_nodes:
            result.add_warning("No 'end' node found in flow")

        return node_ids

    def _validate_node_data(
        self,
        node_id: str,
        node: dict,
        result: SchemaValidationResult
    ) -> None:
        """Validate node-specific data based on type."""
        node_type = node.get('type')
        data = node.get('data', {})

        if node_type == 'start':
            required = ['greeting_message', 'use_agent_prompt']
            for key in required:
                if key not in data:
                    result.add_warning(f"Start node '{node_id}' missing data key: '{key}'")

        elif node_type == 'collect':
            if 'fields' not in data:
                result.add_error(f"Collect node '{node_id}' missing 'fields' in data")
            elif isinstance(data['fields'], list):
                for i, field in enumerate(data['fields']):
                    if not isinstance(field, dict):
                        continue
                    if 'name' not in field:
                        result.add_error(f"Collect node '{node_id}' field {i} missing 'name'")
                    if 'type' not in field:
                        result.add_error(f"Collect node '{node_id}' field {i} missing 'type'")

        elif node_type == 'conversation':
            if 'prompt' not in data:
                result.add_warning(f"Conversation node '{node_id}' missing 'prompt' in data")

        elif node_type == 'api':
            if 'tool_id' not in data:
                result.add_error(f"API node '{node_id}' missing 'tool_id' in data")

    def _validate_exits(
        self,
        exits: list,
        node_ids: set[str],
        result: SchemaValidationResult
    ) -> None:
        """Validate exits array."""
        exit_ids: set[str] = set()

        for i, exit_obj in enumerate(exits):
            if not isinstance(exit_obj, dict):
                result.add_error(f"Exit at index {i} must be an object")
                continue

            # Check required keys
            for key in self.REQUIRED_EXIT_KEYS:
                if key not in exit_obj:
                    result.add_error(f"Exit at index {i} missing required key: '{key}'")

            # Check for duplicate exit IDs
            exit_id = exit_obj.get('id')
            if exit_id:
                if exit_id in exit_ids:
                    result.add_error(f"Duplicate exit ID: '{exit_id}'")
                else:
                    exit_ids.add(exit_id)

            # Validate source_node_id reference
            source = exit_obj.get('source_node_id')
            if source and source not in node_ids:
                result.add_error(
                    f"Exit '{exit_id or i}' references non-existent "
                    f"source node: '{source}'"
                )

            # Validate target_node_id reference
            target = exit_obj.get('target_node_id')
            if target and target not in node_ids:
                result.add_error(
                    f"Exit '{exit_id or i}' references non-existent "
                    f"target node: '{target}'"
                )

            # Check condition field
            if 'condition' not in exit_obj:
                result.add_warning(f"Exit '{exit_id or i}' missing 'condition' field")

    def _validate_tools(
        self,
        tools: Any,
        result: SchemaValidationResult
    ) -> None:
        """Validate top-level tools array."""
        if not isinstance(tools, list):
            result.add_error("Top-level 'tools' must be an array")
            return

        tool_ids: set[str] = set()
        function_names: set[str] = set()

        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                result.add_error(f"Tool at index {i} must be an object")
                continue

            # Check required keys
            for key in self.REQUIRED_TOOL_KEYS:
                if key not in tool:
                    result.add_error(f"Tool at index {i} missing required key: '{key}'")

            # Check for duplicate original_id
            original_id = tool.get('original_id')
            if original_id:
                if original_id in tool_ids:
                    result.add_error(f"Duplicate tool original_id: '{original_id}'")
                else:
                    tool_ids.add(original_id)

            # Check type is http_api
            tool_type = tool.get('type')
            if tool_type and tool_type != 'http_api' and tool_type != 'internal':
                result.add_warning(f"Tool at index {i} has unexpected type: '{tool_type}' (expected 'http_api' or 'internal')")

            # Validate function_definition
            func_def = tool.get('function_definition')
            if isinstance(func_def, dict):
                func_name = func_def.get('name')
                if func_name:
                    if func_name in function_names:
                        result.add_error(f"Duplicate function name: '{func_name}'")
                    else:
                        function_names.add(func_name)
                else:
                    result.add_error(f"Tool at index {i} missing function_definition.name")

                if 'parameters' not in func_def:
                    result.add_warning(f"Tool at index {i} missing function_definition.parameters")

            # Validate execution_config
            exec_config = tool.get('execution_config')
            if isinstance(exec_config, dict):
                if 'method' not in exec_config:
                    result.add_warning(f"Tool at index {i} missing execution_config.method")
                if 'request_chain' not in exec_config:
                    result.add_warning(f"Tool at index {i} missing execution_config.request_chain")

        result.stats['tool_count'] = len(tools)
        result.stats['function_names'] = list(function_names)


def validate_json(json_data: dict | str) -> SchemaValidationResult:
    """
    Convenience function to validate JSON against INSAIT schema.

    Args:
        json_data: JSON data as dict or string

    Returns:
        SchemaValidationResult with errors, warnings, and stats
    """
    validator = SchemaValidator()
    return validator.validate(json_data)
