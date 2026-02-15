"""
PRD Validator - Validates PRD files before generation.

Performs basic validation checks on PRD content to ensure
it contains the necessary information for JSON generation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


class PRDValidator:
    """
    Validator for PRD (Product Requirements Document) files.

    Checks that PRD files exist, are readable, and contain
    the minimum required content for agent generation.
    """

    # Minimum content length (in characters)
    MIN_CONTENT_LENGTH = 50

    # Keywords that indicate agent description
    AGENT_KEYWORDS = [
        'agent', 'assistant', 'bot', 'ai', 'system',
        'purpose', 'goal', 'objective', 'role'
    ]

    # Keywords that indicate flow/process description
    FLOW_KEYWORDS = [
        'flow', 'step', 'process', 'workflow', 'sequence',
        'when', 'then', 'if', 'after', 'before', 'next',
        'trigger', 'action', 'response', 'handle'
    ]

    def validate_file(self, file_path: str | Path) -> ValidationResult:
        """
        Validate a PRD file.

        Args:
            file_path: Path to the PRD file

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        # Check file is readable
        if not path.is_file():
            result.add_error(f"Not a file: {file_path}")
            return result

        # Try to read the file
        try:
            content = path.read_text(encoding='utf-8')
        except PermissionError:
            result.add_error(f"Permission denied: Cannot read {file_path}")
            return result
        except UnicodeDecodeError:
            result.add_error(f"Invalid encoding: File must be UTF-8 encoded")
            return result
        except Exception as e:
            result.add_error(f"Error reading file: {e}")
            return result

        # Validate content
        self._validate_content(content, result)

        return result

    def validate_content(self, content: str) -> ValidationResult:
        """
        Validate PRD content directly.

        Args:
            content: PRD text content

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)
        self._validate_content(content, result)
        return result

    def _validate_content(self, content: str, result: ValidationResult) -> None:
        """
        Internal method to validate PRD content.

        Args:
            content: PRD text content
            result: ValidationResult to populate
        """
        # Check for empty content
        if not content or not content.strip():
            result.add_error("PRD file is empty")
            return

        content_lower = content.lower()

        # Check minimum length
        if len(content.strip()) < self.MIN_CONTENT_LENGTH:
            result.add_error(
                f"PRD content too short ({len(content.strip())} chars). "
                f"Minimum {self.MIN_CONTENT_LENGTH} characters required."
            )
            return

        # Check for agent description
        has_agent_keywords = any(
            keyword in content_lower
            for keyword in self.AGENT_KEYWORDS
        )
        if not has_agent_keywords:
            result.add_warning(
                "PRD may be missing agent description. "
                "Consider adding: purpose, role, or goal of the agent."
            )

        # Check for flow description
        has_flow_keywords = any(
            keyword in content_lower
            for keyword in self.FLOW_KEYWORDS
        )
        if not has_flow_keywords:
            result.add_warning(
                "PRD may be missing flow/process description. "
                "Consider adding: steps, triggers, or workflow details."
            )

        # Check for extremely long content (might exceed token limits)
        if len(content) > 50000:
            result.add_warning(
                f"PRD is very long ({len(content)} chars). "
                "Consider splitting into smaller documents."
            )

        # Check for potential issues
        if '```' in content:
            result.add_warning(
                "PRD contains code blocks. Ensure they represent "
                "expected behavior, not implementation details."
            )


def validate_prd_file(file_path: str | Path) -> ValidationResult:
    """
    Convenience function to validate a PRD file.

    Args:
        file_path: Path to the PRD file

    Returns:
        ValidationResult with errors and warnings
    """
    validator = PRDValidator()
    return validator.validate_file(file_path)


def validate_prd_content(content: str) -> ValidationResult:
    """
    Convenience function to validate PRD content.

    Args:
        content: PRD text content

    Returns:
        ValidationResult with errors and warnings
    """
    validator = PRDValidator()
    return validator.validate_content(content)
