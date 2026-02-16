"""
Validator module - Validate and auto-fix INSAIT JSON output.

Provides:
- INSAITValidator: Validates JSON against INSAIT schema
- AutoFixer: Automatically fixes common validation issues
"""

from .json_validator import (
    INSAITValidator,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
)
from .auto_fixer import AutoFixer, FixResult

__all__ = [
    'INSAITValidator',
    'ValidationResult',
    'ValidationIssue',
    'ValidationSeverity',
    'AutoFixer',
    'FixResult',
]


def validate_and_fix(
    json_data: dict,
    strict_mode: bool = False,
    auto_fix: bool = True,
) -> tuple:
    """
    Convenience function to validate and optionally fix JSON data.

    Args:
        json_data: The JSON data to validate
        strict_mode: If True, treat warnings as errors
        auto_fix: If True, attempt to fix issues

    Returns:
        Tuple of (validation_result, fixed_data or None)
    """
    validator = INSAITValidator(strict_mode=strict_mode)
    result = validator.validate(json_data)

    if not result.valid and auto_fix and result.auto_fixable_count > 0:
        fixer = AutoFixer()
        fix_result = fixer.fix(json_data, result)
        return fix_result.remaining_issues, fix_result.fixed_data

    return result, json_data if result.valid else None
