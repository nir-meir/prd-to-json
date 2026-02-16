"""
Base Extractor - Abstract base class for PRD component extractors.

All extractors inherit from this class and implement the extract method
for their specific component type (metadata, features, variables, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, List
import re

from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base class for PRD component extractors.

    Each extractor is responsible for extracting a specific type of
    component from the PRD text (e.g., features, variables, APIs).
    """

    def __init__(self):
        """Initialize the extractor."""
        self._patterns: List[re.Pattern] = []

    @property
    @abstractmethod
    def component_name(self) -> str:
        """Name of the component this extractor handles."""
        pass

    @abstractmethod
    def extract(self, content: str, **kwargs) -> Any:
        """
        Extract component(s) from PRD content.

        Args:
            content: Raw PRD text content
            **kwargs: Additional context (e.g., llm_client, features)

        Returns:
            Extracted component(s) - type depends on implementation
        """
        pass

    def _find_section(
        self,
        content: str,
        section_headers: List[str],
        end_headers: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Find a section in the PRD by header.

        Args:
            content: PRD content
            section_headers: Possible headers for the section
            end_headers: Headers that mark the end of the section

        Returns:
            Section content or None if not found
        """
        content_lower = content.lower()

        # Find start of section
        start_pos = -1
        for header in section_headers:
            # Try with markdown formatting
            patterns = [
                f"## {header.lower()}",
                f"# {header.lower()}",
                f"### {header.lower()}",
                f"**{header.lower()}**",
                f"{header.lower()}:",
            ]
            for pattern in patterns:
                pos = content_lower.find(pattern)
                if pos != -1:
                    start_pos = pos
                    break
            if start_pos != -1:
                break

        if start_pos == -1:
            return None

        # Find end of section
        end_pos = len(content)
        if end_headers:
            for header in end_headers:
                patterns = [
                    f"\n## {header.lower()}",
                    f"\n# {header.lower()}",
                    f"\n### {header.lower()}",
                ]
                for pattern in patterns:
                    pos = content_lower.find(pattern, start_pos + 1)
                    if pos != -1 and pos < end_pos:
                        end_pos = pos
        else:
            # Find next major section
            for pattern in ["\n## ", "\n# "]:
                pos = content_lower.find(pattern, start_pos + 1)
                if pos != -1 and pos < end_pos:
                    end_pos = pos

        return content[start_pos:end_pos].strip()

    def _extract_list_items(self, text: str) -> List[str]:
        """
        Extract list items from text (bullet points or numbered).

        Args:
            text: Text containing a list

        Returns:
            List of item strings
        """
        items = []

        # Match bullet points (*, -, •) and numbered lists
        pattern = r'(?:^|\n)\s*(?:[\*\-•]|\d+\.)\s*(.+?)(?=\n\s*(?:[\*\-•]|\d+\.)|$)'
        matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)

        for match in matches:
            item = match.strip()
            if item:
                items.append(item)

        return items

    def _extract_table_rows(self, text: str) -> List[List[str]]:
        """
        Extract rows from a markdown table.

        Args:
            text: Text containing a markdown table

        Returns:
            List of rows, where each row is a list of cell values
        """
        rows = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if line.startswith('|') and line.endswith('|'):
                # Skip separator lines
                if set(line.replace('|', '').replace('-', '').replace(':', '').strip()) == set():
                    continue

                # Extract cells
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if any(cells):  # Skip empty rows
                    rows.append(cells)

        return rows

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Remove markdown artifacts
        text = re.sub(r'\*{2,}', '', text)
        text = re.sub(r'#{1,}\s*', '', text)

        return text.strip()

    def _extract_key_value(self, text: str, key: str) -> Optional[str]:
        """
        Extract a value for a given key from text.

        Handles formats like:
        - Key: Value
        - Key = Value
        - **Key**: Value

        Args:
            text: Text to search
            key: Key to find

        Returns:
            Value or None
        """
        patterns = [
            rf'{re.escape(key)}\s*:\s*(.+?)(?:\n|$)',
            rf'{re.escape(key)}\s*=\s*(.+?)(?:\n|$)',
            rf'\*\*{re.escape(key)}\*\*\s*:\s*(.+?)(?:\n|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _use_llm_extraction(
        self,
        content: str,
        prompt: str,
        llm_client: BaseLLMClient,
    ) -> str:
        """
        Use LLM for extraction when pattern matching isn't sufficient.

        Args:
            content: PRD content
            prompt: Extraction prompt
            llm_client: LLM client

        Returns:
            LLM response content
        """
        response = llm_client.generate(
            prompt=content,
            system_prompt=prompt,
        )

        if not response.success:
            logger.warning(f"LLM extraction failed: {response.error_message}")
            return ""

        return response.content
