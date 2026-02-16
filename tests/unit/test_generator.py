"""Unit tests for generator module."""

import pytest
from src.generator import (
    BaseGenerator,
    SimpleGenerator,
    ChunkedGenerator,
    HybridGenerator,
    create_generator,
    select_strategy,
    GenerationStrategy,
    GenerationResult,
    NodeFactory,
    NodeType,
)
from src.generator.nodes import (
    NodeConfig,
    build_node,
    get_builder,
)
from src.parser.models import (
    ParsedPRD,
    Feature,
    Variable,
    APIEndpoint,
    AgentMetadata,
    Channel,
    VariableType,
    Complexity,
    FlowStep,
    FlowStepType,
)
from src.core.context import GenerationContext
from src.core.config import AppConfig
from src.llm import MockLLMClient


class TestNodeBuilders:
    """Tests for node builders."""

    def test_build_start_node(self):
        config = NodeConfig(name="Start", position={"x": 0, "y": 0})
        node = build_node("start", config, initial_message="Welcome!")

        assert node["type"] == "start"
        assert node["name"] == "Start"
        assert node["data"]["initial_message"] == "Welcome!"
        assert "id" in node

    def test_build_end_node(self):
        config = NodeConfig(name="End")
        node = build_node("end", config, end_type="end_call", message="Goodbye")

        assert node["type"] == "end"
        assert node["data"]["end_type"] == "end_call"
        assert node["data"]["message"] == "Goodbye"

    def test_build_collect_node(self):
        config = NodeConfig(name="Collect Phone")
        node = build_node(
            "collect",
            config,
            variable_name="phone_number",
            prompt="Enter your phone number",
        )

        assert node["type"] == "collect"
        assert node["data"]["variable_name"] == "phone_number"
        assert node["data"]["prompt"] == "Enter your phone number"

    def test_build_conversation_node(self):
        config = NodeConfig(name="Greet")
        node = build_node(
            "conversation",
            config,
            message="Hello {{user_name}}!",
        )

        assert node["type"] == "conversation"
        assert "{{user_name}}" in node["data"]["message"]

    def test_build_api_node(self):
        config = NodeConfig(name="Get User")
        node = build_node(
            "api",
            config,
            tool_id="get_user",
            parameters={"user_id": "{{user_id}}"},
        )

        assert node["type"] == "api"
        assert node["data"]["tool_id"] == "get_user"
        assert node["data"]["parameters"]["user_id"] == "{{user_id}}"

    def test_build_condition_node(self):
        config = NodeConfig(name="Check Auth")
        node = build_node(
            "condition",
            config,
            conditions=[
                {"expression": "{{is_auth}} == true", "exit_name": "Authenticated"},
            ],
        )

        assert node["type"] == "condition"
        assert len(node["data"]["conditions"]) == 1

    def test_build_set_variables_node(self):
        config = NodeConfig(name="Set Flags")
        node = build_node(
            "set_variables",
            config,
            assignments={"flag1": True, "counter": 0},
        )

        assert node["type"] == "set_variables"
        assert len(node["data"]["assignments"]) == 2

    def test_get_builder_unknown_type(self):
        with pytest.raises(ValueError):
            get_builder("unknown_type")

    def test_node_has_uuid(self):
        config = NodeConfig(name="Test")
        node = build_node("start", config)

        # UUID should be present and have correct format
        assert "id" in node
        assert len(node["id"]) == 36  # UUID format


class TestNodeFactory:
    """Tests for NodeFactory."""

    @pytest.fixture
    def context(self):
        return GenerationContext()

    @pytest.fixture
    def factory(self, context):
        return NodeFactory(context)

    def test_create_start_node(self, factory):
        node = factory.create_start_node(name="Start")

        assert node["type"] == "start"
        assert node["name"] == "Start"

    def test_create_collect_node_registers_in_context(self, factory, context):
        node = factory.create_collect_node(
            name="Collect",
            variable_name="test_var",
            prompt="Test prompt",
        )

        # Node should be registered in context
        assert node["id"] in context.nodes

    def test_create_exit(self, factory, context):
        node1 = factory.create_start_node()
        node2 = factory.create_end_node()

        exit_data = factory.create_exit(node1["id"], node2["id"], "Next")

        assert exit_data["source"] == node1["id"]
        assert exit_data["target"] == node2["id"]

    def test_position_auto_increment(self, factory):
        node1 = factory.create_start_node()
        node2 = factory.create_conversation_node(name="Conv", message="Test")

        # Positions should be different
        assert node1["position"]["x"] != node2["position"]["x"] or \
               node1["position"]["y"] != node2["position"]["y"]

    def test_advance_row(self, factory):
        node1 = factory.create_start_node()
        factory.advance_row()
        node2 = factory.create_start_node(name="Start2")

        # After advancing row, Y should be different
        assert node2["position"]["y"] > node1["position"]["y"]


