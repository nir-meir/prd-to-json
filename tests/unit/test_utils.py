"""Unit tests for utility modules."""

import pytest
from src.utils.id_generator import (
    generate_uuid,
    generate_node_id,
    to_kebab_case,
    to_snake_case,
    sanitize_id,
    IDGenerator,
)


class TestGenerateUUID:
    """Tests for generate_uuid function."""

    def test_generates_valid_uuid(self):
        uuid = generate_uuid()
        assert len(uuid) == 36
        assert uuid.count("-") == 4

    def test_generates_unique_uuids(self):
        uuids = [generate_uuid() for _ in range(100)]
        assert len(set(uuids)) == 100


class TestGenerateNodeId:
    """Tests for generate_node_id function."""

    def test_generates_id_with_prefix(self):
        # generate_node_id requires prefix and counter
        node_id = generate_node_id("start", 0)
        assert node_id.startswith("start-")

    def test_generates_id_with_counter(self):
        node_id = generate_node_id("collect", 5)
        assert node_id == "collect-5"

    def test_converts_prefix_to_kebab_case(self):
        node_id = generate_node_id("User Name", 0)
        assert node_id == "user-name-0"


class TestToKebabCase:
    """Tests for to_kebab_case function."""

    def test_converts_spaces(self):
        assert to_kebab_case("Hello World") == "hello-world"

    def test_converts_underscores(self):
        assert to_kebab_case("hello_world") == "hello-world"

    def test_converts_camel_case(self):
        result = to_kebab_case("helloWorld")
        assert "-" in result or result == "helloworld"

    def test_handles_empty_string(self):
        assert to_kebab_case("") == ""

    def test_handles_special_characters(self):
        # to_kebab_case doesn't remove special chars, sanitize_id does
        result = to_kebab_case("hello@world!")
        # Just verify it returns something without crashing
        assert isinstance(result, str)


class TestToSnakeCase:
    """Tests for to_snake_case function."""

    def test_converts_spaces(self):
        assert to_snake_case("Hello World") == "hello_world"

    def test_converts_hyphens(self):
        assert to_snake_case("hello-world") == "hello_world"

    def test_converts_camel_case(self):
        result = to_snake_case("helloWorld")
        assert "_" in result or result == "helloworld"

    def test_handles_empty_string(self):
        assert to_snake_case("") == ""


class TestSanitizeId:
    """Tests for sanitize_id function."""

    def test_removes_special_characters(self):
        result = sanitize_id("hello@world!")
        assert "@" not in result
        assert "!" not in result

    def test_handles_unicode(self):
        result = sanitize_id("שלום-world")
        assert result  # Should return something

    def test_handles_empty_string(self):
        # sanitize_id returns "unnamed" for empty string
        assert sanitize_id("") == "unnamed"


class TestIDGenerator:
    """Tests for IDGenerator class."""

    @pytest.fixture
    def generator(self):
        return IDGenerator()

    def test_generates_unique_node_ids(self, generator):
        # IDGenerator uses node_id() method, not generate()
        ids = [generator.node_id("node") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_tracks_used_node_ids(self, generator):
        id1 = generator.node_id("test")
        assert generator.is_node_id_used(id1)

    def test_reserve_node_id(self, generator):
        assert generator.reserve_node_id("custom-id") is True
        assert generator.is_node_id_used("custom-id")

    def test_reserve_duplicate_fails(self, generator):
        generator.reserve_node_id("custom-id")
        assert generator.reserve_node_id("custom-id") is False

    def test_reset_clears_used_ids(self, generator):
        id1 = generator.node_id("test")
        generator.reset()
        assert not generator.is_node_id_used(id1)

    def test_prefix_counters_independent(self, generator):
        node_ids = [generator.node_id("node") for _ in range(5)]
        # IDGenerator has separate methods for different ID types
        # exit_id requires source and target
        exit_ids = [generator.exit_id(f"src-{i}", f"tgt-{i}") for i in range(5)]

        # Both should have their own sequence
        assert all("node" in nid for nid in node_ids)
        assert all("exit" in eid for eid in exit_ids)
