"""
Core module - Contains foundational classes and pipeline orchestration.
"""

from .config import (
    GenerationConfig,
    ValidationConfig,
    TemplateConfig,
    LoggingConfig,
    AppConfig,
    LLMConfig,
    StrategyConfig,
    OutputConfig,
    AutoFixConfig,
    LLMProvider,
    GenerationStrategy,
    OrphanNodeHandling,
    get_default_config,
    load_config,
)
from .context import (
    GenerationContext,
    GenerationPhase,
    NodeReference,
    ExitReference,
    ToolReference,
    GenerationStats,
)

__all__ = [
    # Config classes
    'GenerationConfig',
    'ValidationConfig',
    'TemplateConfig',
    'LoggingConfig',
    'AppConfig',
    'LLMConfig',
    'StrategyConfig',
    'OutputConfig',
    'AutoFixConfig',
    # Config enums
    'LLMProvider',
    'GenerationStrategy',
    'OrphanNodeHandling',
    # Config functions
    'get_default_config',
    'load_config',
    # Context classes
    'GenerationContext',
    'GenerationPhase',
    'NodeReference',
    'ExitReference',
    'ToolReference',
    'GenerationStats',
]
