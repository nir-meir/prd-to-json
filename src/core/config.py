"""
Configuration management for PRD-to-JSON generator.

Provides dataclasses for all configuration options with sensible defaults,
YAML file loading, and validation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum
import os
import yaml


class LLMProvider(Enum):
    """Supported LLM providers."""
    BEDROCK = "bedrock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"  # For testing


class GenerationStrategy(Enum):
    """Available generation strategies."""
    AUTO = "auto"           # Auto-select based on complexity
    SIMPLE = "simple"       # Single-pass generation
    CHUNKED = "chunked"     # Feature-by-feature
    HYBRID = "hybrid"       # Template + LLM combination


class OrphanNodeHandling(Enum):
    """How to handle orphaned nodes during auto-fix."""
    REMOVE = "remove"
    CONNECT = "connect"


@dataclass
class LLMConfig:
    """Configuration for LLM interaction."""
    provider: LLMProvider = LLMProvider.BEDROCK
    model: str = field(default_factory=lambda: os.getenv(
        "BEDROCK_MODEL",
        "anthropic.claude-sonnet-4-20250514-v1:0"
    ))
    temperature: float = 0.3
    max_tokens: int = 64000
    timeout: int = 300  # seconds

    # AWS-specific
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))

    # Retry settings
    max_retries: int = 2
    retry_delay: float = 1.0  # seconds

    def __post_init__(self):
        if isinstance(self.provider, str):
            self.provider = LLMProvider(self.provider)


@dataclass
class StrategyConfig:
    """Configuration for generation strategy selection."""
    auto_select: bool = True
    default_strategy: GenerationStrategy = GenerationStrategy.AUTO

    # Complexity thresholds for auto-selection
    simple_max_features: int = 3
    simple_max_estimated_nodes: int = 10
    medium_max_features: int = 10
    medium_max_estimated_nodes: int = 50

    # Strategy-specific settings
    chunk_size: int = 5  # Features per chunk in chunked strategy

    def __post_init__(self):
        if isinstance(self.default_strategy, str):
            self.default_strategy = GenerationStrategy(self.default_strategy)


@dataclass
class OutputConfig:
    """Configuration for output formatting."""
    pretty_print: bool = True
    indent: int = 2
    sort_keys: bool = False
    ensure_ascii: bool = False


@dataclass
class GenerationConfig:
    """Main configuration for JSON generation."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # INSAIT defaults
    default_channel: str = "voice"
    default_language: str = "en-US"
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"


@dataclass
class AutoFixConfig:
    """Configuration for auto-fix behavior."""
    enabled: bool = True
    max_iterations: int = 3
    fix_missing_fields: bool = True
    fix_invalid_refs: bool = True
    fix_orphaned_nodes: bool = True
    fix_extract_fields: bool = True
    fix_variable_sources: bool = True
    orphan_handling: OrphanNodeHandling = OrphanNodeHandling.CONNECT

    def __post_init__(self):
        if isinstance(self.orphan_handling, str):
            self.orphan_handling = OrphanNodeHandling(self.orphan_handling)


@dataclass
class ValidationConfig:
    """Configuration for validation behavior."""
    auto_fix: AutoFixConfig = field(default_factory=AutoFixConfig)
    strict_mode: bool = False
    warn_on_missing_descriptions: bool = True
    require_all_paths_to_end: bool = True
    validate_node_positions: bool = False  # Position validation optional


@dataclass
class TemplateConfig:
    """Configuration for template matching and usage."""
    enabled: bool = True
    min_match_score: float = 0.7  # Minimum score to use a template
    prefer_templates: bool = True  # Prefer templates over LLM generation
    custom_templates_dir: Optional[Path] = None

    def __post_init__(self):
        if self.custom_templates_dir and isinstance(self.custom_templates_dir, str):
            self.custom_templates_dir = Path(self.custom_templates_dir)


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file: Optional[Path] = None

    def __post_init__(self):
        if self.file and isinstance(self.file, str):
            self.file = Path(self.file)


