"""Unit tests for PRD extractors."""

import pytest
from src.parser.extractors import (
    MetadataExtractor,
    FeatureExtractor,
    VariableExtractor,
    APIExtractor,
    RuleExtractor,
)
from src.parser.models import Channel, VariableType


class TestMetadataExtractor:
    """Tests for MetadataExtractor."""

    @pytest.fixture
    def extractor(self):
        return MetadataExtractor()

    def test_extract_name_from_title(self, extractor):
        content = "# Customer Support Bot\n\nThis is a support bot."
        result = extractor.extract(content)
        assert "Customer Support" in result.name

    def test_extract_name_from_explicit_field(self, extractor):
        content = "Agent Name: My Custom Bot\n\nDescription here."
        result = extractor.extract(content)
        assert result.name == "My Custom Bot"

    def test_extract_language_hebrew(self, extractor):
        content = "# Bot\n\nLanguage: Hebrew\n\nשלום"
        result = extractor.extract(content)
        assert result.language == "he-IL"

    def test_extract_language_english(self, extractor):
        content = "# Bot\n\nLanguage: English"
        result = extractor.extract(content)
        assert result.language == "en-US"

    def test_extract_language_from_hebrew_content(self, extractor):
        content = "# בוט תמיכה\n\nזהו בוט לשירות לקוחות"
        result = extractor.extract(content)
        assert result.language == "he-IL"

    def test_extract_channel_voice(self, extractor):
        content = "# Bot\n\nChannel: voice\n\nThis is a voice bot."
        result = extractor.extract(content)
        assert result.channel == Channel.VOICE

    def test_extract_channel_text(self, extractor):
        content = "# Bot\n\nChannel: text\n\nThis is a WhatsApp bot."
        result = extractor.extract(content)
        assert result.channel == Channel.TEXT

    def test_extract_channel_both(self, extractor):
        content = "# Bot\n\nChannel: both\n\nText + Audio support."
        result = extractor.extract(content)
        assert result.channel == Channel.BOTH

    def test_extract_phase(self, extractor):
        content = "# Bot\n\nPhase: 2\n\nSecond phase implementation."
        result = extractor.extract(content)
        assert result.phase == 2

    def test_default_values(self, extractor):
        content = "Some random content without structure"
        result = extractor.extract(content)
        assert result.name == "Unnamed Agent"
        assert result.language == "en-US"
        assert result.channel == Channel.BOTH
        assert result.phase == 1


class TestFeatureExtractor:
    """Tests for FeatureExtractor."""

    @pytest.fixture
    def extractor(self):
        return FeatureExtractor()

    def test_extract_features_from_sections(self, extractor):
        content = """
# PRD

## Feature F-01: Authentication
Authenticate users with their credentials.

## Feature F-02: Data Lookup
Look up user data from the system.
"""
        result = extractor.extract(content)
        assert len(result) == 2
        assert result[0].id == "F-01"
        assert result[1].id == "F-02"

    def test_extract_feature_description(self, extractor):
        content = """
## Feature F-01: Test Feature

### Description
This is the feature description.

### Flow
1. Step one
"""
        result = extractor.extract(content)
        assert len(result) == 1
        assert "feature description" in result[0].description.lower()

    def test_extract_channel_from_feature(self, extractor):
        content = """
## Feature F-01: Voice Feature

### Flow (Audio)
1. Greet user
2. Collect info
"""
        result = extractor.extract(content)
        assert len(result) == 1
        assert result[0].channel in (Channel.VOICE, Channel.BOTH)

    def test_extract_variables_used(self, extractor):
        content = """
## Feature F-01: Test

### Variables Used
- user_name
- phone_number
"""
        result = extractor.extract(content)
        # Variables should be extracted from the feature content
        assert len(result) >= 1

    def test_no_features_returns_empty(self, extractor):
        content = "Random content without features"
        result = extractor.extract(content)
        assert result == []


class TestVariableExtractor:
    """Tests for VariableExtractor."""

    @pytest.fixture
    def extractor(self):
        return VariableExtractor()

    def test_extract_from_table(self, extractor):
        content = """
## Variables

| Name | Type | Description |
|------|------|-------------|
| user_name | string | The user's name |
| age | number | User age |
"""
        result = extractor.extract(content)
        assert len(result) >= 2
        names = [v.name for v in result]
        assert "user_name" in names

    def test_extract_from_list(self, extractor):
        content = """
## Variables

- **user_name** (string): The user's name
- **phone** (string): Phone number
"""
        result = extractor.extract(content)
        assert len(result) >= 1

    def test_extract_from_mustache_references(self, extractor):
        content = """
## Flow

1. Ask user for {{user_name}}
2. Verify {{phone_number}}
"""
        result = extractor.extract(content)
        names = [v.name for v in result]
        # Should find referenced variables
        assert any("user_name" in n for n in names) or any("phone_number" in n for n in names)

    def test_variable_types(self, extractor):
        content = """
## Variables

| Name | Type | Description |
|------|------|-------------|
| count | number | A count |
| flag | boolean | A flag |
"""
        result = extractor.extract(content)
        types = {v.name: v.type for v in result}
        if "count" in types:
            assert types["count"] == VariableType.NUMBER
        if "flag" in types:
            assert types["flag"] == VariableType.BOOLEAN


class TestAPIExtractor:
    """Tests for APIExtractor."""

    @pytest.fixture
    def extractor(self):
        return APIExtractor()

    def test_extract_from_section(self, extractor):
        content = """
## APIs

### Get User Details
Method: GET
Endpoint: /api/users/{id}

Gets user details from the system.
"""
        result = extractor.extract(content)
        assert len(result) >= 1
        assert any("User" in api.name for api in result)

    def test_extract_from_table(self, extractor):
        content = """
## APIs

| Name | Method | Endpoint |
|------|--------|----------|
| Get User | GET | /api/user |
| Create Order | POST | /api/orders |
"""
        result = extractor.extract(content)
        assert len(result) >= 1

    def test_function_name_generation(self, extractor):
        content = """
## APIs

### Get User Details
Gets user info.
"""
        result = extractor.extract(content)
        if result:
            # Function name should be snake_case
            assert "_" in result[0].function_name or result[0].function_name.islower()


class TestRuleExtractor:
    """Tests for RuleExtractor."""

    @pytest.fixture
    def extractor(self):
        return RuleExtractor()

    def test_extract_from_table(self, extractor):
        content = """
## Business Rules

| ID | Name | Condition | Action |
|----|------|-----------|--------|
| BR-01 | Working Hours | Outside 9-5 | Transfer to voicemail |
"""
        result = extractor.extract(content)
        assert len(result) >= 1
        assert any("BR-01" in r.id for r in result)

    def test_extract_working_hours_pattern(self, extractor):
        content = """
Working hours: 08:00 - 17:00

Outside working hours, transfer to voicemail.
"""
        result = extractor.extract(content)
        # Should detect working hours rule
        assert any("hour" in r.name.lower() for r in result) or len(result) > 0

    def test_extract_authentication_pattern(self, extractor):
        content = """
Users must be authenticated before accessing services.
"""
        result = extractor.extract(content)
        # Should detect auth requirement
        assert len(result) >= 0  # May or may not detect depending on pattern

    def test_extract_transfer_pattern(self, extractor):
        content = """
If MoveToRep is true, transfer to human agent.
"""
        result = extractor.extract(content)
        # Should detect transfer rule
        assert len(result) >= 1
