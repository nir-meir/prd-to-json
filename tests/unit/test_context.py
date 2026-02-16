"""Unit tests for GenerationContext."""

import pytest
from src.core.context import (
    GenerationContext,
    GenerationPhase,
    NodeReference,
    ExitReference,
    ToolReference,
    GenerationStats,
)
from src.parser.models import ParsedPRD, AgentMetadata
from src.core.config import AppConfig


class TestGenerationContext:
    """Tests for GenerationContext."""

    @pytest.fixture
    def context(self):
        return GenerationContext()

    @pytest.fixture
    def context_with_prd(self):
        prd = ParsedPRD(
            raw_content="Test",
            metadata=AgentMetadata(name="Test Bot", description="Test"),
        )
        return GenerationContext(parsed_prd=prd)

    def test_initial_phase(self, context):
        assert context.phase == GenerationPhase.INITIALIZED

    def test_generate_node_id_unique(self, context):
        ids = [context.generate_node_id("test") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_node_id_with_prefix(self, context):
        node_id = context.generate_node_id("start")
        assert node_id.startswith("start-")

    def test_generate_node_id_increments(self, context):
        id1 = context.generate_node_id("node")
        id2 = context.generate_node_id("node")
        # IDs should be different
        assert id1 != id2
        # IDs should have sequential numbers
        assert "node-0" == id1
        assert "node-1" == id2

    def test_generate_exit_id(self, context):
        exit_id = context.generate_exit_id("source-1", "target-1")
        assert "source-1" in exit_id
        assert "target-1" in exit_id

    def test_generate_exit_id_handles_collision(self, context):
        id1 = context.generate_exit_id("s1", "t1")
        id2 = context.generate_exit_id("s1", "t1")
        # Same source/target should get different IDs
        assert id1 != id2

    def test_reserve_node_id(self, context):
        assert context.reserve_node_id("custom-id") is True
        # Second attempt should fail
        assert context.reserve_node_id("custom-id") is False

    def test_register_node(self, context):
        node_json = {
            "id": "test-node-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        }
        ref = context.register_node(node_json)

        assert isinstance(ref, NodeReference)
        assert ref.node_id == "test-node-1"
        assert ref.node_type == "start"
        assert context.node_exists("test-node-1")
        assert context.stats.total_nodes == 1

    def test_register_start_node_sets_start_node_id(self, context):
        node_json = {
            "id": "start-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        }
        context.register_node(node_json)

        assert context.start_node_id == "start-1"

    def test_add_exit(self, context):
        # First register nodes
        context.register_node({
            "id": "node-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "node-2",
            "type": "end",
            "name": "End",
            "position": {"x": 100, "y": 0},
            "data": {},
        })

        ref = context.add_exit("node-1", "node-2", "Next")

        assert isinstance(ref, ExitReference)
        assert ref.source_node_id == "node-1"
        assert ref.target_node_id == "node-2"
        assert context.stats.total_exits == 1

    def test_add_exit_updates_node_references(self, context):
        context.register_node({
            "id": "node-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "node-2",
            "type": "end",
            "name": "End",
            "position": {"x": 100, "y": 0},
            "data": {},
        })

        context.add_exit("node-1", "node-2", "Next")

        # Check node references updated
        node1 = context.get_node("node-1")
        node2 = context.get_node("node-2")
        assert len(node1.outgoing_exits) == 1
        assert len(node2.incoming_exits) == 1

    def test_register_tool(self, context):
        tool_json = {
            "id": "get_user",
            "original_id": "get_user",
            "name": "Get User",
            "function_definition": {
                "name": "get_user",
                "description": "Gets user info",
                "parameters": [],
            },
        }
        ref = context.register_tool(tool_json)

        assert isinstance(ref, ToolReference)
        assert ref.tool_id == "get_user"
        assert context.tool_exists("get_user")
        assert context.stats.total_tools == 1

    def test_add_variable(self, context):
        var_json = {
            "name": "user_name",
            "type": "string",
            "description": "User name",
        }
        context.add_variable(var_json)

        assert len(context.variables_json) == 1
        assert context.stats.total_variables == 1

    def test_get_flow_json(self, context):
        # Register a start node
        context.register_node({
            "id": "start-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        })

        flow = context.get_flow_json()

        assert "start_node_id" in flow
        assert "nodes" in flow
        assert "exits" in flow
        assert flow["start_node_id"] == "start-1"

    def test_feature_tracking(self, context):
        context.set_feature_start_node("F-01", "node-1")
        context.add_feature_end_node("F-01", "node-2")
        context.add_feature_end_node("F-01", "node-3")

        assert context.feature_start_nodes["F-01"] == "node-1"
        assert len(context.feature_end_nodes["F-01"]) == 2

    def test_error_management(self, context):
        context.add_error("Error 1")
        context.add_warning("Warning 1")

        assert context.has_errors()
        assert len(context.errors) == 1
        assert len(context.warnings) == 1

    def test_reset(self, context):
        # Add some data
        context.register_node({
            "id": "test",
            "type": "start",
            "name": "Test",
            "position": {"x": 0, "y": 0},
            "data": {},
        })
        context.add_error("Error")

        # Reset
        context.reset()

        assert len(context.nodes) == 0
        assert len(context.errors) == 0
        assert context.start_node_id is None
        assert context.stats.total_nodes == 0

    def test_get_nodes_by_type(self, context):
        context.register_node({
            "id": "start-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "end-1",
            "type": "end",
            "name": "End",
            "position": {"x": 100, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "end-2",
            "type": "end",
            "name": "End 2",
            "position": {"x": 200, "y": 0},
            "data": {},
        })

        end_nodes = context.get_nodes_by_type("end")
        start_nodes = context.get_nodes_by_type("start")

        assert len(end_nodes) == 2
        assert len(start_nodes) == 1

    def test_get_exits_from_node(self, context):
        # Setup nodes
        context.register_node({
            "id": "node-1",
            "type": "start",
            "name": "Start",
            "position": {"x": 0, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "node-2",
            "type": "end",
            "name": "End",
            "position": {"x": 100, "y": 0},
            "data": {},
        })
        context.register_node({
            "id": "node-3",
            "type": "end",
            "name": "End 2",
            "position": {"x": 200, "y": 0},
            "data": {},
        })

        # Add exits
        context.add_exit("node-1", "node-2", "Path 1")
        context.add_exit("node-1", "node-3", "Path 2")

        exits = context.get_exits_from_node("node-1")
        assert len(exits) == 2

    def test_position_management(self, context):
        pos1 = context.get_next_position()
        pos2 = context.get_next_position()

        # Positions should advance
        assert pos1 != pos2

    def test_start_new_feature_row(self, context):
        pos1 = context.get_next_position()
        pos2 = context.start_new_feature_row()

        # Y should increase significantly for feature row gap
        assert pos2["y"] > pos1["y"]


class TestNodeReference:
    """Tests for NodeReference dataclass."""

    def test_create_node_reference(self):
        ref = NodeReference(
            node_id="test-1",
            node_type="start",
            name="Test Node",
        )
        assert ref.node_id == "test-1"
        assert ref.node_type == "start"
        assert ref.incoming_exits == []
        assert ref.outgoing_exits == []


class TestGenerationStats:
    """Tests for GenerationStats dataclass."""

    def test_default_stats(self):
        stats = GenerationStats()
        assert stats.total_nodes == 0
        assert stats.total_exits == 0
        assert stats.total_tools == 0
        assert stats.llm_calls == 0

    def test_stats_tracking(self):
        stats = GenerationStats()
        stats.total_nodes = 5
        stats.nodes_by_type["start"] = 1
        stats.nodes_by_type["end"] = 1
        stats.nodes_by_type["conversation"] = 3

        assert stats.total_nodes == 5
        assert sum(stats.nodes_by_type.values()) == 5
