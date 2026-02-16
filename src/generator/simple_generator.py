"""
Simple Generator - Single-pass generation for simple PRDs.

Best for PRDs with:
- 1-3 features
- < 20 estimated nodes
- Linear or simple branching flows
"""

from typing import Dict, Any, List, Optional

from .base_generator import BaseGenerator, GenerationResult
from .node_factory import NodeFactory
from .nodes.builders import NodeConfig, build_node
from ..parser.models import ParsedPRD, Feature, Variable, APIEndpoint
from ..core.context import GenerationContext
from ..llm.base import BaseLLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SimpleGenerator(BaseGenerator):
    """
    Simple single-pass generator.

    Generates the entire flow in one pass without chunking.
    Best for simple to medium complexity PRDs.
    """

    @property
    def strategy_name(self) -> str:
        return "simple"

    def _generate(self, parsed_prd: ParsedPRD) -> Dict[str, Any]:
        """
        Generate INSAIT JSON in a single pass.

        Args:
            parsed_prd: Parsed PRD object

        Returns:
            INSAIT JSON structure
        """
        logger.info(f"Generating with simple strategy for: {parsed_prd.metadata.name}")

        # Create node factory
        factory = NodeFactory(self.context)

        # 1. Create start node
        start_node = self._create_start_node(factory, parsed_prd)
        start_node_id = start_node["id"]

        # 2. Create variables
        self._create_variables(parsed_prd.variables)

        # 3. Create tools from APIs
        self._create_tools(factory, parsed_prd.apis)

        # 4. Generate feature nodes
        prev_node_id = start_node_id
        for feature in parsed_prd.features:
            feature_exit_node_id = self._generate_feature(factory, feature, prev_node_id)
            prev_node_id = feature_exit_node_id

        # 5. Create end node
        end_node = self._create_end_node(factory, parsed_prd)

        # Connect last feature to end
        self.context.add_exit(prev_node_id, end_node["id"], "Complete")

        # Build final JSON
        return self._build_agent_json()

    def _create_start_node(
        self,
        factory: NodeFactory,
        parsed_prd: ParsedPRD
    ) -> Dict[str, Any]:
        """Create the start node."""
        metadata = parsed_prd.metadata

        # Build system prompt from PRD context
        system_prompt = self._build_system_prompt(parsed_prd)

        node = factory.create_start_node(
            name="Start",
        )
        node["data"]["system_prompt"] = system_prompt
        node["data"]["initial_message"] = f"Welcome to {metadata.name}."

        return node

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
            logger.debug(f"Created variable: {var.name}")

    def _create_tools(
        self,
        factory: NodeFactory,
        apis: List[APIEndpoint]
    ) -> None:
        """Create tools from API definitions."""
        for api in apis:
            # Build parameters list
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

    def _generate_feature(
        self,
        factory: NodeFactory,
        feature: Feature,
        entry_node_id: str
    ) -> str:
        """
        Generate nodes for a single feature.

        Args:
            factory: Node factory
            feature: Feature to generate
            entry_node_id: ID of node to connect from

        Returns:
            ID of the last node in the feature (for chaining)
        """
        logger.debug(f"Generating feature: {feature.id} - {feature.name}")

        self.context.current_feature_id = feature.id
        factory.advance_row()

        # Track the current node for chaining
        current_node_id = entry_node_id

        # Feature entry conversation (announce feature)
        entry_node = factory.create_conversation_node(
            name=f"{feature.id}: {feature.name}",
            message=feature.description or f"Now handling: {feature.name}",
        )
        self.context.add_exit(current_node_id, entry_node["id"], f"To {feature.id}")
        self.context.set_feature_start_node(feature.id, entry_node["id"])
        current_node_id = entry_node["id"]

        # Generate nodes from flow steps
        if feature.flow_steps:
            for step in feature.flow_steps:
                step_node = self._generate_step_node(factory, step, feature)
                if step_node:
                    self.context.add_exit(current_node_id, step_node["id"], "Next")
                    current_node_id = step_node["id"]
        else:
            # No flow steps - generate basic collect/respond pattern
            if feature.variables_used:
                for var_name in feature.variables_used[:3]:  # Limit to avoid too many nodes
                    collect_node = factory.create_collect_node(
                        name=f"Collect {var_name}",
                        variable_name=var_name,
                        prompt=f"Please provide your {var_name.replace('_', ' ')}",
                    )
                    self.context.add_exit(current_node_id, collect_node["id"], "Next")
                    current_node_id = collect_node["id"]

            # Add API calls if any
            for api_name in feature.apis_used[:2]:  # Limit
                if self.context.tool_exists(api_name):
                    api_node = factory.create_api_node(
                        name=f"Call {api_name}",
                        tool_id=api_name,
                    )
                    self.context.add_exit(current_node_id, api_node["id"], "Next")
                    current_node_id = api_node["id"]

        self.context.add_feature_end_node(feature.id, current_node_id)
        return current_node_id

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
                name=f"Collect {step.variable_name or 'input'}",
                variable_name=step.variable_name or "user_input",
                prompt=step.description,
            )

        elif step.type == FlowStepType.API_CALL:
            tool_id = step.api_name or "unknown_api"
            return factory.create_api_node(
                name=f"Call {tool_id}",
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
                name=f"Check condition",
                conditions=conditions,
            )

        elif step.type == FlowStepType.CONVERSATION:
            return factory.create_conversation_node(
                name=f"Step {step.order}",
                message=step.description,
            )

        elif step.type == FlowStepType.TRANSFER:
            return factory.create_end_node(
                name="Transfer to Agent",
                end_type="transfer",
                message="Transferring you to a human agent.",
            )

        elif step.type == FlowStepType.SET_VARIABLE:
            assignments = {}
            if step.variable_name:
                assignments[step.variable_name] = step.details.get("value", "")
            return factory.create_set_variables_node(
                name=f"Set {step.variable_name or 'variable'}",
                assignments=assignments,
            )

        elif step.type == FlowStepType.END:
            return factory.create_end_node(
                name="End",
                message=step.description,
            )

        else:
            # Default to conversation node
            return factory.create_conversation_node(
                name=f"Step {step.order}",
                message=step.description,
            )

    def _build_system_prompt(self, parsed_prd: ParsedPRD) -> str:
        """Build system prompt from PRD context."""
        metadata = parsed_prd.metadata

        prompt_parts = [
            f"You are {metadata.name}.",
            f"{metadata.description}" if metadata.description else "",
            f"Language: {metadata.language}",
        ]

        # Add feature descriptions
        if parsed_prd.features:
            prompt_parts.append("\nYou can help with:")
            for feature in parsed_prd.features:
                prompt_parts.append(f"- {feature.name}: {feature.description}")

        # Add business rules
        if parsed_prd.business_rules:
            prompt_parts.append("\nImportant rules:")
            for rule in parsed_prd.business_rules[:5]:  # Limit
                prompt_parts.append(f"- {rule.name}: {rule.description}")

        return "\n".join(filter(None, prompt_parts))
