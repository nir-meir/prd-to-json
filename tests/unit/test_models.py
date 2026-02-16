"""Unit tests for parser models."""

import pytest
from src.parser.models import (
    Channel,
    Complexity,
    VariableType,
    VariableSource,
    FlowStepType,
    HTTPMethod,
    Variable,
    Feature,
    APIEndpoint,
    BusinessRule,
    AgentMetadata,
    ParsedPRD,
    FlowStep,
    UserStory,
)


class TestChannel:
    """Tests for Channel enum."""

    def test_from_string_voice(self):
        assert Channel.from_string("voice") == Channel.VOICE
        assert Channel.from_string("audio") == Channel.VOICE
        assert Channel.from_string("phone") == Channel.VOICE
        assert Channel.from_string("VOICE") == Channel.VOICE

    def test_from_string_text(self):
        assert Channel.from_string("text") == Channel.TEXT
        assert Channel.from_string("chat") == Channel.TEXT
        assert Channel.from_string("whatsapp") == Channel.TEXT
        assert Channel.from_string("sms") == Channel.TEXT

    def test_from_string_both(self):
        assert Channel.from_string("both") == Channel.BOTH
        assert Channel.from_string("all") == Channel.BOTH
        assert Channel.from_string("dual") == Channel.BOTH

    def test_from_string_unknown_defaults_to_both(self):
        assert Channel.from_string("unknown") == Channel.BOTH
        assert Channel.from_string("") == Channel.BOTH


class TestVariableType:
    """Tests for VariableType enum."""

    def test_from_string_string(self):
        assert VariableType.from_string("string") == VariableType.STRING
        assert VariableType.from_string("str") == VariableType.STRING
        assert VariableType.from_string("text") == VariableType.STRING

    def test_from_string_number(self):
        assert VariableType.from_string("number") == VariableType.NUMBER
        assert VariableType.from_string("int") == VariableType.NUMBER
        assert VariableType.from_string("float") == VariableType.NUMBER

    def test_from_string_boolean(self):
        assert VariableType.from_string("boolean") == VariableType.BOOLEAN
        assert VariableType.from_string("bool") == VariableType.BOOLEAN

    def test_from_string_unknown_defaults_to_string(self):
        assert VariableType.from_string("unknown") == VariableType.STRING


class TestVariable:
    """Tests for Variable dataclass."""

    def test_create_variable(self):
        var = Variable(
            name="test_var",
            type=VariableType.STRING,
            description="A test variable",
        )
        assert var.name == "test_var"
        assert var.type == VariableType.STRING
        assert var.source == VariableSource.USER  # default

    def test_variable_type_coercion(self):
        var = Variable(
            name="test",
            type="number",  # string instead of enum
            description="Test",
        )
        assert var.type == VariableType.NUMBER

    def test_to_insait_dict(self):
        var = Variable(
            name="phone",
            type=VariableType.STRING,
            description="Phone number",
            required=True,
        )
        result = var.to_insait_dict()
        assert result["name"] == "phone"
        assert result["type"] == "string"
        assert result["required"] is True


class TestFeature:
    """Tests for Feature dataclass."""

    def test_create_feature(self):
        feature = Feature(
            id="F-01",
            name="Authentication",
            description="User authentication feature",
        )
        assert feature.id == "F-01"
        assert feature.name == "Authentication"
        assert feature.channel == Channel.BOTH  # default

    def test_feature_channel_coercion(self):
        feature = Feature(
            id="F-01",
            name="Test",
            description="Test",
            channel="voice",  # string
        )
        assert feature.channel == Channel.VOICE

    def test_has_text_flow(self):
        text_feature = Feature(id="F-01", name="T", description="D", channel=Channel.TEXT)
        voice_feature = Feature(id="F-02", name="V", description="D", channel=Channel.VOICE)
        both_feature = Feature(id="F-03", name="B", description="D", channel=Channel.BOTH)

        assert text_feature.has_text_flow is True
        assert voice_feature.has_text_flow is False
        assert both_feature.has_text_flow is True

    def test_has_voice_flow(self):
        text_feature = Feature(id="F-01", name="T", description="D", channel=Channel.TEXT)
        voice_feature = Feature(id="F-02", name="V", description="D", channel=Channel.VOICE)
        both_feature = Feature(id="F-03", name="B", description="D", channel=Channel.BOTH)

        assert text_feature.has_voice_flow is False
        assert voice_feature.has_voice_flow is True
        assert both_feature.has_voice_flow is True

    def test_estimated_node_count(self):
        feature = Feature(
            id="F-01",
            name="Test",
            description="Test",
            flow_steps=[
                FlowStep(order=1, type=FlowStepType.COLLECT, description="Step 1"),
                FlowStep(order=2, type=FlowStepType.API_CALL, description="Step 2"),
            ],
        )
        assert feature.estimated_node_count == 4  # 2 steps * 2


