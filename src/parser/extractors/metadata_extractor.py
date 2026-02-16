"""
Metadata Extractor - Extract agent metadata from PRD documents.

Extracts:
- Agent name
- Description
- Language (en-US, he-IL, etc.)
- Channel (voice, text, both)
- Version/Phase information
"""

import re
import json
from typing import Optional

from .base import BaseExtractor
from ..models import AgentMetadata, Channel
from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class MetadataExtractor(BaseExtractor):
    """
    Extractor for agent metadata.

    Attempts pattern-based extraction first, falls back to LLM
    for complex or unstructured PRDs.
    """

    @property
    def component_name(self) -> str:
        return "metadata"

    def extract(
        self,
        content: str,
        llm_client: Optional[BaseLLMClient] = None,
        **kwargs
    ) -> AgentMetadata:
        """
        Extract agent metadata from PRD content.

        Args:
            content: Raw PRD text
            llm_client: Optional LLM client for assisted extraction

        Returns:
            AgentMetadata object
        """
        logger.debug("Extracting metadata...")

        # Try pattern-based extraction first
        name = self._extract_name(content)
        description = self._extract_description(content)
        language = self._extract_language(content)
        channel = self._extract_channel(content)
        phase = self._extract_phase(content)

        # If pattern extraction failed for critical fields, try LLM
        if not name and llm_client:
            logger.debug("Using LLM for metadata extraction")
            llm_metadata = self._llm_extract(content, llm_client)
            if llm_metadata:
                name = name or llm_metadata.get('name')
                description = description or llm_metadata.get('description')
                language = language or llm_metadata.get('language')
                channel = channel or llm_metadata.get('channel')

        return AgentMetadata(
            name=name or "Unnamed Agent",
            description=description or "",
            language=language or "en-US",
            channel=Channel.from_string(channel or "both"),
            phase=phase or 1,
        )

    def _extract_name(self, content: str) -> Optional[str]:
        """Extract agent/bot name from content."""
        # Try common patterns

        # Pattern 1: Title at start of document
        # e.g., "# Agent Name" or "## Bot Name PRD"
        title_match = re.search(r'^#\s*(.+?)(?:\s+PRD|\s+Bot|\s*$)', content, re.MULTILINE | re.IGNORECASE)
        if title_match:
            name = title_match.group(1).strip()
            # Clean up common suffixes
            name = re.sub(r'\s*(PRD|Document|Specification|Spec|Requirements?)\s*$', '', name, flags=re.IGNORECASE)
            if name and len(name) < 100:
                return name

        # Pattern 2: Explicit name field
        # e.g., "Agent Name: Customer Support Bot"
        patterns = [
            r'(?:Agent|Bot)\s*Name\s*:\s*(.+?)(?:\n|$)',
            r'Name\s*:\s*(.+?)(?:\n|$)',
            r'Project\s*(?:Name|Title)\s*:\s*(.+?)(?:\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name and len(name) < 100:
                    return name

        # Pattern 3: Look for "AI" or "Bot" in first few lines
        first_lines = content[:500]
        bot_match = re.search(r'([\w\s]+(?:AI|Bot|Agent|Assistant))', first_lines, re.IGNORECASE)
        if bot_match:
            name = bot_match.group(1).strip()
            if name and len(name) < 50:
                return name

        return None

    def _extract_description(self, content: str) -> Optional[str]:
        """Extract agent description from content."""
        # Try to find description section
        section = self._find_section(
            content,
            ['Description', 'Overview', 'Summary', 'Introduction', 'About'],
            ['Features', 'Requirements', 'Scope']
        )

        if section:
            # Get first paragraph
            paragraphs = section.split('\n\n')
            for para in paragraphs:
                para = self._clean_text(para)
                if len(para) > 20 and not para.startswith('#'):
                    return para[:500]  # Limit length

        # Try explicit description field
        desc_match = re.search(
            r'Description\s*:\s*(.+?)(?:\n\n|\n#|$)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if desc_match:
            return desc_match.group(1).strip()[:500]

        return None

    def _extract_language(self, content: str) -> Optional[str]:
        """Extract language from content."""
        content_lower = content.lower()

        # Check for explicit language mentions
        language_patterns = [
            (r'language\s*:\s*(hebrew|he-il|he)', 'he-IL'),
            (r'language\s*:\s*(english|en-us|en)', 'en-US'),
            (r'agent_language\s*:\s*"?(he-il|he)"?', 'he-IL'),
            (r'agent_language\s*:\s*"?(en-us|en)"?', 'en-US'),
            (r'respond\s+in\s+hebrew', 'he-IL'),
            (r'respond\s+in\s+english', 'en-US'),
            (r'hebrew\s+(?:bot|agent|response)', 'he-IL'),
            (r'english\s+(?:bot|agent|response)', 'en-US'),
        ]

        for pattern, language in language_patterns:
            if re.search(pattern, content_lower):
                return language

        # Check for Hebrew text presence (indicates Hebrew agent)
        hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        hebrew_matches = hebrew_pattern.findall(content)
        if len(hebrew_matches) > 10:  # Significant Hebrew content
            return 'he-IL'

        return None

    def _extract_channel(self, content: str) -> Optional[str]:
        """Extract channel type from content."""
        content_lower = content.lower()

        # Check for explicit channel mentions
        channel_patterns = [
            (r'channel\s*:\s*(voice|audio|phone|call)', 'voice'),
            (r'channel\s*:\s*(text|chat|whatsapp|sms)', 'text'),
            (r'channel\s*:\s*(both|dual|all)', 'both'),
            (r'voice\s*(?:bot|agent|channel)', 'voice'),
            (r'(?:text|chat|whatsapp)\s*(?:bot|agent|channel)', 'text'),
            (r'text\s*\+\s*audio', 'both'),
            (r'audio\s*\+\s*text', 'both'),
        ]

        voice_found = False
        text_found = False

        for pattern, channel in channel_patterns:
            if re.search(pattern, content_lower):
                if channel == 'voice':
                    voice_found = True
                elif channel == 'text':
                    text_found = True
                elif channel == 'both':
                    return 'both'

        if voice_found and text_found:
            return 'both'
        elif voice_found:
            return 'voice'
        elif text_found:
            return 'text'

        # Check for flow sections that indicate channels
        if 'flow (audio)' in content_lower or 'voice flow' in content_lower:
            voice_found = True
        if 'flow (text)' in content_lower or 'text flow' in content_lower or 'whatsapp' in content_lower:
            text_found = True

        if voice_found and text_found:
            return 'both'
        elif voice_found:
            return 'voice'
        elif text_found:
            return 'text'

        return None

    def _extract_phase(self, content: str) -> Optional[int]:
        """Extract project phase from content."""
        # Look for phase indicators
        phase_match = re.search(r'phase\s*:?\s*(\d+)', content, re.IGNORECASE)
        if phase_match:
            return int(phase_match.group(1))

        # Check table format
        table_match = re.search(r'\|\s*Phase\s*\|\s*Phase\s*(\d+)', content, re.IGNORECASE)
        if table_match:
            return int(table_match.group(1))

        return None

    def _llm_extract(
        self,
        content: str,
        llm_client: BaseLLMClient
    ) -> Optional[dict]:
        """Use LLM to extract metadata."""
        prompt = """Extract agent metadata from this PRD document.

Return ONLY a JSON object with these fields:
{
  "name": "Agent name from the document",
  "description": "Brief description of what the agent does",
  "language": "he-IL or en-US",
  "channel": "voice or text or both"
}

Output ONLY valid JSON, no explanations."""

        try:
            response = llm_client.generate(
                prompt=content[:5000],  # Limit content to reduce tokens
                system_prompt=prompt,
            )

            if response.success:
                # Try to parse JSON from response
                json_match = re.search(r'\{[^{}]*\}', response.content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())

        except Exception as e:
            logger.warning(f"LLM metadata extraction failed: {e}")

        return None
