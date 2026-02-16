"""
Chunked Generator - Per-feature generation for complex PRDs.

Best for PRDs with:
- 10+ features
- 50+ estimated nodes
- Complex branching and dependencies

Generates each feature independently, then composes them into a unified flow.
"""

from typing import Dict, Any, List, Optional, Set
import json
import re

from .base_generator import BaseGenerator, GenerationResult
from .node_factory import NodeFactory
from .nodes.builders import NodeConfig, build_node
from ..parser.models import ParsedPRD, Feature, Variable, APIEndpoint
from ..core.context import GenerationContext
from ..llm.base import BaseLLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ChunkedGenerator(BaseGenerator):
    """
    Chunked generator for complex PRDs.

    Generates features in independent chunks, then composes them.
    Uses LLM for intelligent flow composition.
    """

    @property
    def strategy_name(self) -> str:
        return "chunked"

    def _generate(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """
        Generate INSAIT JSON using chunked approach.

        Args:
            parsed_prd: Parsed PRD object

        Returns:
            INSAIT JSON structure
        """
        logger.info(f"Generating with chunked strategy for: {parsed_prd.metadata.name}")
        logger.info(f"Processing {len(parsed_prd.features)} features")

        # Create node factory
        factory = NodeFactory(self.context)

        # 1. Create shared resources (variables, tools)
        self._create_variables(parsed_prd.variables)
        self._create_tools(factory, parsed_prd.apis)

        # 2. Create start node
        start_node = self._create_start_node(factory, parsed_prd)

        # 3. Create main menu/router node
        router_node = self._create_router_node(factory, parsed_prd)
        self.context.add_exit(start_node["id"], router_node["id"], "To Menu")

        # 4. Generate each feature as a chunk
        feature_order = self._determine_feature_order(parsed_prd)

        for feature_id in feature_order:
            feature = parsed_prd.get_feature_by_id(feature_id)
            if feature:
                self._generate_feature_chunk(factory, feature, router_node["id"])

        # 5. Create default end node
        end_node = self._create_end_node(factory, parsed_prd)

        # 6. Connect router to features and end
        self._connect_router_to_features(router_node["id"], end_node["id"])

        # Build final JSON
        return self._build_agent_json()

    def _create_start_node(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> Dict[str, Any]:
        """Create the start node with system prompt."""
        system_prompt = self._build_system_prompt(parsed_prd)

        node = factory.create_start_node(name="Start")
        node["data"]["system_prompt"] = system_prompt
        node["data"]["initial_message"] = self._build_initial_message(parsed_prd)

        return node

    def _create_router_node(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> Dict[str, Any]:
        """Create the main router/menu node."""
        factory.advance_row()

        # Build conditions for each feature
        conditions = []
        for i, feature in enumerate(parsed_prd.features):
            conditions.append({
                "expression": f"{{{{intent}}}} == '{feature.id}'",
                "exit_name": feature.name,
                "priority": i,
            })

        return factory.create_condition_node(
            name="Main Menu Router",
            conditions=conditions,
        )

    def _create_end_node(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> Dict[str, Any]:
        """Create the default end node."""
        factory.advance_row()
        return factory.create_end_node(
            name="End Conversation",
            end_type="end_call",
            message="Thank you for using our service. Goodbye!",
        )

    def _create_variables(self, variables: List[Variable]) -> None:
        """Create variables from PRD definitions."""
        for var in variables:
            var_json = var.to_insait_dict()
            self.context.add_variable(var_json)

    def _create_tools(
        self,
        factory: NodeFactory,
        apis: List[APIEndpoint]
    ) -> None:
        """Create tools from API definitions."""
        for api in apis:
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

    def _determine_feature_order(self, parsed_prd: ParsedPRD) -> List[str]:
        """
        Determine optimal feature generation order based on dependencies.

        Returns features in order such that dependencies come first.
        """
        features = {f.id: f for f in parsed_prd.features}
        visited: Set[str] = set()
        order: List[str] = []

        def visit(feature_id: str) -> None:
            if feature_id in visited:
                return
            visited.add(feature_id)

            feature = features.get(feature_id)
            if feature:
                # Visit dependencies first
                for dep_id in feature.dependencies:
                    if dep_id in features:
                        visit(dep_id)
                order.append(feature_id)

        for feature_id in features:
            visit(feature_id)

        return order

    def _generate_feature_chunk(
        self,
        factory: NodeFactory,
        feature: Feature,
        router_node_id: str
    ) -> None:
        """
        Generate a feature as an independent chunk.

        Args:
            factory: Node factory
            feature: Feature to generate
            router_node_id: ID of router node for return connection
        """
        logger.info(f"Generating chunk for feature: {feature.id} - {feature.name}")

        self.context.current_feature_id = feature.id
        factory.advance_row()

        # Feature entry node
        entry_node = factory.create_conversation_node(
            name=f"{feature.id}: Start",
            message=f"Starting {feature.name}. {feature.description or ''}",
        )
        self.context.set_feature_start_node(feature.id, entry_node["id"])

        current_node_id = entry_node["id"]

        # Generate collect nodes for variables
        collect_node_ids = []
        for var_name in feature.variables_used[:5]:  # Limit to avoid explosion
            collect_node = factory.create_collect_node(
                name=f"{feature.id}: Collect {var_name}",
                variable_name=var_name,
                prompt=f"Please provide your {var_name.replace('_', ' ')}",
            )
            self.context.add_exit(current_node_id, collect_node["id"], "Next")
            current_node_id = collect_node["id"]
            collect_node_ids.append(collect_node["id"])

        # Generate API call nodes
        for api_name in feature.apis_used[:3]:  # Limit
            if self.context.tool_exists(api_name):
                api_node = factory.create_api_node(
                    name=f"{feature.id}: Call {api_name}",
                    tool_id=api_name,
                )
                self.context.add_exit(current_node_id, api_node["id"], "Next")
                current_node_id = api_node["id"]

        # Generate flow step nodes
        for step in feature.flow_steps[:10]:  # Limit
            step_node = self._generate_step_node(factory, step, feature)
            if step_node:
                self.context.add_exit(current_node_id, step_node["id"], "Next")
                current_node_id = step_node["id"]

        # Feature completion node
        complete_node = factory.create_conversation_node(
            name=f"{feature.id}: Complete",
            message=f"{feature.name} completed. Returning to main menu.",
        )
        self.context.add_exit(current_node_id, complete_node["id"], "Complete")
        self.context.add_feature_end_node(feature.id, complete_node["id"])

        # Store chunk reference
        self.context.store_feature_chunk(feature.id, {
            "entry_node_id": entry_node["id"],
            "exit_node_id": complete_node["id"],
            "node_count": len(collect_node_ids) + len(feature.apis_used) + len(feature.flow_steps) + 2,
        })

    def _generate_step_node(
        self,
        factory: NodeFactory,
        step,
        feature: Feature
    ) -> Optional[Dict[str, Any]]:
        """Generate a node for a flow step."""
        from ..parser.models import FlowStepType

        if step.type == FlowStepType.COLLECT:
            return factory.create_collect_node(
                name=f"{feature.id}: Collect {step.variable_name or 'input'}",
                variable_name=step.variable_name or "user_input",
                prompt=step.description,
            )

        elif step.type == FlowStepType.API_CALL:
            tool_id = step.api_name or "unknown_api"
            return factory.create_api_node(
                name=f"{feature.id}: Call {tool_id}",
                tool_id=tool_id,
            )

        elif step.type == FlowStepType.CONDITION:
            conditions = []
            if step.condition:
                conditions.append({
                    "expression": step.condition,
                    "exit_name": "True",
                })
            return factory.create_condition_node(
                name=f"{feature.id}: Check",
                conditions=conditions,
            )

        elif step.type == FlowStepType.CONVERSATION:
            return factory.create_conversation_node(
                name=f"{feature.id}: Step {step.order}",
                message=step.description,
            )

        elif step.type == FlowStepType.TRANSFER:
            return factory.create_end_node(
                name=f"{feature.id}: Transfer",
                end_type="transfer",
                message="Transferring to agent.",
            )

        elif step.type == FlowStepType.SET_VARIABLE:
            assignments = {}
            if step.variable_name:
                assignments[step.variable_name] = step.details.get("value", "")
            return factory.create_set_variables_node(
                name=f"{feature.id}: Set {step.variable_name or 'var'}",
                assignments=assignments,
            )

        elif step.type == FlowStepType.END:
            return factory.create_end_node(
                name=f"{feature.id}: End",
                message=step.description,
            )

        else:
            return factory.create_conversation_node(
                name=f"{feature.id}: Step {step.order}",
                message=step.description,
            )

    def _connect_router_to_features(
        self,
        router_node_id: str,
        end_node_id: str
    ) -> None:
        """Connect router node to feature entry points."""
        for feature_id, chunk in self.context.feature_chunks.items():
            entry_node_id = chunk.get("entry_node_id")
            exit_node_id = chunk.get("exit_node_id")

            if entry_node_id:
                # Router -> Feature entry
                self.context.add_exit(router_node_id, entry_node_id, feature_id)

            if exit_node_id:
                # Feature exit -> Router (loop back)
                self.context.add_exit(exit_node_id, router_node_id, "Back to Menu")

        # Default exit to end
        self.context.add_exit(router_node_id, end_node_id, "Exit")

    def _build_system_prompt(self, parsed_prd: ParsedPRD) -> str:
        """Build comprehensive system prompt."""
        metadata = parsed_prd.metadata

        prompt_parts = [
            f"You are {metadata.name}.",
            metadata.description or "",
            f"Language: {metadata.language}",
            "",
            "Available features:",
        ]

        for feature in parsed_prd.features:
            prompt_parts.append(f"- {feature.id}: {feature.name}")

        if parsed_prd.business_rules:
            prompt_parts.append("")
            prompt_parts.append("Business rules:")
            for rule in parsed_prd.business_rules[:10]:
                prompt_parts.append(f"- {rule.name}: {rule.description}")

        return "\n".join(filter(None, prompt_parts))

    def _build_initial_message(self, parsed_prd: ParsedPRD) -> str:
        """Build initial greeting message."""
        metadata = parsed_prd.metadata
        return f"Welcome to {metadata.name}. How can I assist you today?"
