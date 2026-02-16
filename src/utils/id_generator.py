"""
ID Generator utilities for creating unique identifiers.

Provides functions for generating UUIDs, node IDs, and other
identifiers used throughout the INSAIT JSON structure.
"""

import uuid
import re
from typing import Set, Optional


def generate_uuid() -> str:
    """
    Generate a random UUID.

    Returns:
        UUID string in format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    """
    return str(uuid.uuid4())


def generate_node_id(prefix: str, counter: int) -> str:
    """
    Generate a node ID with the given prefix and counter.

    Args:
        prefix: Node type prefix (e.g., "start", "collect", "api")
        counter: Counter value for uniqueness

    Returns:
        Node ID in kebab-case (e.g., "collect-user-info-0")
    """
    # Ensure prefix is kebab-case
    prefix = to_kebab_case(prefix)
    return f"{prefix}-{counter}"


def generate_exit_id(source_id: str, target_id: str, counter: Optional[int] = None) -> str:
    """
    Generate an exit ID connecting two nodes.

    Args:
        source_id: Source node ID
        target_id: Target node ID
        counter: Optional counter for disambiguation

    Returns:
        Exit ID (e.g., "exit-start-node-to-collect-name")
    """
    base_id = f"exit-{source_id}-to-{target_id}"
    if counter is not None:
        return f"{base_id}-{counter}"
    return base_id


def to_kebab_case(text: str) -> str:
    """
    Convert text to kebab-case.

    Args:
        text: Input text (can be camelCase, PascalCase, snake_case, or space-separated)

    Returns:
        kebab-case string
    """
    # Handle empty string
    if not text:
        return ""

    # Replace underscores and spaces with hyphens
    text = text.replace("_", "-").replace(" ", "-")

    # Insert hyphen before uppercase letters (for camelCase/PascalCase)
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', text)

    # Convert to lowercase
    text = text.lower()

    # Remove any double hyphens
    text = re.sub(r'-+', '-', text)

    # Remove leading/trailing hyphens
    text = text.strip('-')

    return text


def to_snake_case(text: str) -> str:
    """
    Convert text to snake_case.

    Args:
        text: Input text

    Returns:
        snake_case string
    """
    # First convert to kebab-case, then replace hyphens with underscores
    return to_kebab_case(text).replace("-", "_")


def sanitize_id(text: str) -> str:
    """
    Sanitize text to be used as an ID.

    Removes special characters, converts to lowercase, and ensures
    the ID is valid for use in JSON keys.

    Args:
        text: Input text

    Returns:
        Sanitized ID string
    """
    # Convert to kebab-case first
    text = to_kebab_case(text)

    # Remove any characters that aren't alphanumeric or hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)

    # Ensure it doesn't start with a number
    if text and text[0].isdigit():
        text = f"id-{text}"

    return text or "unnamed"


def generate_unique_id(prefix: str, existing_ids: Set[str]) -> str:
    """
    Generate a unique ID that doesn't exist in the given set.

    Args:
        prefix: ID prefix
        existing_ids: Set of existing IDs to avoid

    Returns:
        Unique ID string
    """
    prefix = to_kebab_case(prefix)

    # Try without counter first
    if prefix not in existing_ids:
        return prefix

    # Add counter until unique
    counter = 1
    while True:
        new_id = f"{prefix}-{counter}"
        if new_id not in existing_ids:
            return new_id
        counter += 1


def extract_feature_id(text: str) -> Optional[str]:
    """
    Extract a feature ID from text (e.g., "F-01", "Feature 1").

    Args:
        text: Text potentially containing a feature ID

    Returns:
        Extracted feature ID or None
    """
    # Try F-XX format
    match = re.search(r'F-?(\d+)', text, re.IGNORECASE)
    if match:
        num = int(match.group(1))
        return f"F-{num:02d}"

    # Try "Feature X" format
    match = re.search(r'Feature\s*(\d+)', text, re.IGNORECASE)
    if match:
        num = int(match.group(1))
        return f"F-{num:02d}"

    return None


def extract_user_story_id(text: str) -> Optional[str]:
    """
    Extract a user story ID from text (e.g., "US-001", "User Story 1").

    Args:
        text: Text potentially containing a user story ID

    Returns:
        Extracted user story ID or None
    """
    # Try US-XXX format
    match = re.search(r'US-?(\d+)', text, re.IGNORECASE)
    if match:
        num = int(match.group(1))
        return f"US-{num:03d}"

    # Try "User Story X" format
    match = re.search(r'User\s*Story\s*(\d+)', text, re.IGNORECASE)
    if match:
        num = int(match.group(1))
        return f"US-{num:03d}"

    return None


class IDGenerator:
    """
    Stateful ID generator for tracking used IDs during generation.

    Use this class when you need to generate multiple unique IDs
    while keeping track of what's been used.
    """

    def __init__(self):
        self._used_node_ids: Set[str] = set()
        self._used_exit_ids: Set[str] = set()
        self._used_tool_ids: Set[str] = set()
        self._counters: dict = {}

    def node_id(self, prefix: str) -> str:
        """Generate a unique node ID with the given prefix."""
        prefix = to_kebab_case(prefix)

        if prefix not in self._counters:
            self._counters[prefix] = 0

        while True:
            node_id = f"{prefix}-{self._counters[prefix]}"
            self._counters[prefix] += 1
            if node_id not in self._used_node_ids:
                self._used_node_ids.add(node_id)
                return node_id

    def exit_id(self, source_id: str, target_id: str) -> str:
        """Generate a unique exit ID."""
        base_id = f"exit-{source_id}-to-{target_id}"

        if base_id not in self._used_exit_ids:
            self._used_exit_ids.add(base_id)
            return base_id

        counter = 1
        while True:
            exit_id = f"{base_id}-{counter}"
            if exit_id not in self._used_exit_ids:
                self._used_exit_ids.add(exit_id)
                return exit_id
            counter += 1

    def tool_id(self) -> str:
        """Generate a unique tool ID (UUID)."""
        while True:
            tool_id = generate_uuid()
            if tool_id not in self._used_tool_ids:
                self._used_tool_ids.add(tool_id)
                return tool_id

    def reserve_node_id(self, node_id: str) -> bool:
        """Reserve a specific node ID."""
        if node_id in self._used_node_ids:
            return False
        self._used_node_ids.add(node_id)
        return True

    def is_node_id_used(self, node_id: str) -> bool:
        """Check if a node ID is already used."""
        return node_id in self._used_node_ids

    def reset(self) -> None:
        """Reset all tracking."""
        self._used_node_ids.clear()
        self._used_exit_ids.clear()
        self._used_tool_ids.clear()
        self._counters.clear()
