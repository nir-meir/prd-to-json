"""
Auto-Fixer - Automatically fix common validation issues.

Handles:
- Missing default fields
- Orphaned nodes (connect or remove)
- Invalid references
- Missing start/end nodes
"""

from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from copy import deepcopy

from .json_validator import ValidationResult, ValidationIssue, ValidationSeverity
from ..utils.id_generator import generate_uuid
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FixResult:
    """Result of auto-fix operation."""
    success: bool
    fixed_data: Optional[Dict[str, Any]] = None
    fixes_applied: List[str] = field(default_factory=list)
    fixes_failed: List[str] = field(default_factory=list)
    remaining_issues: List[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "fixes_applied_count": len(self.fixes_applied),
            "fixes_applied": self.fixes_applied,
            "fixes_failed": self.fixes_failed,
            "remaining_issues_count": len(self.remaining_issues),
        }


class AutoFixer:
    """
    Automatic fixer for INSAIT JSON validation issues.

    Attempts to fix issues marked as auto_fixable by the validator.
    """

    def __init__(
        self,
        remove_orphans: bool = False,
        add_default_end: bool = True,
        fix_missing_prompts: bool = True,
    ):
        """
        Initialize auto-fixer.

        Args:
            remove_orphans: If True, remove orphaned nodes. If False, try to connect them.
            add_default_end: Add default end node if missing
            fix_missing_prompts: Add default prompts to collect nodes
        """
        self.remove_orphans = remove_orphans
        self.add_default_end = add_default_end
        self.fix_missing_prompts = fix_missing_prompts

    def fix(
        self,
        json_data: Dict[str, Any],
        validation_result: ValidationResult
    ) -> FixResult:
        """
        Attempt to fix validation issues.

        Args:
            json_data: The JSON data to fix
            validation_result: Validation result with issues to fix

        Returns:
            FixResult with fixed data and applied fixes
        """
        # Work on a copy
        data = deepcopy(json_data)
        fixes_applied = []
        fixes_failed = []

        # Get auto-fixable issues
        fixable = [i for i in validation_result.issues if i.auto_fixable]

        logger.info(f"Attempting to fix {len(fixable)} auto-fixable issues")

        for issue in fixable:
            try:
                fixed = self._fix_issue(data, issue)
                if fixed:
                    fixes_applied.append(f"{issue.code}: {issue.message}")
                else:
                    fixes_failed.append(f"{issue.code}: Could not fix")
            except Exception as e:
                fixes_failed.append(f"{issue.code}: Error - {e}")
                logger.warning(f"Failed to fix {issue.code}: {e}")

        # Re-validate to get remaining issues
        from .json_validator import INSAITValidator
        validator = INSAITValidator()
        new_result = validator.validate(data)

        return FixResult(
            success=new_result.valid,
            fixed_data=data,
            fixes_applied=fixes_applied,
            fixes_failed=fixes_failed,
            remaining_issues=new_result.issues,
        )

    def _fix_issue(self, data: Dict[str, Any], issue: ValidationIssue) -> bool:
        """
        Fix a single issue.

        Args:
            data: JSON data to modify
            issue: Issue to fix

        Returns:
            True if fixed successfully
        """
        code = issue.code

        if code == "MISSING_NODE_FIELD":
            return self._fix_missing_node_field(data, issue)
        elif code == "EMPTY_NODE_ID":
            return self._fix_empty_node_id(data, issue)
        elif code == "COLLECT_NO_PROMPT":
            return self._fix_collect_prompt(data, issue)
        elif code == "INVALID_START_NODE":
            return self._fix_invalid_start_node(data, issue)
        elif code == "ORPHANED_NODE":
            return self._fix_orphaned_node(data, issue)
        elif code == "DEAD_END_NODE":
            return self._fix_dead_end_node(data, issue)
        elif code == "NO_START_NODE":
            return self._fix_no_start_node(data, issue)
        elif code == "NO_END_NODE":
            return self._fix_no_end_node(data, issue)
        elif code == "MISSING_FLOW_FIELD":
            return self._fix_missing_flow_field(data, issue)

        return False

    def _fix_missing_node_field(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix missing node field with default value."""
        field = issue.context.get("field")
        node_type = issue.context.get("node_type")

        if not field:
            return False

        # Navigate to node
        path_parts = issue.path.split(".")
        node = self._navigate_to_parent(data, path_parts[:-1])

        if not node:
            return False

        # Add default value
        if field == "position":
            node["position"] = {"x": 0, "y": 0}
        elif field == "data":
            node["data"] = {}
        else:
            return False

        return True

    def _fix_empty_node_id(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix empty node ID by generating a new one."""
        path_parts = issue.path.split(".")
        node = self._navigate_to_parent(data, path_parts[:-1])

        if not node:
            return False

        new_id = generate_uuid()
        old_id = node.get("id", "")
        node["id"] = new_id

        # Update any references to this node
        flow = data.get("flow", {})
        if old_id and flow.get("start_node_id") == old_id:
            flow["start_node_id"] = new_id

        # Update exits
        for exit_data in flow.get("exits", []):
            if exit_data.get("source_node_id") == old_id:
                exit_data["source_node_id"] = new_id
            if exit_data.get("target_node_id") == old_id:
                exit_data["target_node_id"] = new_id
            if exit_data.get("source") == old_id:
                exit_data["source"] = new_id
            if exit_data.get("target") == old_id:
                exit_data["target"] = new_id

        return True

    def _fix_collect_prompt(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix missing collect prompt."""
        if not self.fix_missing_prompts:
            return False

        path_parts = issue.path.split(".")
        node_data = self._navigate_to_parent(data, path_parts[:-1])

        if not node_data:
            return False

        var_name = node_data.get("variable_name", "input")
        node_data["prompt"] = f"Please provide your {var_name.replace('_', ' ')}"
        return True

    def _fix_invalid_start_node(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix invalid start_node_id by finding a start node."""
        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})

        # Find a start node
        start_id = None
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if node.get("type") == "start":
                    start_id = node_id
                    break
            if not start_id and nodes:
                # Use first node as start
                start_id = list(nodes.keys())[0]
        elif isinstance(nodes, list):
            for node in nodes:
                if node.get("type") == "start":
                    start_id = node.get("id")
                    break
            if not start_id and nodes:
                start_id = nodes[0].get("id")

        if start_id:
            flow["start_node_id"] = start_id
            return True

        return False

    def _fix_orphaned_node(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix orphaned node by connecting or removing it."""
        node_id = issue.context.get("node_id")
        if not node_id:
            return False

        if self.remove_orphans:
            return self._remove_node(data, node_id)
        else:
            return self._connect_orphan(data, node_id)

    def _remove_node(self, data: Dict[str, Any], node_id: str) -> bool:
        """Remove a node from the flow."""
        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})

        if isinstance(nodes, dict) and node_id in nodes:
            del nodes[node_id]

            # Remove exits referencing this node
            exits = flow.get("exits", [])
            flow["exits"] = [
                e for e in exits
                if e.get("source_node_id") != node_id
                and e.get("target_node_id") != node_id
                and e.get("source") != node_id
                and e.get("target") != node_id
            ]
            return True

        return False

    def _connect_orphan(self, data: Dict[str, Any], node_id: str) -> bool:
        """Connect orphan node to the flow."""
        flow = data.get("flow", {})
        start_id = flow.get("start_node_id")

        if not start_id:
            return False

        # Add exit from start to this node
        exits = flow.setdefault("exits", [])
        exits.append({
            "id": generate_uuid(),
            "source_node_id": start_id,
            "target_node_id": node_id,
            "name": f"To {node_id[:8]}",
            "priority": len(exits),
            "condition": {"type": "always"},
        })

        return True

    def _fix_dead_end_node(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix dead-end node by connecting to an end node."""
        node_id = issue.context.get("node_id")
        if not node_id:
            return False

        flow = data.get("flow", {})
        nodes = flow.get("nodes", {})

        # Find an end node
        end_id = None
        if isinstance(nodes, dict):
            for nid, node in nodes.items():
                if node.get("type") == "end":
                    end_id = nid
                    break

        if not end_id:
            # Create an end node
            end_id = generate_uuid()
            if isinstance(nodes, dict):
                nodes[end_id] = {
                    "id": end_id,
                    "type": "end",
                    "name": "Auto End",
                    "position": {"x": 0, "y": 0},
                    "data": {"end_type": "end_call", "message": "Goodbye"},
                }

        # Connect dead-end to end node
        exits = flow.setdefault("exits", [])
        exits.append({
            "id": generate_uuid(),
            "source_node_id": node_id,
            "target_node_id": end_id,
            "name": "End",
            "priority": len(exits),
            "condition": {"type": "always"},
        })

        return True

    def _fix_no_start_node(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Add a start node if missing."""
        flow = data.setdefault("flow", {})
        nodes = flow.setdefault("nodes", {})

        start_id = generate_uuid()
        start_node = {
            "id": start_id,
            "type": "start",
            "name": "Start",
            "position": {"x": 100, "y": 100},
            "data": {
                "initial_message": "Welcome",
                "system_prompt": "",
            },
        }

        if isinstance(nodes, dict):
            nodes[start_id] = start_node
        elif isinstance(nodes, list):
            nodes.insert(0, start_node)

        flow["start_node_id"] = start_id
        return True

    def _fix_no_end_node(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Add an end node if missing."""
        if not self.add_default_end:
            return False

        flow = data.setdefault("flow", {})
        nodes = flow.setdefault("nodes", {})

        end_id = generate_uuid()
        end_node = {
            "id": end_id,
            "type": "end",
            "name": "End",
            "position": {"x": 500, "y": 100},
            "data": {
                "end_type": "end_call",
                "message": "Goodbye",
            },
        }

        if isinstance(nodes, dict):
            nodes[end_id] = end_node
        elif isinstance(nodes, list):
            nodes.append(end_node)

        return True

    def _fix_missing_flow_field(
        self,
        data: Dict[str, Any],
        issue: ValidationIssue
    ) -> bool:
        """Fix missing flow field."""
        field = issue.path.split(".")[-1]
        flow = data.setdefault("flow", {})

        if field == "start_node_id":
            return self._fix_invalid_start_node(data, issue)
        elif field == "nodes":
            flow["nodes"] = {}
            return True
        elif field == "exits":
            flow["exits"] = []
            return True

        return False

    def _navigate_to_parent(
        self,
        data: Dict[str, Any],
        path_parts: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Navigate to a JSON path and return the parent object."""
        current = data

        for part in path_parts:
            if part.startswith("$"):
                continue

            # Handle array notation
            if "[" in part:
                key = part.split("[")[0]
                index = int(part.split("[")[1].rstrip("]"))
                current = current.get(key, [])
                if isinstance(current, list) and index < len(current):
                    current = current[index]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

            if current is None:
                return None

        return current
