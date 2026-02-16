"""
Hybrid Generator - Adaptive strategy selection for any PRD complexity.

Analyzes the PRD and selects the optimal generation approach:
- Uses simple generation for straightforward features
- Uses chunked generation for complex features
- Composes results into a unified flow

Best for enterprise PRDs with mixed complexity features.
"""

from typing import Dict, Any, List, Optional, Tuple
import json

from .base_generator import BaseGenerator, GenerationResult, GenerationStrategy
from .simple_generator import SimpleGenerator
from .chunked_generator import ChunkedGenerator
from .node_factory import NodeFactory
from ..parser.models import ParsedPRD, Feature, Complexity
from ..core.context import GenerationContext
from ..core.config import AppConfig
from ..llm.base import BaseLLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class HybridGenerator(BaseGenerator):
    """
    Hybrid generator that adapts to PRD complexity.

    Analyzes features individually and generates them using the
    most appropriate strategy, then composes into a unified flow.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        super().__init__(config, llm_client)
        self._simple_generator: Optional[SimpleGenerator] = None
        self._chunked_generator: Optional[ChunkedGenerator] = None

    @property
    def strategy_name(self) -> str:
        return "hybrid"

    @property
    def simple_generator(self) -> SimpleGenerator:
        """Lazy-load simple generator."""
        if self._simple_generator is None:
            self._simple_generator = SimpleGenerator(self.config, self.llm_client)
        return self._simple_generator

    @property
    def chunked_generator(self) -> ChunkedGenerator:
        """Lazy-load chunked generator."""
        if self._chunked_generator is None:
            self._chunked_generator = ChunkedGenerator(self.config, self.llm_client)
        return self._chunked_generator

    def _generate(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """
        Generate INSAIT JSON using hybrid approach.

        Args:
            parsed_prd: Parsed PRD object

        Returns:
            INSAIT JSON structure
        """
        logger.info(f"Generating with hybrid strategy for: {parsed_prd.metadata.name}")

        # Analyze and categorize features
        simple_features, complex_features = self._categorize_features(parsed_prd)

        logger.info(f"Feature analysis: {len(simple_features)} simple, {len(complex_features)} complex")

        # Determine overall strategy
        if not complex_features:
            # All features are simple - use simple generator
            logger.info("All features simple - delegating to simple generator")
            return self._delegate_to_simple(parsed_prd)

        elif not simple_features:
            # All features are complex - use chunked generator
            logger.info("All features complex - delegating to chunked generator")
            return self._delegate_to_chunked(parsed_prd)

        else:
            # Mixed complexity - use hybrid approach
            logger.info("Mixed complexity - using hybrid composition")
            return self._generate_hybrid(parsed_prd, simple_features, complex_features)

    def _categorize_features(
        self,
        parsed_prd: ParsedPRD
    ) -> Tuple[List[Feature], List[Feature]]:
        """
        Categorize features by complexity.

        Returns:
            Tuple of (simple_features, complex_features)
        """
        simple = []
        complex_list = []

        for feature in parsed_prd.features:
            complexity = self._assess_feature_complexity(feature)
            if complexity in (Complexity.SIMPLE, Complexity.MEDIUM):
                simple.append(feature)
            else:
                complex_list.append(feature)

        return simple, complex_list

    def _assess_feature_complexity(self, feature: Feature) -> Complexity:
        """
        Assess the complexity of a single feature.

        Factors:
        - Number of flow steps
        - Number of variables used
        - Number of APIs called
        - Number of dependencies
        - Presence of conditions
        """
        score = 0

        # Flow steps
        step_count = len(feature.flow_steps)
        if step_count > 10:
            score += 3
        elif step_count > 5:
            score += 2
        elif step_count > 0:
            score += 1

        # Variables
        var_count = len(feature.variables_used)
        if var_count > 5:
            score += 2
        elif var_count > 2:
            score += 1

        # APIs
        api_count = len(feature.apis_used)
        if api_count > 3:
            score += 2
        elif api_count > 0:
            score += 1

        # Dependencies
        if feature.dependencies:
            score += 1

        # User stories (indicates complexity)
        if len(feature.user_stories) > 3:
            score += 1

        # Determine complexity level
        if score <= 2:
            return Complexity.SIMPLE
        elif score <= 5:
            return Complexity.MEDIUM
        elif score <= 8:
            return Complexity.COMPLEX
        else:
            return Complexity.ENTERPRISE

    def _delegate_to_simple(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """Delegate entire generation to simple generator."""
        # Share context
        self.simple_generator._context = self._context
        return self.simple_generator._generate(parsed_prd)

    def _delegate_to_chunked(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """Delegate entire generation to chunked generator."""
        # Share context
        self.chunked_generator._context = self._context
        return self.chunked_generator._generate(parsed_prd)

    def _generate_hybrid(
        self,
        parsed_prd: ParsedPRD,
        simple_features: List[Feature],
        complex_features: List[Feature]
    ) -> Dict[str, Any]:
        """
        Generate using hybrid approach for mixed complexity.

        - Simple features are generated inline
        - Complex features are chunked
        - All composed into unified flow
        """
        logger.info("Starting hybrid generation")

        factory = NodeFactory(self.context)

        # 1. Create shared resources
        self._create_shared_resources(factory, parsed_prd)

        # 2. Create start node
        start_node = self._create_start_node(factory, parsed_prd)

        # 3. Create router for complex features
        if complex_features:
            router_node = self._create_router_node(factory, complex_features)
            self.context.add_exit(start_node["id"], router_node["id"], "To Router")
            router_id = router_node["id"]
        else:
            router_id = start_node["id"]

        # 4. Generate simple features inline (linear chain)
        current_node_id = router_id
        for feature in simple_features:
            exit_node_id = self._generate_simple_feature(factory, feature, current_node_id)
            current_node_id = exit_node_id

        # 5. Generate complex features as chunks
        for feature in complex_features:
            self._generate_complex_feature_chunk(factory, feature)

        # 6. Create end node
        end_node = self._create_end_node(factory)

        # 7. Connect everything
        self._connect_flow(router_id, current_node_id, end_node["id"], complex_features)

        return self._build_agent_json()

    def _create_shared_resources(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> None:
        """Create variables and tools."""
        # Variables
        for var in parsed_prd.variables:
            self.context.add_variable(var.to_insait_dict())

        # Tools
        for api in parsed_prd.apis:
            params = [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in api.parameters
            ]
            factory.create_tool(
                name=api.name,
                function_name=api.function_name,
                description=api.description,
                method=api.method.value,
                endpoint=api.endpoint,
                parameters=params,
            )

    def _create_start_node(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> Dict[str, Any]:
        """Create start node."""
        node = factory.create_start_node(name="Start")
        node["data"]["system_prompt"] = self._build_system_prompt(parsed_prd)
        node["data"]["initial_message"] = f"Welcome to {parsed_prd.metadata.name}."
        return node

    def _create_router_node(
        self,
        factory: NodeFactory,
        complex_features: List[Feature]
    ) -> Dict[str, Any]:
        """Create router for complex features."""
        factory.advance_row()

        conditions = []
        for i, feature in enumerate(complex_features):
            conditions.append({
                "expression": f"{{{{intent}}}} == '{feature.id}'",
                "exit_name": feature.name,
                "priority": i,
            })

        return factory.create_condition_node(
            name="Feature Router",
            conditions=conditions,
        )

    def _create_end_node(self, factory: NodeFactory) -> Dict[str, Any]:
        """Create end node."""
        factory.advance_row()
        return factory.create_end_node(
            name="End",
            message="Thank you. Goodbye!",
        )

    def _generate_simple_feature(
        self,
        factory: NodeFactory,
        feature: Feature,
        entry_node_id: str
    ) -> str:
        """Generate a simple feature inline."""
        self.context.current_feature_id = feature.id
        factory.advance_row()

        # Entry
        entry = factory.create_conversation_node(
            name=f"{feature.id}: {feature.name}",
            message=feature.description or f"Processing {feature.name}",
        )
        self.context.add_exit(entry_node_id, entry["id"], feature.id)
        self.context.set_feature_start_node(feature.id, entry["id"])

        current = entry["id"]

        # Generate basic nodes
        for var in feature.variables_used[:3]:
            collect = factory.create_collect_node(
                name=f"{feature.id}: Get {var}",
                variable_name=var,
                prompt=f"Please provide {var.replace('_', ' ')}",
            )
            self.context.add_exit(current, collect["id"], "Next")
            current = collect["id"]

        for api in feature.apis_used[:2]:
            if self.context.tool_exists(api):
                api_node = factory.create_api_node(
                    name=f"{feature.id}: {api}",
                    tool_id=api,
                )
                self.context.add_exit(current, api_node["id"], "Next")
                current = api_node["id"]

        self.context.add_feature_end_node(feature.id, current)
        return current

    def _generate_complex_feature_chunk(
        self,
        factory: NodeFactory,
        feature: Feature
    ) -> None:
        """Generate a complex feature as a chunk."""
        self.context.current_feature_id = feature.id
        factory.advance_row()

        # Entry
        entry = factory.create_conversation_node(
            name=f"{feature.id}: Start",
            message=f"Starting {feature.name}",
        )
        self.context.set_feature_start_node(feature.id, entry["id"])

        current = entry["id"]

        # Generate all nodes
        for var in feature.variables_used:
            collect = factory.create_collect_node(
                name=f"{feature.id}: Collect {var}",
                variable_name=var,
                prompt=f"Please provide {var.replace('_', ' ')}",
            )
            self.context.add_exit(current, collect["id"], "Next")
            current = collect["id"]

        for api in feature.apis_used:
            if self.context.tool_exists(api):
                api_node = factory.create_api_node(
                    name=f"{feature.id}: Call {api}",
                    tool_id=api,
                )
                self.context.add_exit(current, api_node["id"], "Next")
                current = api_node["id"]

        for step in feature.flow_steps:
            step_node = self._generate_step_node(factory, step, feature)
            if step_node:
                self.context.add_exit(current, step_node["id"], "Next")
                current = step_node["id"]

        # Exit
        exit_node = factory.create_conversation_node(
            name=f"{feature.id}: Done",
            message=f"Completed {feature.name}",
        )
        self.context.add_exit(current, exit_node["id"], "Complete")
        self.context.add_feature_end_node(feature.id, exit_node["id"])

        # Store chunk
        self.context.store_feature_chunk(feature.id, {
            "entry_node_id": entry["id"],
            "exit_node_id": exit_node["id"],
        })

    def _generate_step_node(
        self,
        factory: NodeFactory,
        step,
        feature: Feature
    ) -> Optional[Dict[str, Any]]:
        """Generate node for flow step."""
        from ..parser.models import FlowStepType

        if step.type == FlowStepType.COLLECT:
            return factory.create_collect_node(
                name=f"{feature.id}: Collect",
                variable_name=step.variable_name or "input",
                prompt=step.description,
            )
        elif step.type == FlowStepType.API_CALL:
            return factory.create_api_node(
                name=f"{feature.id}: API",
                tool_id=step.api_name or "api",
            )
        elif step.type == FlowStepType.CONVERSATION:
            return factory.create_conversation_node(
                name=f"{feature.id}: {step.order}",
                message=step.description,
            )
        elif step.type == FlowStepType.TRANSFER:
            return factory.create_end_node(
                name=f"{feature.id}: Transfer",
                end_type="transfer",
            )
        else:
            return factory.create_conversation_node(
                name=f"{feature.id}: Step",
                message=step.description,
            )

    def _connect_flow(
        self,
        router_id: str,
        simple_exit_id: str,
        end_id: str,
        complex_features: List[Feature]
    ) -> None:
        """Connect all parts of the flow."""
        # Simple chain to end
        self.context.add_exit(simple_exit_id, end_id, "Done")

        # Router to complex features
        for feature in complex_features:
            chunk = self.context.feature_chunks.get(feature.id)
            if chunk:
                entry = chunk.get("entry_node_id")
                exit_node = chunk.get("exit_node_id")
                if entry:
                    self.context.add_exit(router_id, entry, feature.id)
                if exit_node:
                    self.context.add_exit(exit_node, router_id, "Back")

        # Router default to end
        self.context.add_exit(router_id, end_id, "Exit")

    def _build_system_prompt(self, parsed_prd: ParsedPRD) -> str:
        """Build system prompt."""
        parts = [
            f"You are {parsed_prd.metadata.name}.",
            parsed_prd.metadata.description or "",
            f"Language: {parsed_prd.metadata.language}",
        ]

        if parsed_prd.features:
            parts.append("\nCapabilities:")
            for f in parsed_prd.features:
                parts.append(f"- {f.name}")

        return "\n".join(filter(None, parts))


def create_generator(
    parsed_prd: ParsedPRD,
    config: Optional[AppConfig] = None,
    llm_client: Optional[BaseLLMClient] = None,
) -> BaseGenerator:
    """
    Factory function to create the appropriate generator.

    Args:
        parsed_prd: Parsed PRD to analyze
        config: Optional configuration
        llm_client: Optional LLM client

    Returns:
        Appropriate generator instance
    """
    from .base_generator import select_strategy, GenerationStrategy

    strategy = select_strategy(parsed_prd, config or AppConfig())

    if strategy == GenerationStrategy.SIMPLE:
        return SimpleGenerator(config, llm_client)
    elif strategy == GenerationStrategy.CHUNKED:
        return ChunkedGenerator(config, llm_client)
    else:
        return HybridGenerator(config, llm_client)
