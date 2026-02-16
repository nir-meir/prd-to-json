"""Integration tests for the full pipeline."""

import pytest
import tempfile
import json
from pathlib import Path

from src.cli import run_pipeline
from src.parser import PRDParser, ParsedPRD
from src.generator import SimpleGenerator, create_generator
from src.validator import INSAITValidator, AutoFixer
from src.llm import MockLLMClient
from src.core.config import AppConfig


class TestFullPipeline:
    """End-to-end pipeline tests."""

    @pytest.fixture
    def mock_llm(self):
        return MockLLMClient(default_response="{}")

    @pytest.fixture
    def simple_prd_content(self):
        return """
# Simple Test Bot PRD

## Overview
A simple test bot for integration testing.

Language: English
Channel: Text

## Feature F-01: Greeting

### Description
Greet the user and ask for their name.

### Flow (Text)
1. Say hello
2. Ask for user name
3. Respond with personalized greeting

### Variables Used
- user_name

## Variables

| Name | Type | Description |
|------|------|-------------|
| user_name | string | The user's name |

## APIs

| Name | Method | Endpoint |
|------|--------|----------|
| Get User | GET | /api/user |
"""

    @pytest.fixture
    def complex_prd_content(self):
        return """
# Complex Test Bot PRD

## Overview
A complex test bot with multiple features.

Language: Hebrew
Channel: Both

## Feature F-01: Authentication

### Description
Authenticate users with phone and ID.

### Flow (Text)
1. Ask for phone number
2. Ask for ID number
3. Call verify API
4. Check result

### Flow (Audio)
1. Greet user
2. Ask for phone number
3. Ask for ID number
4. Verify user

### Variables Used
- phone_number
- id_number

### APIs Used
- verify_user

## Feature F-02: Policy Lookup

### Description
Look up user policy details.

### Flow (Text)
1. Ask for policy number
2. Call get_policy API
3. Display policy details

### Variables Used
- policy_number
- policy_data

### APIs Used
- get_policy

## Feature F-03: Transfer to Agent

### Description
Transfer user to human agent.

### Flow (Text)
1. Confirm transfer
2. Transfer to queue

## Variables

| Name | Type | Description | Source |
|------|------|-------------|--------|
| phone_number | string | User phone | collect |
| id_number | string | User ID | collect |
| policy_number | string | Policy number | collect |
| policy_data | object | Policy details | tool |

## APIs

### verify_user
Method: POST
Endpoint: /api/verify

### get_policy
Method: GET
Endpoint: /api/policy/{id}

## Business Rules

| ID | Name | Condition | Action |
|----|------|-----------|--------|
| BR-01 | Working Hours | Outside 8-17 | Transfer to voicemail |
| BR-02 | Auth Required | Not authenticated | Go to F-01 |
"""

    def test_simple_prd_pipeline(self, simple_prd_content, mock_llm):
        """Test pipeline with a simple PRD."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(simple_prd_content)
            temp_path = f.name

        try:
            result = run_pipeline(
                input_path=temp_path,
                use_mock_llm=True,
                auto_fix=True,
            )

            # Verify result structure
            assert "name" in result
            assert "flow" in result
            assert "start_node_id" in result["flow"]
            assert "nodes" in result["flow"]

            # Verify has start and end nodes
            nodes = result["flow"]["nodes"]
            node_types = [n["type"] for n in nodes.values()]
            assert "start" in node_types
            assert "end" in node_types

        finally:
            Path(temp_path).unlink()

    def test_complex_prd_pipeline(self, complex_prd_content, mock_llm):
        """Test pipeline with a complex multi-feature PRD."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(complex_prd_content)
            temp_path = f.name

        try:
            result = run_pipeline(
                input_path=temp_path,
                use_mock_llm=True,
                auto_fix=True,
            )

            # Verify result structure
            assert "name" in result
            assert "flow" in result

            # Should have multiple nodes for complex PRD
            nodes = result["flow"]["nodes"]
            assert len(nodes) > 2

        finally:
            Path(temp_path).unlink()

    def test_pipeline_with_validation(self, simple_prd_content, mock_llm):
        """Test that pipeline output passes validation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(simple_prd_content)
            temp_path = f.name

        try:
            result = run_pipeline(
                input_path=temp_path,
                use_mock_llm=True,
                auto_fix=True,
            )

            # Validate the output
            validator = INSAITValidator()
            validation = validator.validate(result)

            # Should be valid or have only warnings
            assert len(validation.errors) == 0, f"Errors: {[e.message for e in validation.errors]}"

        finally:
            Path(temp_path).unlink()

    def test_pipeline_output_to_file(self, simple_prd_content, mock_llm):
        """Test that pipeline can write to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(simple_prd_content)
            input_path = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = f.name

        try:
            run_pipeline(
                input_path=input_path,
                output_path=output_path,
                use_mock_llm=True,
            )

            # Verify file was written
            assert Path(output_path).exists()

            # Verify valid JSON
            with open(output_path) as f:
                data = json.load(f)
            assert "name" in data
            assert "flow" in data

        finally:
            Path(input_path).unlink()
            Path(output_path).unlink()