@dataclass
class AppConfig:
    """
    Root configuration object containing all settings.

    Can be loaded from YAML file or constructed programmatically.
    """
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path | str) -> 'AppConfig':
        """
        Load configuration from a YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            AppConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """
        Create configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            AppConfig instance
        """
        generation_data = data.get('generation', {})
        validation_data = data.get('validation', {})
        templates_data = data.get('templates', {})
        logging_data = data.get('logging', {})

        # Build nested configs
        generation = GenerationConfig(
            llm=LLMConfig(**generation_data.get('llm', {})),
            strategy=StrategyConfig(**generation_data.get('strategy', {})),
            output=OutputConfig(**generation_data.get('output', {})),
            default_channel=generation_data.get('default_channel', 'voice'),
            default_language=generation_data.get('default_language', 'en-US'),
            default_llm_provider=generation_data.get('default_llm_provider', 'openai'),
            default_llm_model=generation_data.get('default_llm_model', 'gpt-4o'),
        )

        validation = ValidationConfig(
            auto_fix=AutoFixConfig(**validation_data.get('auto_fix', {})),
            strict_mode=validation_data.get('strict_mode', False),
            warn_on_missing_descriptions=validation_data.get('warn_on_missing_descriptions', True),
            require_all_paths_to_end=validation_data.get('require_all_paths_to_end', True),
            validate_node_positions=validation_data.get('validate_node_positions', False),
        )

        templates = TemplateConfig(**templates_data)
        logging = LoggingConfig(**logging_data)

        return cls(
            generation=generation,
            validation=validation,
            templates=templates,
            logging=logging,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to a dictionary.

        Returns:
            Configuration as dictionary
        """
        return {
            'generation': {
                'llm': {
                    'provider': self.generation.llm.provider.value,
                    'model': self.generation.llm.model,
                    'temperature': self.generation.llm.temperature,
                    'max_tokens': self.generation.llm.max_tokens,
                    'timeout': self.generation.llm.timeout,
                    'aws_region': self.generation.llm.aws_region,
                    'max_retries': self.generation.llm.max_retries,
                    'retry_delay': self.generation.llm.retry_delay,
                },
                'strategy': {
                    'auto_select': self.generation.strategy.auto_select,
                    'default_strategy': self.generation.strategy.default_strategy.value,
                    'simple_max_features': self.generation.strategy.simple_max_features,
                    'simple_max_estimated_nodes': self.generation.strategy.simple_max_estimated_nodes,
                    'medium_max_features': self.generation.strategy.medium_max_features,
                    'medium_max_estimated_nodes': self.generation.strategy.medium_max_estimated_nodes,
                    'chunk_size': self.generation.strategy.chunk_size,
                },
                'output': {
                    'pretty_print': self.generation.output.pretty_print,
                    'indent': self.generation.output.indent,
                    'sort_keys': self.generation.output.sort_keys,
                    'ensure_ascii': self.generation.output.ensure_ascii,
                },
                'default_channel': self.generation.default_channel,
                'default_language': self.generation.default_language,
                'default_llm_provider': self.generation.default_llm_provider,
                'default_llm_model': self.generation.default_llm_model,
            },
            'validation': {
                'auto_fix': {
                    'enabled': self.validation.auto_fix.enabled,
                    'max_iterations': self.validation.auto_fix.max_iterations,
                    'fix_missing_fields': self.validation.auto_fix.fix_missing_fields,
                    'fix_invalid_refs': self.validation.auto_fix.fix_invalid_refs,
                    'fix_orphaned_nodes': self.validation.auto_fix.fix_orphaned_nodes,
                    'fix_extract_fields': self.validation.auto_fix.fix_extract_fields,
                    'fix_variable_sources': self.validation.auto_fix.fix_variable_sources,
                    'orphan_handling': self.validation.auto_fix.orphan_handling.value,
                },
                'strict_mode': self.validation.strict_mode,
                'warn_on_missing_descriptions': self.validation.warn_on_missing_descriptions,
                'require_all_paths_to_end': self.validation.require_all_paths_to_end,
                'validate_node_positions': self.validation.validate_node_positions,
            },
            'templates': {
                'enabled': self.templates.enabled,
                'min_match_score': self.templates.min_match_score,
                'prefer_templates': self.templates.prefer_templates,
                'custom_templates_dir': str(self.templates.custom_templates_dir) if self.templates.custom_templates_dir else None,
            },
            'logging': {
                'level': self.logging.level,
                'format': self.logging.format,
                'file': str(self.logging.file) if self.logging.file else None,
            },
        }

    def save_yaml(self, path: Path | str) -> None:
        """
        Save configuration to a YAML file.

        Args:
            path: Path to output YAML file
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)


def get_default_config() -> AppConfig:
    """
    Get the default application configuration.

    Returns:
        AppConfig with all default values
    """
    return AppConfig()


def load_config(config_path: Optional[Path | str] = None) -> AppConfig:
    """
    Load configuration from file or return defaults.

    Looks for config in this order:
    1. Provided path
    2. ./config/default.yaml
    3. Default values

    Args:
        config_path: Optional path to config file

    Returns:
        AppConfig instance
    """
    if config_path:
        return AppConfig.from_yaml(config_path)

    # Try default locations
    default_paths = [
        Path("config/default.yaml"),
        Path("config.yaml"),
        Path.home() / ".prdtojson" / "config.yaml",
    ]

    for path in default_paths:
        if path.exists():
            return AppConfig.from_yaml(path)

    return get_default_config()