class TestAPIEndpoint:
    """Tests for APIEndpoint dataclass."""

    def test_create_api(self):
        api = APIEndpoint(
            name="Get User",
            description="Get user details",
            function_name="get_user",
            method=HTTPMethod.GET,
            endpoint="/api/users/{id}",
        )
        assert api.name == "Get User"
        assert api.method == HTTPMethod.GET

    def test_method_coercion(self):
        api = APIEndpoint(
            name="Create",
            description="Create",
            function_name="create",
            method="post",  # string lowercase
        )
        assert api.method == HTTPMethod.POST


class TestParsedPRD:
    """Tests for ParsedPRD dataclass."""

    def test_create_empty_prd(self):
        prd = ParsedPRD(raw_content="Test content")
        assert prd.raw_content == "Test content"
        assert prd.complexity == Complexity.SIMPLE
        assert len(prd.features) == 0

    def test_complexity_calculation_simple(self):
        prd = ParsedPRD(
            raw_content="Test",
            features=[
                Feature(id="F-01", name="F1", description="D"),
            ],
        )
        assert prd.complexity == Complexity.SIMPLE

    def test_complexity_calculation_medium(self):
        features = [
            Feature(id=f"F-{i:02d}", name=f"Feature {i}", description="D")
            for i in range(5)
        ]
        prd = ParsedPRD(raw_content="Test", features=features)
        assert prd.complexity == Complexity.MEDIUM

    def test_complexity_calculation_complex(self):
        # COMPLEX: feature_count <= 20 AND estimated_nodes <= 100
        # 15 features with 2 flow_steps each = 2 + (15 * 4) = 62 nodes
        features = [
            Feature(
                id=f"F-{i:02d}",
                name=f"Feature {i}",
                description="D",
                flow_steps=[FlowStep(order=j, type=FlowStepType.CONVERSATION, description="S") for j in range(2)],
            )
            for i in range(15)
        ]
        prd = ParsedPRD(raw_content="Test", features=features)
        assert prd.complexity == Complexity.COMPLEX

    def test_get_feature_by_id(self):
        prd = ParsedPRD(
            raw_content="Test",
            features=[
                Feature(id="F-01", name="First", description="D"),
                Feature(id="F-02", name="Second", description="D"),
            ],
        )
        assert prd.get_feature_by_id("F-01").name == "First"
        assert prd.get_feature_by_id("F-02").name == "Second"
        assert prd.get_feature_by_id("F-99") is None

    def test_get_variable_by_name(self):
        prd = ParsedPRD(
            raw_content="Test",
            variables=[
                Variable(name="phone", type=VariableType.STRING, description="Phone"),
                Variable(name="email", type=VariableType.STRING, description="Email"),
            ],
        )
        assert prd.get_variable_by_name("phone").description == "Phone"
        assert prd.get_variable_by_name("unknown") is None

    def test_validate_duplicate_features(self):
        prd = ParsedPRD(
            raw_content="Test",
            features=[
                Feature(id="F-01", name="First", description="D"),
                Feature(id="F-01", name="Duplicate", description="D"),  # Duplicate ID
            ],
        )
        errors = prd.validate()
        assert any("Duplicate feature IDs" in e for e in errors)

    def test_validate_duplicate_variables(self):
        prd = ParsedPRD(
            raw_content="Test",
            variables=[
                Variable(name="test", type=VariableType.STRING, description="D"),
                Variable(name="test", type=VariableType.NUMBER, description="D"),  # Duplicate
            ],
        )
        errors = prd.validate()
        assert any("Duplicate variable names" in e for e in errors)

    def test_summary(self):
        prd = ParsedPRD(
            raw_content="Test",
            metadata=AgentMetadata(name="Test Bot", description="A test bot"),
            features=[Feature(id="F-01", name="F1", description="D")],
            variables=[Variable(name="v1", type=VariableType.STRING, description="D")],
        )
        summary = prd.summary()
        assert "Test Bot" in summary
        assert "Features: 1" in summary
        assert "Variables: 1" in summary