class TestParserToGenerator:
    """Test parser output works with generator."""

    @pytest.fixture
    def mock_llm(self):
        return MockLLMClient(default_response="{}")

    def test_parser_output_compatible_with_generator(self, mock_llm):
        """Test that parser output can be passed to generator."""
        prd_content = """
# Test Bot

## Overview
A test bot.

## Feature F-01: Test Feature
A test feature.
"""
        parser = PRDParser(llm_client=mock_llm)
        parsed = parser.parse(prd_content)

        # Verify parser output type
        assert isinstance(parsed, ParsedPRD)

        # Pass to generator
        generator = create_generator(parsed, llm_client=mock_llm)
        result = generator.generate(parsed)

        assert result.success is True
        assert result.json_output is not None


class TestGeneratorToValidator:
    """Test generator output works with validator."""

    @pytest.fixture
    def mock_llm(self):
        return MockLLMClient(default_response="{}")

    def test_generator_output_is_validatable(self, mock_llm):
        """Test that generator output can be validated."""
        prd_content = """
# Test Bot

## Overview
A test bot.

## Feature F-01: Test Feature
A test feature.
"""
        parser = PRDParser(llm_client=mock_llm)
        parsed = parser.parse(prd_content)

        generator = SimpleGenerator(llm_client=mock_llm)
        gen_result = generator.generate(parsed)

        # Validate
        validator = INSAITValidator()
        val_result = validator.validate(gen_result.json_output)

        # Should be valid or auto-fixable
        if not val_result.valid:
            assert val_result.auto_fixable_count > 0


class TestValidatorToFixer:
    """Test validator output works with fixer."""

    def test_validation_issues_are_fixable(self):
        """Test that validation issues can be fixed."""
        # Create JSON with known issues
        json_data = {
            "name": "Test",
            "flow": {
                "start_node_id": "nonexistent",  # Invalid reference
                "nodes": {
                    "start-1": {
                        "id": "start-1",
                        "type": "start",
                        "name": "Start",
                        # Missing position - fixable
                        "data": {},
                    },
                },
                "exits": [],
            },
        }

        validator = INSAITValidator()
        val_result = validator.validate(json_data)

        assert not val_result.valid
        assert val_result.auto_fixable_count > 0

        fixer = AutoFixer()
        fix_result = fixer.fix(json_data, val_result)

        assert len(fix_result.fixes_applied) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def mock_llm(self):
        return MockLLMClient(default_response="{}")

    def test_empty_prd(self, mock_llm):
        """Test handling of empty PRD."""
        parser = PRDParser(llm_client=mock_llm)

        with pytest.raises(ValueError):
            parser.parse("")

    def test_prd_with_no_features(self, mock_llm):
        """Test PRD with no extractable features."""
        prd_content = "Just some random text without structure."

        parser = PRDParser(llm_client=mock_llm)
        parsed = parser.parse(prd_content)

        # Should not crash, just have empty features
        assert parsed is not None
        assert parsed.features == []

    def test_generator_handles_empty_features(self, mock_llm):
        """Test generator with PRD that has no features."""
        parsed = ParsedPRD(raw_content="Test")

        generator = SimpleGenerator(llm_client=mock_llm)
        result = generator.generate(parsed)

        # Should still produce valid JSON
        assert result.success is True
        assert "flow" in result.json_output

    def test_nonexistent_input_file(self):
        """Test handling of nonexistent input file."""
        with pytest.raises(FileNotFoundError):
            run_pipeline("/nonexistent/path/to/file.md")

    def test_invalid_json_for_validator(self):
        """Test validator with completely invalid structure."""
        validator = INSAITValidator()
        result = validator.validate({})

        assert not result.valid
        assert len(result.errors) > 0
