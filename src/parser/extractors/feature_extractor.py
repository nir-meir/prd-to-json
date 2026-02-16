"""
Feature Extractor - Extract features and user stories from PRD documents.

Extracts:
- Feature definitions (F-XX)
- User stories (US-XXX)
- Flow steps per channel
- Dependencies between features
"""

import re
import json
from typing import Optional, List, Dict, Any

from .base import BaseExtractor
from ..models import Feature, UserStory, FlowStep, FlowStepType, Channel
from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class FeatureExtractor(BaseExtractor):
    """
    Extractor for features and user stories.

    Handles multiple PRD formats:
    - Markdown with ## Feature sections
    - Tables with feature definitions
    - Free-form text with feature descriptions
    """

    @property
    def component_name(self) -> str:
        return "features"

    def extract(
        self,
        content: str,
        llm_client: Optional[BaseLLMClient] = None,
        **kwargs
    ) -> List[Feature]:
        """
        Extract features from PRD content.

        Args:
            content: Raw PRD text
            llm_client: Optional LLM client for assisted extraction

        Returns:
            List of Feature objects
        """
        logger.debug("Extracting features...")

        features = []

        # Try structured extraction first
        features = self._extract_structured_features(content)

        # If no features found or too few, try LLM extraction
        if len(features) < 2 and llm_client:
            logger.debug("Using LLM for feature extraction")
            llm_features = self._llm_extract_features(content, llm_client)
            if llm_features:
                features = llm_features

        # Extract user stories and associate with features
        user_stories = self._extract_user_stories(content)
        self._associate_stories_with_features(features, user_stories)

        # Extract flow information for each feature
        for feature in features:
            self._extract_flow_for_feature(feature, content)

        logger.info(f"Extracted {len(features)} features")
        return features

    def _extract_structured_features(self, content: str) -> List[Feature]:
        """Extract features from structured PRD format."""
        features = []

        # Pattern 1: Feature sections with F-XX IDs
        # Handles multiple formats:
        # - "## Feature F-01: Customer Authentication"
        # - "## **F-01. Authentication (WhatsApp Text)**"
        # - "## F-01 - Authentication"
        feature_pattern = re.compile(
            r'(?:^|\n)#+\s*\*{0,2}\s*(?:Feature\s+)?(F-?\d+)[\.\:\s\-]+\s*(.+?)(?:\*{0,2})?(?:\n|$)',
            re.IGNORECASE | re.MULTILINE
        )

        matches = list(feature_pattern.finditer(content))

        for i, match in enumerate(matches):
            feature_id = match.group(1).upper()
            # Normalize ID format to F-XX
            if not feature_id.startswith('F-'):
                feature_id = 'F-' + feature_id.lstrip('F')

            name = match.group(2).strip()
            name = re.sub(r'\*+', '', name)  # Remove markdown bold

            # Find feature content (until next feature or section)
            start_pos = match.end()
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                # Find next major section
                next_section = re.search(r'\n##\s+[^F]', content[start_pos:])
                end_pos = start_pos + next_section.start() if next_section else len(content)

            feature_content = content[start_pos:end_pos]

            # Extract description
            description = self._extract_feature_description(feature_content)

            # Determine channel
            channel = self._determine_channel(feature_content)

            # Extract phase
            phase = self._extract_phase(feature_content)

            # Extract variables used
            variables_used = self._extract_referenced_variables(feature_content)

            # Extract APIs used
            apis_used = self._extract_referenced_apis(feature_content)

            feature = Feature(
                id=feature_id,
                name=name,
                description=description,
                channel=channel,
                phase=phase,
                variables_used=variables_used,
                apis_used=apis_used,
            )
            features.append(feature)

        # Pattern 2: Table format
        if not features:
            features = self._extract_from_table(content)

        return features

    def _extract_from_table(self, content: str) -> List[Feature]:
        """Extract features from markdown table format."""
        features = []

        # Find feature tables
        table_section = self._find_section(
            content,
            ['Features', 'Feature List', 'Feature Summary'],
            ['User Stories', 'Variables', 'APIs']
        )

        if not table_section:
            return features

        rows = self._extract_table_rows(table_section)

        # Skip header row
        if rows and any('id' in cell.lower() or 'feature' in cell.lower() for cell in rows[0]):
            rows = rows[1:]

        for row in rows:
            if len(row) >= 2:
                feature_id = row[0].strip()
                name = row[1].strip() if len(row) > 1 else ""
                description = row[2].strip() if len(row) > 2 else ""

                # Normalize ID
                if not feature_id.upper().startswith('F-'):
                    feature_id = f"F-{feature_id}"

                if feature_id and name:
                    feature = Feature(
                        id=feature_id.upper(),
                        name=name,
                        description=description,
                    )
                    features.append(feature)

        return features

    def _extract_feature_description(self, content: str) -> str:
        """Extract description from feature content."""
        # Try to find explicit description
        desc_match = re.search(
            r'(?:Description|Overview)[:\s]*(.+?)(?:\n\n|\n#|\n\*\*)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if desc_match:
            return self._clean_text(desc_match.group(1).strip())[:500]

        # Otherwise, use first paragraph
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            para = self._clean_text(para)
            if len(para) > 30 and not para.startswith(('#', '|', '-', '*')):
                return para[:500]

        return ""

    def _determine_channel(self, content: str) -> Channel:
        """Determine channel from feature content."""
        content_lower = content.lower()

        has_voice = bool(re.search(r'voice|audio|phone|call|flow\s*\(audio\)', content_lower))
        has_text = bool(re.search(r'text|chat|whatsapp|sms|flow\s*\(text\)', content_lower))

        if has_voice and has_text:
            return Channel.BOTH
        elif has_voice:
            return Channel.VOICE
        elif has_text:
            return Channel.TEXT
        else:
            return Channel.BOTH

    def _extract_phase(self, content: str) -> int:
        """Extract phase number from content."""
        phase_match = re.search(r'phase\s*:?\s*(\d+)', content, re.IGNORECASE)
        if phase_match:
            return int(phase_match.group(1))
        return 1

    def _extract_referenced_variables(self, content: str) -> List[str]:
        """Extract variable names referenced in content."""
        variables = set()

        # Pattern 1: {{variable_name}}
        mustache_vars = re.findall(r'\{\{(\w+)\}\}', content)
        variables.update(mustache_vars)

        # Pattern 2: `variable_name` or ${variable_name}
        code_vars = re.findall(r'[`$]\{?(\w+)\}?', content)
        variables.update(code_vars)

        # Pattern 3: Variable: value references
        var_refs = re.findall(r'(?:variable|var|param)[:\s]+[`"]?(\w+)[`"]?', content, re.IGNORECASE)
        variables.update(var_refs)

        return list(variables)

    def _extract_referenced_apis(self, content: str) -> List[str]:
        """Extract API names referenced in content."""
        apis = set()

        # Pattern 1: API/function names
        api_patterns = [
            r'(?:call|invoke|use)\s+(?:the\s+)?[`"]?(\w+)[`"]?\s+(?:API|function|endpoint)',
            r'(?:API|function|endpoint)[:\s]+[`"]?(\w+)[`"]?',
            r'\b(get|post|fetch|send|check|verify|create|update|delete)_\w+',
        ]

        for pattern in api_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            apis.update(matches)

        return list(apis)

    def _extract_user_stories(self, content: str) -> List[UserStory]:
        """Extract user stories from PRD content."""
        stories = []

        # Find user story sections
        story_section = self._find_section(
            content,
            ['User Stories', 'User Story', 'Stories'],
            ['Features', 'Flow', 'Implementation']
        )

        if not story_section:
            # Try to find stories inline
            story_section = content

        # Pattern: US-XXX: Description or US-XXX | Description
        story_pattern = re.compile(
            r'(US-?\d+)[:\s|]+(.+?)(?:\n(?=US-?\d+)|$)',
            re.IGNORECASE | re.DOTALL
        )

        for match in story_pattern.finditer(story_section):
            story_id = match.group(1).upper()
            if not story_id.startswith('US-'):
                story_id = 'US-' + story_id.lstrip('US')

            description = self._clean_text(match.group(2).strip())

            # Extract acceptance criteria if present
            criteria = []
            criteria_match = re.search(
                r'acceptance\s+criteria[:\s]*(.+?)(?:\n\n|$)',
                match.group(0),
                re.IGNORECASE | re.DOTALL
            )
            if criteria_match:
                criteria = self._extract_list_items(criteria_match.group(1))

            stories.append(UserStory(
                id=story_id,
                description=description,
                acceptance_criteria=criteria,
            ))

        return stories

    def _associate_stories_with_features(
        self,
        features: List[Feature],
        stories: List[UserStory]
    ) -> None:
        """Associate user stories with features."""
        # Build feature ID to feature mapping
        feature_map = {f.id: f for f in features}

        # Try to match stories to features by ID pattern or content
        for story in stories:
            # Check if story ID contains feature reference
            # e.g., US-F01-001 belongs to F-01
            feature_ref = re.search(r'F-?(\d+)', story.id, re.IGNORECASE)
            if feature_ref:
                feature_id = f"F-{feature_ref.group(1).zfill(2)}"
                if feature_id in feature_map:
                    feature_map[feature_id].user_stories.append(story)
                    continue

            # Try to match by story content mentioning feature
            for feature in features:
                if feature.name.lower() in story.description.lower():
                    feature.user_stories.append(story)
                    break

    def _extract_flow_for_feature(self, feature: Feature, content: str) -> None:
        """Extract flow information for a feature."""
        # Find feature-specific content
        feature_pattern = re.compile(
            rf'(?:^|\n)#+\s*(?:Feature\s+)?{re.escape(feature.id)}[:\s-].*?'
            r'(?=\n#+\s*(?:Feature\s+)?F-?\d+|\n##\s+[^F]|$)',
            re.IGNORECASE | re.DOTALL
        )
        match = feature_pattern.search(content)

        if not match:
            return

        feature_content = match.group(0)

        # Extract text flow
        text_flow = self._find_section(
            feature_content,
            ['Flow (Text)', 'Text Flow', 'WhatsApp Flow', 'Chat Flow'],
            ['Flow (Audio)', 'Voice Flow', 'Acceptance']
        )
        if text_flow:
            feature.flow_text = self._clean_text(text_flow)
            feature.flow_steps.extend(self._parse_flow_steps(text_flow))

        # Extract audio flow
        audio_flow = self._find_section(
            feature_content,
            ['Flow (Audio)', 'Voice Flow', 'Audio Flow', 'Call Flow'],
            ['Acceptance', 'Requirements', 'Definition']
        )
        if audio_flow:
            feature.flow_audio = self._clean_text(audio_flow)
            if not feature.flow_steps:  # Only if no text flow steps yet
                feature.flow_steps.extend(self._parse_flow_steps(audio_flow))

        # Extract acceptance criteria
        ac_section = self._find_section(
            feature_content,
            ['Acceptance Criteria', 'AC', 'Criteria'],
            ['Definition of Done', 'DoD', 'Implementation']
        )
        if ac_section:
            feature.acceptance_criteria = self._extract_list_items(ac_section)

        # Extract definition of done
        dod_section = self._find_section(
            feature_content,
            ['Definition of Done', 'DoD', 'Done Criteria'],
            ['Implementation', 'Requirements', 'Questions']
        )
        if dod_section:
            feature.definition_of_done = self._extract_list_items(dod_section)

        # Extract open questions
        questions_section = self._find_section(
            feature_content,
            ['Open Questions', 'Questions', 'TBD'],
            ['Notes', 'Implementation']
        )
        if questions_section:
            feature.open_questions = self._extract_list_items(questions_section)

    def _parse_flow_steps(self, flow_text: str) -> List[FlowStep]:
        """Parse flow text into structured flow steps."""
        steps = []

        # Look for numbered or bulleted steps
        items = self._extract_list_items(flow_text)

        for i, item in enumerate(items):
            step_type = self._determine_step_type(item)
            step = FlowStep(
                order=i + 1,
                type=step_type,
                description=item,
            )

            # Extract additional details
            if step_type == FlowStepType.COLLECT:
                var_match = re.search(r'collect\s+[`"]?(\w+)[`"]?', item, re.IGNORECASE)
                if var_match:
                    step.variable_name = var_match.group(1)

            elif step_type == FlowStepType.API_CALL:
                api_match = re.search(r'(?:call|invoke)\s+[`"]?(\w+)[`"]?', item, re.IGNORECASE)
                if api_match:
                    step.api_name = api_match.group(1)

            elif step_type == FlowStepType.CONDITION:
                cond_match = re.search(r'(?:if|when|check)\s+(.+?)(?:then|:)', item, re.IGNORECASE)
                if cond_match:
                    step.condition = cond_match.group(1).strip()

            steps.append(step)

        return steps

    def _determine_step_type(self, step_text: str) -> FlowStepType:
        """Determine the type of flow step from its description."""
        text_lower = step_text.lower()

        if any(kw in text_lower for kw in ['collect', 'ask', 'request', 'get from user', 'input']):
            return FlowStepType.COLLECT
        elif any(kw in text_lower for kw in ['call api', 'invoke', 'fetch', 'send request', 'api call']):
            return FlowStepType.API_CALL
        elif any(kw in text_lower for kw in ['if ', 'when ', 'check ', 'condition', 'branch']):
            return FlowStepType.CONDITION
        elif any(kw in text_lower for kw in ['transfer', 'handoff', 'escalate', 'move to rep', 'human']):
            return FlowStepType.TRANSFER
        elif any(kw in text_lower for kw in ['set ', 'store ', 'save ', 'assign']):
            return FlowStepType.SET_VARIABLE
        elif any(kw in text_lower for kw in ['end', 'finish', 'complete', 'terminate', 'goodbye']):
            return FlowStepType.END
        elif any(kw in text_lower for kw in ['wait', 'delay', 'pause', 'sleep']):
            return FlowStepType.WAIT
        elif any(kw in text_lower for kw in ['repeat', 'loop', 'iterate', 'for each']):
            return FlowStepType.LOOP
        else:
            return FlowStepType.CONVERSATION

    def _llm_extract_features(
        self,
        content: str,
        llm_client: BaseLLMClient
    ) -> Optional[List[Feature]]:
        """Use LLM to extract features from unstructured content."""
        prompt = """Extract features from this PRD document.

Return ONLY a JSON array of features with this structure:
[
  {
    "id": "F-01",
    "name": "Feature Name",
    "description": "What this feature does",
    "channel": "voice or text or both",
    "variables_used": ["var1", "var2"],
    "apis_used": ["api1", "api2"]
  }
]

Output ONLY valid JSON, no explanations."""

        try:
            response = llm_client.generate(
                prompt=content[:8000],  # Limit content size
                system_prompt=prompt,
            )

            if response.success:
                # Parse JSON from response
                json_match = re.search(r'\[[\s\S]*\]', response.content)
                if json_match:
                    data = json.loads(json_match.group())
                    features = []
                    for item in data:
                        feature = Feature(
                            id=item.get('id', f'F-{len(features)+1:02d}'),
                            name=item.get('name', ''),
                            description=item.get('description', ''),
                            channel=Channel.from_string(item.get('channel', 'both')),
                            variables_used=item.get('variables_used', []),
                            apis_used=item.get('apis_used', []),
                        )
                        features.append(feature)
                    return features

        except Exception as e:
            logger.warning(f"LLM feature extraction failed: {e}")

        return None
