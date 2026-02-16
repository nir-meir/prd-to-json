"""
Utilities module - Common helper functions and classes.
"""

from .id_generator import (
    generate_uuid,
    generate_node_id,
    generate_exit_id,
    to_kebab_case,
    to_snake_case,
    sanitize_id,
    generate_unique_id,
    extract_feature_id,
    extract_user_story_id,
    IDGenerator,
)
from .logger import (
    setup_logging,
    get_logger,
    LogContext,
    ProgressLogger,
    log_exception,
    log_json,
)

__all__ = [
    # ID generation
    'generate_uuid',
    'generate_node_id',
    'generate_exit_id',
    'to_kebab_case',
    'to_snake_case',
    'sanitize_id',
    'generate_unique_id',
    'extract_feature_id',
    'extract_user_story_id',
    'IDGenerator',
    # Logging
    'setup_logging',
    'get_logger',
    'LogContext',
    'ProgressLogger',
    'log_exception',
    'log_json',
]
