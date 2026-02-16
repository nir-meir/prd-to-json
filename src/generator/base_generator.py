"""
Base Generator - Abstract base class for JSON generation strategies.

Defines the interface for converting ParsedPRD to INSAIT JSON format.
Different strategies implement different approaches based on PRD complexity.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..parser.models import ParsedPRD, Feature, Variable, APIEndpoint
from ..core.context import GenerationContext
from ..core.config import AppConfig
from ..llm.base import BaseLLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class GenerationStrategy(Enum):
    """Available generation strategies."""
    SIMPLE = "simple"
    CHUNKED = "chunked"
    HYBRID = "hybrid"


@dataclass
class GenerationResult:
    """Result of JSON generation."""
    success: bool
    json_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        """Convert result to JSON-serializable dict."""
        return {
            "success": self.success,
            "json_output": self.json_output,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "stats": self.stats,
        }


class BaseGenerator(ABC):
    """
    Abstract base class for JSON generators.

    Generators convert ParsedPRD objects into INSAIT-compatible JSON format.
    Different implementations use different strategies based on PRD complexity.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        """
        Initialize the generator.

        Args:
            config: Application configuration
            llm_client: LLM client for generation assistance
        """
        self.config = config or AppConfig()
        self.llm_client = llm_client
        self._context: Optional[GenerationContext] = None

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Name of this generation strategy."""
        pass

    @property
    def context(self) -> GenerationContext:
        """Get current generation context."""
        if self._context is None:
            raise RuntimeError("Generation not started - no context available")
        return self._context

    def generate(self, parsed_prd: ParsedPRD) -> GenerationResult:
        """
        Generate INSAIT JSON from parsed PRD.

        Args:
            parsed_prd: Parsed PRD object

        Returns:
            GenerationResult with JSON output or error
        """
        logger.info(f"Starting generation with {self.strategy_name} strategy")

        try:
            # Initialize context
            self._context = GenerationContext(
                parsed_prd=parsed_prd,
                config=self.config,
            )

            # Pre-generation setup
            self._setup(parsed_prd)

            # Run strategy-specific generation
            json_output = self._generate(parsed_prd)

            # Post-generation cleanup
            self._finalize()

            # Build result
            return GenerationResult(
                success=True,
                json_output=json_output,
                warnings=self._context.warnings,
                stats={
                    "strategy": self.strategy_name,
                    "node_count": len(self._context.nodes),
                    "exit_count": len(self._context.exits),
                    "tool_count": len(self._context.tools),
                    "variable_count": len(self._context.variables_json),
                },
            )

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return GenerationResult(
                success=False,
                error_message=str(e),
                warnings=self._context.warnings if self._context else [],
            )

    @abstractmethod
    def _generate(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """
        Strategy-specific generation implementation.

        Args:
            parsed_prd: Parsed PRD object

        Returns:
            INSAIT JSON structure
        """
        pass

    def _setup(self, parsed_prd: ParsedPRD) -> None:
        """
        Pre-generation setup.

        Override in subclasses for custom setup logic.
        """
        logger.debug(f"Setting up {self.strategy_name} generator")

    def _finalize(self) -> None:
        """
        Post-generation finalization.

        Override in subclasses for custom cleanup logic.
        """
        logger.debug(f"Finalizing {self.strategy_name} generation")

    def _build_agent_json(self) -> Dict[str, Any]:
        """
        Build the complete INSAIT agent JSON structure.

        Returns:
            Complete agent JSON
        """
        metadata = self.context.parsed_prd.metadata
        flow_json = self.context.get_flow_json()

        return {
            "name": metadata.name,
            "description": metadata.description,
            "agent_language": metadata.language,
            "flow": flow_json,
            "tools": self.context.get_tools_json(),
            "variables": self.context.get_variables_json(),
            "settings": self._build_settings(),
        }

    def _build_settings(self) -> Dict[str, Any]:
        """Build agent settings section."""
        metadata = self.context.parsed_prd.metadata

        return {
            "version": metadata.version,
            "phase": metadata.phase,
            "created_by": "PRD-to-JSON Generator",
        }


def select_strategy(parsed_prd: ParsedPRD, config: AppConfig) -> GenerationStrategy:
    """
    Select the best generation strategy based on PRD complexity.

    Args:
        parsed_prd: Parsed PRD to analyze
        config: Application configuration

    Returns:
        Recommended generation strategy
    """
    from ..parser.models import Complexity

    complexity = parsed_prd.complexity
    strategy_config = config.generation.strategy

    if complexity == Complexity.SIMPLE:
        return GenerationStrategy.SIMPLE
    elif complexity == Complexity.MEDIUM:
        # Check if we should use chunked or simple
        if parsed_prd.estimated_node_count > strategy_config.simple_max_estimated_nodes:
            return GenerationStrategy.CHUNKED
        return GenerationStrategy.SIMPLE
    elif complexity in (Complexity.COMPLEX, Complexity.ENTERPRISE):
        return GenerationStrategy.HYBRID

    return GenerationStrategy.HYBRID  # Default to hybrid for unknown
