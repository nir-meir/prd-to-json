"""Unit tests for validator module."""

import pytest
from src.validator import (
    INSAITValidator,
    AutoFixer,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    FixResult,
)


class TestINSAITValidator:
    """Tests for INSAITValidator."""

    @pytest.fixture
    def validator(self):
        return INSAITValidator()

    @pytest.fixture
    def valid_json(self):
        return {
            "name": "Test Bot",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "end-1": {
                        "id": "end-1",
                        "type": "end",
                        "name": "End",
                        "position": {"x": 100, "y": 0},
                        "data": {},
                    },
                },
                "exits": [
                    {
                        "source_node_id": "start-1",
                        "target_node_id": "end-1",
                        "name": "Next",
                    }
                ],
            },
        }

    def test_valid_json_passes(self, validator, valid_json):
        result = validator.validate(valid_json)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_name_fails(self, validator):
        json_data = {
            "flow": {
                "start_node_id": "start-1",
                "nodes": {},
            }
        }
        result = validator.validate(json_data)
        assert result.valid is False
        assert any(i.code == "MISSING_REQUIRED_FIELD" for i in result.issues)

    def test_missing_flow_fails(self, validator):
        json_data = {"name": "Test"}
        result = validator.validate(json_data)
        assert result.valid is False
        assert any(i.code == "MISSING_REQUIRED_FIELD" for i in result.issues)

    def test_missing_start_node_id_detected(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "nodes": {},
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "MISSING_FLOW_FIELD" for i in result.issues)

    def test_invalid_start_node_reference(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "nonexistent",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    }
                },
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "INVALID_START_NODE" for i in result.issues)

    def test_orphaned_node_detected(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "orphan": {
                        "id": "orphan",
                        "type": "conversation",
                        "name": "Orphan",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "ORPHANED_NODE" for i in result.issues)

    def test_dead_end_node_detected(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "conv-1": {
                        "id": "conv-1",
                        "type": "conversation",
                        "name": "Conv",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [
                    {
                        "source_node_id": "start-1",
                        "target_node_id": "conv-1",
                        "name": "Next",
                    }
                ],
            },
        }
        result = validator.validate(json_data)
        # conv-1 has no outgoing exits and is not an end node
        assert any(i.code == "DEAD_END_NODE" for i in result.issues)

    def test_collect_node_without_variable_name(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "collect-1": {
                        "id": "collect-1",
                        "type": "collect",
                        "name": "Collect",
                        "position": {"x": 0, "y": 0},
                        "data": {"prompt": "Enter value"},  # Missing variable_name
                    },
                },
                "exits": [
                    {"source_node_id": "start-1", "target_node_id": "collect-1"}
                ],
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "COLLECT_NO_VARIABLE" for i in result.issues)

    def test_api_node_without_tool_id(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "api-1": {
                        "id": "api-1",
                        "type": "api",
                        "name": "API",
                        "position": {"x": 0, "y": 0},
                        "data": {},  # Missing tool_id
                    },
                },
                "exits": [],
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "API_NO_TOOL_ID" for i in result.issues)

    def test_no_start_node_semantic_error(self, validator):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "end-1",
                "nodes": {
                    "end-1": {
                        "id": "end-1",
                        "type": "end",
                        "name": "End",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }
        result = validator.validate(json_data)
        assert any(i.code == "NO_START_NODE" for i in result.issues)

    def test_strict_mode_treats_warnings_as_errors(self):
        validator = INSAITValidator(strict_mode=True)
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }
        result = validator.validate(json_data)
        # Should have warning for no end node, which becomes error in strict mode
        if result.warnings:
            assert result.valid is False


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_errors_property(self):
        result = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(code="E1", message="Error 1", severity=ValidationSeverity.ERROR),
                ValidationIssue(code="W1", message="Warning 1", severity=ValidationSeverity.WARNING),
                ValidationIssue(code="E2", message="Error 2", severity=ValidationSeverity.ERROR),
            ],
        )
        assert len(result.errors) == 2

    def test_warnings_property(self):
        result = ValidationResult(
            valid=True,
            issues=[
                ValidationIssue(code="W1", message="Warning 1", severity=ValidationSeverity.WARNING),
                ValidationIssue(code="W2", message="Warning 2", severity=ValidationSeverity.WARNING),
            ],
        )
        assert len(result.warnings) == 2

    def test_auto_fixable_count(self):
        result = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(code="E1", message="M1", severity=ValidationSeverity.ERROR, auto_fixable=True),
                ValidationIssue(code="E2", message="M2", severity=ValidationSeverity.ERROR, auto_fixable=False),
                ValidationIssue(code="W1", message="M3", severity=ValidationSeverity.WARNING, auto_fixable=True),
            ],
        )
        assert result.auto_fixable_count == 2

    def test_to_dict(self):
        result = ValidationResult(
            valid=True,
            issues=[
                ValidationIssue(code="W1", message="Warning", severity=ValidationSeverity.WARNING),
            ],
        )
        data = result.to_dict()
        assert data["valid"] is True
        assert data["warning_count"] == 1


class TestAutoFixer:
    """Tests for AutoFixer."""

    @pytest.fixture
    def fixer(self):
        return AutoFixer()

    def test_fix_missing_position(self, fixer):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        # Missing position
                        "data": {},
                    },
                },
                "exits": [],
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        assert "position" in result.fixed_data["flow"]["nodes"]["start-1"]

    def test_fix_invalid_start_node_id(self, fixer):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "nonexistent",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        # Should fix start_node_id to point to actual start node
        assert result.fixed_data["flow"]["start_node_id"] == "start-1"

    def test_fix_adds_end_node_when_missing(self, fixer):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        nodes = result.fixed_data["flow"]["nodes"]
        has_end = any(n.get("type") == "end" for n in nodes.values())
        assert has_end

    def test_fix_connects_dead_end_to_end_node(self, fixer):
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "conv-1": {
                        "id": "conv-1",
                        "type": "conversation",
                        "name": "Conv",
                        "position": {"x": 100, "y": 0},
                        "data": {},
                    },
                },
                "exits": [
                    {"source_node_id": "start-1", "target_node_id": "conv-1", "name": "Next"}
                ],
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        # Should have connected conv-1 to an end node
        exits = result.fixed_data["flow"]["exits"]
        conv_exits = [e for e in exits if e.get("source_node_id") == "conv-1"]
        assert len(conv_exits) > 0

    def test_remove_orphans_option(self):
        fixer = AutoFixer(remove_orphans=True)
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "start-1",
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                    "orphan": {
                        "id": "orphan",
                        "type": "conversation",
                        "name": "Orphan",
                        "position": {"x": 0, "y": 0},
                        "data": {},
                    },
                },
                "exits": [],
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        # Orphan should be removed
        assert "orphan" not in result.fixed_data["flow"]["nodes"]

    def test_fix_result_tracks_applied_fixes(self, fixer):
        json_data = {
            "name": "Test",
            "flow": {
                "nodes": {},
            },
        }

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        assert len(result.fixes_applied) > 0

    def test_fix_result_to_dict(self, fixer):
        json_data = {"name": "Test", "flow": {"nodes": {}}}

        validator = INSAITValidator()
        validation = validator.validate(json_data)

        result = fixer.fix(json_data, validation)
        data = result.to_dict()

        assert "fixes_applied_count" in data
        assert "remaining_issues_count" in data
