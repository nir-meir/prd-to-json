"""
Rule Extractor - Extract business rules from PRD documents.

Extracts:
- Business rules and constraints
- Conditions and actions
- Rule applicability (which features)
- Priority ordering
"""

import re
import json
from typing import Optional, List, Dict, Any

from .base import BaseExtractor
from ..models import BusinessRule
from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class RuleExtractor(BaseExtractor):
    """
    Extractor for business rules.

    Business rules define conditional logic that applies across
    features, such as working hours, authentication requirements,
    transfer conditions, etc.
    """

    @property
    def component_name(self) -> str:
        return "rules"

    def extract(
        self,
        content: str,
        llm_client: Optional[BaseLLMClient] = None,
        **kwargs
    ) -> List[BusinessRule]:
        """
        Extract business rules from PRD content.

        Args:
            content: Raw PRD text
            llm_client: Optional LLM client for assisted extraction

        Returns:
            List of BusinessRule objects
        """
        logger.debug("Extracting business rules...")

        rules = []
        seen_ids = set()

        # Extract explicitly defined rules
        explicit_rules = self._extract_explicit_rules(content)
        for rule in explicit_rules:
            if rule.id not in seen_ids:
                rules.append(rule)
                seen_ids.add(rule.id)

        # Extract rules from flow conditions
        flow_rules = self._extract_from_flows(content)
        for rule in flow_rules:
            if rule.id not in seen_ids:
                rules.append(rule)
                seen_ids.add(rule.id)

        # Extract common patterns as rules
        pattern_rules = self._extract_common_patterns(content)
        for rule in pattern_rules:
            if rule.id not in seen_ids:
                rules.append(rule)
                seen_ids.add(rule.id)

        # Use LLM for complex rule extraction
        if len(rules) < 2 and llm_client:
            logger.debug("Using LLM for rule extraction")
            llm_rules = self._llm_extract_rules(content, llm_client)
            for rule in llm_rules:
                if rule.id not in seen_ids:
                    rules.append(rule)
                    seen_ids.add(rule.id)

        logger.info(f"Extracted {len(rules)} business rules")
        return rules

    def _extract_explicit_rules(self, content: str) -> List[BusinessRule]:
        """Extract explicitly defined business rules."""
        rules = []

        # Find business rules section
        rule_section = self._find_section(
            content,
            ['Business Rules', 'Rules', 'Constraints', 'Logic Rules'],
            ['Flow', 'Features', 'APIs', 'Variables']
        )

        if not rule_section:
            return rules

        # Try table format
        table_rules = self._extract_from_table(rule_section)
        rules.extend(table_rules)

        # Try section format with BR-XX IDs
        section_rules = self._extract_from_sections(rule_section)
        rules.extend(section_rules)

        # Try list format
        list_rules = self._extract_from_list(rule_section)
        rules.extend(list_rules)

        return rules

    def _extract_from_table(self, content: str) -> List[BusinessRule]:
        """Extract rules from markdown table."""
        rules = []

        rows = self._extract_table_rows(content)

        if not rows:
            return rules

        # Detect columns
        header = rows[0]
        id_col = self._find_column_index(header, ['id', 'rule id', 'code'])
        name_col = self._find_column_index(header, ['name', 'rule', 'title'])
        cond_col = self._find_column_index(header, ['condition', 'when', 'if'])
        action_col = self._find_column_index(header, ['action', 'then', 'do'])
        desc_col = self._find_column_index(header, ['description', 'desc', 'details'])
        applies_col = self._find_column_index(header, ['applies to', 'features', 'scope'])

        data_rows = rows[1:] if len(rows) > 1 else []

        for i, row in enumerate(data_rows):
            rule_id = self._get_cell(row, id_col, f'BR-{i+1:02d}')
            if rule_id.startswith('-'):
                continue

            rule_id = re.sub(r'[`*]', '', rule_id).strip()
            if not rule_id.upper().startswith('BR-'):
                rule_id = f'BR-{rule_id}'

            name = self._get_cell(row, name_col, '')
            condition = self._get_cell(row, cond_col, '')
            action = self._get_cell(row, action_col, '')
            description = self._get_cell(row, desc_col, '')
            applies_to = self._parse_applies_to(self._get_cell(row, applies_col, ''))

            if not description and condition and action:
                description = f"When {condition}, then {action}"

            rule = BusinessRule(
                id=rule_id.upper(),
                name=name or f"Rule {rule_id}",
                description=description,
                condition=condition,
                action=action,
                applies_to=applies_to,
                priority=len(data_rows) - i,  # Earlier rules have higher priority
            )
            rules.append(rule)

        return rules

    def _extract_from_sections(self, content: str) -> List[BusinessRule]:
        """Extract rules from section format."""
        rules = []

        # Pattern: ### BR-XX: Rule Name
        pattern = re.compile(
            r'###?\s*(BR-?\d+)[:\s-]+(.+?)(?=\n###|\n##|$)',
            re.IGNORECASE | re.DOTALL
        )

        for match in pattern.finditer(content):
            rule_id = match.group(1).upper()
            if not rule_id.startswith('BR-'):
                rule_id = 'BR-' + rule_id.lstrip('BR')

            content_block = match.group(2).strip()
            lines = content_block.split('\n')

            name = lines[0].strip() if lines else ""
            name = re.sub(r'\*+', '', name)

            rest_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""

            # Extract condition
            condition = ""
            cond_match = re.search(
                r'(?:condition|when|if)\s*:\s*(.+?)(?:\n\n|\naction|\nthen|$)',
                rest_content,
                re.IGNORECASE | re.DOTALL
            )
            if cond_match:
                condition = self._clean_text(cond_match.group(1))

            # Extract action
            action = ""
            action_match = re.search(
                r'(?:action|then|do)\s*:\s*(.+?)(?:\n\n|\napplies|$)',
                rest_content,
                re.IGNORECASE | re.DOTALL
            )
            if action_match:
                action = self._clean_text(action_match.group(1))

            # Extract applies to
            applies_to = []
            applies_match = re.search(
                r'(?:applies to|features?|scope)\s*:\s*(.+?)(?:\n\n|$)',
                rest_content,
                re.IGNORECASE
            )
            if applies_match:
                applies_to = self._parse_applies_to(applies_match.group(1))

            # Build description
            description = ""
            if condition and action:
                description = f"When {condition}, then {action}"
            elif rest_content:
                # Use first paragraph
                paragraphs = rest_content.split('\n\n')
                for para in paragraphs:
                    para = self._clean_text(para)
                    if len(para) > 20:
                        description = para[:300]
                        break

            rule = BusinessRule(
                id=rule_id,
                name=name,
                description=description,
                condition=condition,
                action=action,
                applies_to=applies_to,
            )
            rules.append(rule)

        return rules

    def _extract_from_list(self, content: str) -> List[BusinessRule]:
        """Extract rules from list format."""
        rules = []

        items = self._extract_list_items(content)

        for i, item in enumerate(items):
            # Check if item looks like a rule
            if not any(kw in item.lower() for kw in ['if', 'when', 'must', 'should', 'always', 'never']):
                continue

            rule_id = f"BR-{i+1:02d}"

            # Try to extract ID from item
            id_match = re.match(r'(BR-?\d+)[:\s-]+(.+)', item, re.IGNORECASE)
            if id_match:
                rule_id = id_match.group(1).upper()
                if not rule_id.startswith('BR-'):
                    rule_id = 'BR-' + rule_id.lstrip('BR')
                item = id_match.group(2)

            # Parse condition and action
            condition, action = self._parse_condition_action(item)

            rule = BusinessRule(
                id=rule_id,
                name=item[:50],
                description=item,
                condition=condition,
                action=action,
            )
            rules.append(rule)

        return rules

    def _extract_from_flows(self, content: str) -> List[BusinessRule]:
        """Extract rules from flow descriptions."""
        rules = []

        # Common patterns that indicate business rules
        patterns = [
            # If/then patterns
            (r'If\s+(.+?),?\s+(?:then\s+)?(.+?)(?:\.|$)', 'COND'),
            # Must/should patterns
            (r'(?:must|should)\s+(.+?)(?:\.|$)', 'CONSTRAINT'),
            # Never/always patterns
            (r'(?:never|always)\s+(.+?)(?:\.|$)', 'CONSTRAINT'),
            # Working hours
            (r'(?:during|outside)\s+(?:working|business)\s+hours?\s*[,:]\s*(.+?)(?:\.|$)', 'HOURS'),
            # Transfer conditions
            (r'transfer\s+(?:to|when)\s+(.+?)(?:\.|$)', 'TRANSFER'),
        ]

        rule_count = 0
        for pattern, rule_type in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                rule_count += 1
                rule_id = f"BR-AUTO-{rule_count:02d}"

                if rule_type == 'COND':
                    condition = match.group(1).strip()
                    action = match.group(2).strip()
                else:
                    condition = ""
                    action = match.group(1).strip() if match.groups() else match.group(0)

                rule = BusinessRule(
                    id=rule_id,
                    name=f"Auto-extracted rule {rule_count}",
                    description=match.group(0).strip(),
                    condition=condition,
                    action=action,
                )
                rules.append(rule)

        return rules

    def _extract_common_patterns(self, content: str) -> List[BusinessRule]:
        """Extract common business rule patterns."""
        rules = []
        content_lower = content.lower()

        # Working hours rule
        if 'working hours' in content_lower or 'business hours' in content_lower:
            hours_match = re.search(
                r'(?:working|business)\s+hours\s*[:\-]?\s*'
                r'(?:(\d{1,2}:\d{2})\s*[-to]+\s*(\d{1,2}:\d{2})|'
                r'(\d{1,2})\s*[-to]+\s*(\d{1,2}))',
                content,
                re.IGNORECASE
            )
            if hours_match:
                start = hours_match.group(1) or hours_match.group(3)
                end = hours_match.group(2) or hours_match.group(4)
                rules.append(BusinessRule(
                    id="BR-HOURS",
                    name="Working Hours Gate",
                    description=f"Agent operates during working hours ({start} - {end})",
                    condition=f"current_time BETWEEN {start} AND {end}",
                    action="Allow self-service; otherwise transfer to voicemail/queue",
                ))

        # Authentication required
        if 'authenticated' in content_lower or 'authentication' in content_lower:
            rules.append(BusinessRule(
                id="BR-AUTH",
                name="Authentication Required",
                description="User must be authenticated before accessing services",
                condition="user.authenticated == false",
                action="Redirect to authentication flow",
            ))

        # Move to rep patterns
        if 'move to rep' in content_lower or 'movetorep' in content_lower:
            rules.append(BusinessRule(
                id="BR-TRANSFER",
                name="Human Transfer Condition",
                description="Transfer to human agent when MoveToRep flag is set",
                condition="MoveToRep == true",
                action="Transfer to human agent queue",
            ))

        return rules

    def _parse_condition_action(self, text: str) -> tuple:
        """Parse condition and action from rule text."""
        condition = ""
        action = ""

        # Pattern: If X then Y
        match = re.match(r'(?:if|when)\s+(.+?),?\s+(?:then\s+)?(.+)', text, re.IGNORECASE)
        if match:
            condition = match.group(1).strip()
            action = match.group(2).strip()
        else:
            # Use entire text as action
            action = text

        return condition, action

    def _parse_applies_to(self, applies_str: str) -> List[str]:
        """Parse feature IDs from applies_to string."""
        if not applies_str:
            return []

        # Extract F-XX patterns
        feature_ids = re.findall(r'F-?\d+', applies_str, re.IGNORECASE)
        return [fid.upper() if fid.upper().startswith('F-') else f'F-{fid}' for fid in feature_ids]

    def _find_column_index(self, header: List[str], candidates: List[str]) -> int:
        """Find column index matching any of the candidate names."""
        for i, cell in enumerate(header):
            cell_lower = cell.lower().strip()
            for candidate in candidates:
                if candidate in cell_lower:
                    return i
        return -1

    def _get_cell(self, row: List[str], index: int, default: str) -> str:
        """Get cell value at index or return default."""
        if 0 <= index < len(row):
            value = row[index].strip()
            return value if value else default
        return default

    def _llm_extract_rules(
        self,
        content: str,
        llm_client: BaseLLMClient
    ) -> List[BusinessRule]:
        """Use LLM to extract business rules from content."""
        prompt = """Extract business rules from this PRD document.

Business rules are conditional logic that applies across features, such as:
- Working hours restrictions
- Authentication requirements
- Transfer/escalation conditions
- Data validation rules
- Priority rules

Return ONLY a JSON array with this structure:
[
  {
    "id": "BR-01",
    "name": "Rule Name",
    "description": "What this rule does",
    "condition": "When this is true",
    "action": "Do this",
    "applies_to": ["F-01", "F-02"]
  }
]

Output ONLY valid JSON, no explanations."""

        try:
            response = llm_client.generate(
                prompt=content[:6000],
                system_prompt=prompt,
            )

            if response.success:
                json_match = re.search(r'\[[\s\S]*\]', response.content)
                if json_match:
                    data = json.loads(json_match.group())
                    rules = []
                    for item in data:
                        rule = BusinessRule(
                            id=item.get('id', f'BR-{len(rules)+1:02d}'),
                            name=item.get('name', ''),
                            description=item.get('description', ''),
                            condition=item.get('condition', ''),
                            action=item.get('action', ''),
                            applies_to=item.get('applies_to', []),
                        )
                        if rule.name:
                            rules.append(rule)
                    return rules

        except Exception as e:
            logger.warning(f"LLM rule extraction failed: {e}")

        return []
