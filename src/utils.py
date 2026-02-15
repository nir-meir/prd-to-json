"""
Utility functions for PRD to JSON Generator.
"""

import re
import json
from pathlib import Path
from typing import Optional


def extract_json_from_response(response: str) -> str:
    """
    Extract JSON content from a model response.

    The model might wrap JSON in markdown code blocks or include
    explanatory text. This function extracts just the JSON.

    Args:
        response: Raw response text from the model

    Returns:
        Extracted JSON string

    Raises:
        ValueError: If no valid JSON could be extracted
    """
    # Try to find JSON in markdown code blocks first
    # Pattern matches ```json ... ``` or just ``` ... ```
    code_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
    matches = re.findall(code_block_pattern, response)

    if matches:
        # Try each match to find valid JSON
        for match in matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue

    # Try to find JSON object directly (starts with { ends with })
    # Use a more robust approach - find the outermost braces
    brace_start = response.find('{')
    if brace_start != -1:
        # Find matching closing brace
        depth = 0
        for i, char in enumerate(response[brace_start:], brace_start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    candidate = response[brace_start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    # Last resort: try the entire response
    try:
        json.loads(response.strip())
        return response.strip()
    except json.JSONDecodeError:
        pass

    raise ValueError("Could not extract valid JSON from response")


def read_file(file_path: str | Path) -> str:
    """
    Read content from a file.

    Args:
        file_path: Path to the file

    Returns:
        File content as string

    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If file isn't readable
    """
    path = Path(file_path)
    return path.read_text(encoding='utf-8')


def write_file(file_path: str | Path, content: str) -> None:
    """
    Write content to a file.

    Args:
        file_path: Path to the file
        content: Content to write
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def format_json(json_string: str, indent: int = 2) -> str:
    """
    Format JSON string with proper indentation.

    Args:
        json_string: JSON string to format
        indent: Number of spaces for indentation

    Returns:
        Formatted JSON string
    """
    data = json.loads(json_string)
    return json.dumps(data, indent=indent, ensure_ascii=False)


def get_file_size_kb(file_path: str | Path) -> float:
    """
    Get file size in kilobytes.

    Args:
        file_path: Path to the file

    Returns:
        File size in KB
    """
    path = Path(file_path)
    return path.stat().st_size / 1024


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.

    Args:
        text: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
