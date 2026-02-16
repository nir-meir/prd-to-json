"""
Variable Extractor - Extract variables from PRD documents.

Extracts:
- Variable definitions
- Types and validation rules
- Sources (user input, collection, API response)
- Default values and options
"""

import re
import json
from typing import Optional, List, Dict, Any

from .base import BaseExtractor
from ..models import Variable, VariableType, VariableSource, ValidationRule, Feature
from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class VariableExtractor(BaseExtractor):
    """
    Extractor for variables.

    Variables can be defined explicitly in tables/lists or
    inferred from flow descriptions and API specifications.
    """

    @property
    def component_name(self) -> str:
        return "variables"

    def extract(
        self,
        content: str,
        features: Optional[List[Feature]] = None,
        llm_client: Optional[BaseLLMClient] = None,
        **kwargs
    ) -> List[Variable]:
        """
        Extract variables from PRD content.

        Args:
            content: Raw PRD text
            features: Optional list of extracted features (for context)
            llm_client: Optional LLM client for assisted extraction

        Returns:
            List of Variable objects
        """
        logger.debug("Extracting variables...")

        variables = []
        seen_names = set()

        # Extract explicitly defined variables
        explicit_vars = self._extract_explicit_variables(content)
        for var in explicit_vars:
            if var.name not in seen_names:
                variables.append(var)
                seen_names.add(var.name)

        # Extract variables from feature flows
        if features:
            flow_vars = self._extract_from_features(features, content)
            for var in flow_vars:
                if var.name not in seen_names:
                    variables.append(var)
                    seen_names.add(var.name)

        # Extract variables referenced in content but not yet defined
        referenced_vars = self._extract_referenced_variables(content, seen_names)
        for var in referenced_vars:
            if var.name not in seen_names:
                variables.append(var)
                seen_names.add(var.name)

        # Use LLM if we found very few variables
        if len(variables) < 3 and llm_client:
            logger.debug("Using LLM for variable extraction")
            llm_vars = self._llm_extract_variables(content, llm_client)
            for var in llm_vars:
                if var.name not in seen_names:
                    variables.append(var)
                    seen_names.add(var.name)

        logger.info(f"Extracted {len(variables)} variables")
        return variables

    def _extract_explicit_variables(self, content: str) -> List[Variable]:
        """Extract variables from explicit definitions in the PRD."""
        variables = []

        # Method 1: Table format
        table_vars = self._extract_from_table(content)
        variables.extend(table_vars)

        # Method 2: List format
        list_vars = self._extract_from_list(content)
        variables.extend(list_vars)

        # Method 3: Key-value definitions
        kv_vars = self._extract_from_key_value(content)
        variables.extend(kv_vars)

        return variables

    def _extract_from_table(self, content: str) -> List[Variable]:
        """Extract variables from markdown tables."""
        variables = []

        # Find variable section
        var_section = self._find_section(
            content,
            ['Variables', 'Parameters', 'Data Fields', 'Input Variables'],
            ['APIs', 'Flow', 'Features', 'Business Rules']
        )

        if not var_section:
            return variables

        rows = self._extract_table_rows(var_section)

        # Detect header row and column indices
        header_row = rows[0] if rows else []
        name_col = self._find_column_index(header_row, ['name', 'variable', 'field', 'parameter'])
        type_col = self._find_column_index(header_row, ['type', 'data type', 'format'])
        desc_col = self._find_column_index(header_row, ['description', 'desc', 'details', 'purpose'])
        source_col = self._find_column_index(header_row, ['source', 'origin', 'from'])
        required_col = self._find_column_index(header_row, ['required', 'mandatory', 'req'])
        default_col = self._find_column_index(header_row, ['default', 'default value'])

        # Skip header row
        data_rows = rows[1:] if len(rows) > 1 else []

        for row in data_rows:
            if not row or all(cell.strip() == '' for cell in row):
                continue

            name = self._get_cell(row, name_col, '')
            if not name or name.startswith('-'):
                continue

            # Clean name
            name = re.sub(r'[`*]', '', name).strip()

            variable = Variable(
                name=name,
                type=VariableType.from_string(self._get_cell(row, type_col, 'string')),
                description=self._get_cell(row, desc_col, ''),
                source=self._parse_source(self._get_cell(row, source_col, 'user')),
                required=self._parse_bool(self._get_cell(row, required_col, 'false')),
                default=self._parse_default(self._get_cell(row, default_col, None)),
            )
            variables.append(variable)

        return variables

    def _extract_from_list(self, content: str) -> List[Variable]:
        """Extract variables from list format."""
        variables = []

        # Find variable section
        var_section = self._find_section(
            content,
            ['Variables', 'Parameters', 'Data Fields'],
            ['APIs', 'Flow', 'Features']
        )

        if not var_section:
            return variables

        # Pattern: - **variable_name** (type): description
        pattern = re.compile(
            r'[-*]\s*\*?\*?([a-zA-Z_]\w*)\*?\*?\s*'
            r'(?:\(([^)]+)\))?\s*'
            r'[:-]?\s*(.+?)(?:\n|$)',
            re.MULTILINE
        )

        for match in pattern.finditer(var_section):
            name = match.group(1).strip()
            type_str = match.group(2) or 'string'
            description = match.group(3).strip()

            # Skip if name looks like a header
            if name.lower() in ('variables', 'parameters', 'name', 'type'):
                continue

            variable = Variable(
                name=name,
                type=VariableType.from_string(type_str),
                description=description,
            )
            variables.append(variable)

        return variables

    def _extract_from_key_value(self, content: str) -> List[Variable]:
        """Extract variables from key-value definitions."""
        variables = []

        # Pattern: Variable Name: value or `variable_name`: description
        patterns = [
            r'Variable\s*Name\s*:\s*([a-zA-Z_]\w+)',
            r'`([a-zA-Z_]\w+)`\s*[-:]\s*(.+?)(?:\n|$)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                name = match.group(1).strip()
                description = match.group(2).strip() if len(match.groups()) > 1 else ''

                if name and len(name) < 50:
                    variable = Variable(
                        name=name,
                        type=VariableType.STRING,
                        description=description,
                    )
                    variables.append(variable)

        return variables

    def _extract_from_features(
        self,
        features: List[Feature],
        content: str
    ) -> List[Variable]:
        """Extract variables from feature flows."""
        variables = []
        seen = set()

        for feature in features:
            # Variables referenced by feature
            for var_name in feature.variables_used:
                if var_name not in seen:
                    # Try to find definition in content
                    var_def = self._find_variable_definition(var_name, content)
                    variables.append(var_def)
                    seen.add(var_name)

            # Variables from flow steps
            for step in feature.flow_steps:
                if step.variable_name and step.variable_name not in seen:
                    var = Variable(
                        name=step.variable_name,
                        type=VariableType.STRING,
                        description=f"Collected in {feature.name}",
                        source=VariableSource.COLLECT,
                    )
                    variables.append(var)
                    seen.add(step.variable_name)

        return variables

    def _find_variable_definition(self, name: str, content: str) -> Variable:
        """Find variable definition in content by name."""
        # Try to find definition near the variable name
        pattern = re.compile(
            rf'{re.escape(name)}\s*'
            r'(?:\(([^)]+)\))?\s*'
            r'[-:]\s*(.+?)(?:\n|$)',
            re.IGNORECASE
        )

        match = pattern.search(content)
        if match:
            type_str = match.group(1) or 'string'
            description = match.group(2).strip()
            return Variable(
                name=name,
                type=VariableType.from_string(type_str),
                description=description,
            )

        # Return basic variable if no definition found
        return Variable(
            name=name,
            type=VariableType.STRING,
            description="",
        )

    def _extract_referenced_variables(
        self,
        content: str,
        existing_names: set
    ) -> List[Variable]:
        """Extract variables referenced in content but not yet defined."""
        variables = []

        # Pattern 1: {{variable_name}}
        mustache_vars = re.findall(r'\{\{(\w+)\}\}', content)

        # Pattern 2: ${variable_name}
        dollar_vars = re.findall(r'\$\{(\w+)\}', content)

        # Pattern 3: Common variable naming patterns in flows
        collect_vars = re.findall(
            r'(?:collect|get|ask for|request)\s+(?:the\s+)?[`"]?([a-zA-Z_]\w+)[`"]?',
            content,
            re.IGNORECASE
        )

        all_vars = set(mustache_vars + dollar_vars + collect_vars)

        for name in all_vars:
            if name not in existing_names and not self._is_keyword(name):
                var = Variable(
                    name=name,
                    type=VariableType.STRING,
                    description="Referenced in flow",
                )
                variables.append(var)

        return variables

    def _is_keyword(self, name: str) -> bool:
        """Check if name is a common keyword rather than a variable."""
        keywords = {
            'user', 'agent', 'bot', 'system', 'api', 'response', 'request',
            'if', 'then', 'else', 'and', 'or', 'not', 'true', 'false',
            'flow', 'step', 'action', 'condition', 'end', 'start',
            'name', 'type', 'description', 'value', 'data',
        }
        return name.lower() in keywords

    def _find_column_index(self, header: List[str], candidates: List[str]) -> int:
        """Find column index matching any of the candidate names."""
        for i, cell in enumerate(header):
            cell_lower = cell.lower().strip()
            for candidate in candidates:
                if candidate in cell_lower:
                    return i
        return -1

    def _get_cell(self, row: List[str], index: int, default: Any) -> Any:
        """Get cell value at index or return default."""
        if index >= 0 and index < len(row):
            value = row[index].strip()
            return value if value else default
        return default

    def _parse_source(self, source_str: str) -> VariableSource:
        """Parse variable source from string."""
        source_lower = source_str.lower().strip()
        if 'collect' in source_lower or 'input' in source_lower:
            return VariableSource.COLLECT
        elif 'tool' in source_lower or 'api' in source_lower:
            return VariableSource.TOOL
        else:
            return VariableSource.USER

    def _parse_bool(self, value: str) -> bool:
        """Parse boolean value from string."""
        return value.lower().strip() in ('true', 'yes', '1', 'required', 'mandatory')

    def _parse_default(self, value: Optional[str]) -> Any:
        """Parse default value, handling special cases."""
        if value is None or value in ('', 'null', 'none', 'None', '-'):
            return None

        # Try to parse as number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            pass

        # Try to parse as boolean
        if value.lower() in ('true', 'yes'):
            return True
        if value.lower() in ('false', 'no'):
            return False

        return value

    def _llm_extract_variables(
        self,
        content: str,
        llm_client: BaseLLMClient
    ) -> List[Variable]:
        """Use LLM to extract variables from content."""
        prompt = """Extract variables from this PRD document.

Return ONLY a JSON array of variables with this structure:
[
  {
    "name": "variable_name",
    "type": "string or number or boolean",
    "description": "What this variable stores",
    "source": "user or collect or tool",
    "required": true
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
                    variables = []
                    for item in data:
                        var = Variable(
                            name=item.get('name', ''),
                            type=VariableType.from_string(item.get('type', 'string')),
                            description=item.get('description', ''),
                            source=self._parse_source(item.get('source', 'user')),
                            required=item.get('required', False),
                        )
                        if var.name:
                            variables.append(var)
                    return variables

        except Exception as e:
            logger.warning(f"LLM variable extraction failed: {e}")

        return []