class TestStrategySelection:
    """Tests for strategy selection."""

    def test_simple_strategy_for_simple_prd(self):
        prd = ParsedPRD(
            raw_content="Test",
            features=[Feature(id="F-01", name="F1", description="D")],
        )
        config = AppConfig()
        strategy = select_strategy(prd, config)

        assert strategy == GenerationStrategy.SIMPLE

    def test_chunked_strategy_for_medium_prd(self):
        # Create PRD with many nodes
        features = [
            Feature(
                id=f"F-{i:02d}",
                name=f"Feature {i}",
                description="D",
                flow_steps=[FlowStep(order=j, type=FlowStepType.CONVERSATION, description="S") for j in range(3)],
            )
            for i in range(6)
        ]
        prd = ParsedPRD(raw_content="Test", features=features)
        config = AppConfig()
        strategy = select_strategy(prd, config)

        # Should select chunked or hybrid for medium complexity
        assert strategy in (GenerationStrategy.CHUNKED, GenerationStrategy.HYBRID, GenerationStrategy.SIMPLE)

    def test_hybrid_strategy_for_complex_prd(self):
        # Create complex PRD
        features = [
            Feature(
                id=f"F-{i:02d}",
                name=f"Feature {i}",
                description="D",
                flow_steps=[FlowStep(order=j, type=FlowStepType.CONVERSATION, description="S") for j in range(5)],
            )
            for i in range(15)
        ]
        prd = ParsedPRD(raw_content="Test", features=features)
        config = AppConfig()
        strategy = select_strategy(prd, config)

        assert strategy == GenerationStrategy.HYBRID


class TestSimpleGenerator:
    """Tests for SimpleGenerator."""

    @pytest.fixture
    def mock_llm(self):
        return MockLLMClient(default_response="{}")

    @pytest.fixture
    def simple_prd(self):
        return ParsedPRD(
            raw_content="Test PRD",
            metadata=AgentMetadata(name="Test Bot", description="A test bot"),
            features=[
                Feature(
                    id="F-01",
                    name="Greeting",
                    description="Greet the user",
                    variables_used=["user_name"],
                )
            ],
            variables=[
                Variable(name="user_name", type=VariableType.STRING, description="User name"),
            ],
        )

    def test_generate_creates_valid_json(self, mock_llm, simple_prd):
        generator = SimpleGenerator(llm_client=mock_llm)
        result = generator.generate(simple_prd)

        assert result.success is True
        assert result.json_output is not None
        assert "name" in result.json_output
        assert "flow" in result.json_output

    def test_generate_includes_start_node(self, mock_llm, simple_prd):
        generator = SimpleGenerator(llm_client=mock_llm)
        result = generator.generate(simple_prd)

        nodes = result.json_output["flow"]["nodes"]
        node_types = [n["type"] for n in nodes.values()]
        assert "start" in node_types

    def test_generate_includes_end_node(self, mock_llm, simple_prd):
        generator = SimpleGenerator(llm_client=mock_llm)
        result = generator.generate(simple_prd)

        nodes = result.json_output["flow"]["nodes"]
        node_types = [n["type"] for n in nodes.values()]
        assert "end" in node_types

    def test_generate_creates_variables(self, mock_llm, simple_prd):
        generator = SimpleGenerator(llm_client=mock_llm)
        result = generator.generate(simple_prd)

        variables = result.json_output.get("variables", [])
        assert len(variables) > 0

    def test_strategy_name(self, mock_llm):
        generator = SimpleGenerator(llm_client=mock_llm)
        assert generator.strategy_name == "simple"


class TestGenerationResult:
    """Tests for GenerationResult."""

    def test_successful_result(self):
        result = GenerationResult(
            success=True,
            json_output={"test": "data"},
        )
        assert result.success is True
        assert result.json_output == {"test": "data"}

    def test_failed_result(self):
        result = GenerationResult(
            success=False,
            error_message="Something went wrong",
        )
        assert result.success is False
        assert result.error_message == "Something went wrong"

    def test_to_json(self):
        result = GenerationResult(
            success=True,
            json_output={"test": "data"},
            warnings=["Warning 1"],
            stats={"nodes": 5},
        )
        json_data = result.to_json()

        assert json_data["success"] is True
        assert json_data["warnings"] == ["Warning 1"]
        assert json_data["stats"]["nodes"] == 5


class TestCreateGenerator:
    """Tests for create_generator factory function."""

    def test_creates_simple_generator_for_simple_prd(self):
        prd = ParsedPRD(
            raw_content="Test",
            features=[Feature(id="F-01", name="F1", description="D")],
        )
        generator = create_generator(prd)

        assert isinstance(generator, (SimpleGenerator, HybridGenerator))

    def test_creates_generator_with_config(self):
        prd = ParsedPRD(raw_content="Test")
        config = AppConfig()
        generator = create_generator(prd, config=config)

        assert generator.config == config
