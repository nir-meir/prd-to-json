"""
API Extractor - Extract API endpoint definitions from PRD documents.

Extracts:
- API/endpoint names and descriptions
- HTTP methods and URLs
- Request parameters
- Response extractions
- Error handling
"""

import re
import json
from typing import Optional, List, Dict, Any

from .base import BaseExtractor
from ..models import (
    APIEndpoint,
    APIParameter,
    APIExtraction,
    HTTPMethod,
    Feature,
)
from ...llm.base import BaseLLMClient
from ...utils.logger import get_logger

logger = get_logger(__name__)


class APIExtractor(BaseExtractor):
    """
    Extractor for API endpoints.

    Handles various formats:
    - OpenAPI/Swagger snippets
    - Table-based definitions
    - Narrative API descriptions
    """

    @property
    def component_name(self) -> str:
        return "apis"

    def extract(
        self,
        content: str,
        features: Optional[List[Feature]] = None,
        llm_client: Optional[BaseLLMClient] = None,
        **kwargs
    ) -> List[APIEndpoint]:
        """
        Extract API endpoints from PRD content.

        Args:
            content: Raw PRD text
            features: Optional list of extracted features (for context)
            llm_client: Optional LLM client for assisted extraction

        Returns:
            List of APIEndpoint objects
        """
        logger.debug("Extracting APIs...")

        apis = []
        seen_names = set()

        # Extract from API sections
        section_apis = self._extract_from_section(content)
        for api in section_apis:
            if api.name not in seen_names:
                apis.append(api)
                seen_names.add(api.name)

        # Extract from tables
        table_apis = self._extract_from_table(content)
        for api in table_apis:
            if api.name not in seen_names:
                apis.append(api)
                seen_names.add(api.name)

        # Extract APIs referenced in features but not defined
        if features:
            for feature in features:
                for api_name in feature.apis_used:
                    if api_name not in seen_names:
                        # Try to find definition
                        api = self._find_api_definition(api_name, content)
                        if api:
                            apis.append(api)
                            seen_names.add(api.name)

        # Use LLM for complex or unstructured content
        if len(apis) < 2 and llm_client:
            logger.debug("Using LLM for API extraction")
            llm_apis = self._llm_extract_apis(content, llm_client)
            for api in llm_apis:
                if api.name not in seen_names:
                    apis.append(api)
                    seen_names.add(api.name)

        logger.info(f"Extracted {len(apis)} API endpoints")
        return apis

    def _extract_from_section(self, content: str) -> List[APIEndpoint]:
        """Extract APIs from dedicated API sections."""
        apis = []

        # Find API section
        api_section = self._find_section(
            content,
            ['APIs', 'API Endpoints', 'Integrations', 'External APIs', 'Tools'],
            ['Flow', 'Features', 'User Stories', 'Business Rules']
        )

        if not api_section:
            return apis

        # Pattern 1: ### API_NAME format
        api_blocks = re.split(r'\n###?\s+', api_section)

        for block in api_blocks[1:]:  # Skip content before first header
            lines = block.split('\n')
            if not lines:
                continue

            # First line is the API name
            api_name = lines[0].strip()
            api_name = re.sub(r'\*+', '', api_name)

            if not api_name or api_name.lower() in ('apis', 'endpoints', 'integrations'):
                continue

            # Parse rest of block for details
            block_content = '\n'.join(lines[1:])

            # Extract method
            method = HTTPMethod.POST
            method_match = re.search(r'method\s*:\s*(GET|POST|PUT|PATCH|DELETE)', block_content, re.IGNORECASE)
            if method_match:
                method = HTTPMethod(method_match.group(1).upper())

            # Extract endpoint
            endpoint = ""
            endpoint_match = re.search(r'(?:endpoint|url|path)\s*:\s*([^\n]+)', block_content, re.IGNORECASE)
            if endpoint_match:
                endpoint = endpoint_match.group(1).strip()

            # Extract function name
            function_name = self._to_function_name(api_name)
            func_match = re.search(r'(?:function|tool_id)\s*:\s*([^\n]+)', block_content, re.IGNORECASE)
            if func_match:
                function_name = func_match.group(1).strip()

            # Extract description
            description = self._extract_key_value(block_content, 'Description') or ""
            if not description:
                # Use first paragraph as description
                paragraphs = block_content.split('\n\n')
                for para in paragraphs:
                    para = self._clean_text(para)
                    if len(para) > 20 and not para.startswith(('method', 'endpoint', 'url')):
                        description = para[:300]
                        break

            # Extract parameters
            parameters = self._extract_parameters(block_content)

            # Extract response extractions
            extractions = self._extract_response_extractions(block_content)

            api = APIEndpoint(
                name=api_name,
                description=description,
                function_name=function_name,
                method=method,
                endpoint=endpoint,
                parameters=parameters,
                extractions=extractions,
            )
            apis.append(api)

        return apis

    def _extract_from_table(self, content: str) -> List[APIEndpoint]:
        """Extract APIs from markdown tables."""
        apis = []

        # Find API tables
        api_section = self._find_section(
            content,
            ['APIs', 'API Endpoints', 'Integrations', 'Tools'],
            ['Flow', 'Features', 'Variables']
        )

        if not api_section:
            api_section = content

        rows = self._extract_table_rows(api_section)

        if not rows:
            return apis

        # Detect columns
        header = rows[0] if rows else []
        name_col = self._find_column_index(header, ['name', 'api', 'endpoint', 'tool'])
        desc_col = self._find_column_index(header, ['description', 'purpose', 'desc'])
        method_col = self._find_column_index(header, ['method', 'http method', 'type'])
        url_col = self._find_column_index(header, ['url', 'endpoint', 'path'])
        func_col = self._find_column_index(header, ['function', 'function_name', 'tool_id'])

        data_rows = rows[1:] if len(rows) > 1 else []

        for row in data_rows:
            name = self._get_cell(row, name_col, '')
            if not name or name.startswith('-'):
                continue

            name = re.sub(r'[`*]', '', name).strip()

            api = APIEndpoint(
                name=name,
                description=self._get_cell(row, desc_col, ''),
                function_name=self._get_cell(row, func_col, '') or self._to_function_name(name),
                method=self._parse_method(self._get_cell(row, method_col, 'POST')),
                endpoint=self._get_cell(row, url_col, ''),
            )
            apis.append(api)

        return apis

    def _find_api_definition(self, name: str, content: str) -> Optional[APIEndpoint]:
        """Find API definition by name in content."""
        # Try to find the API mentioned in context
        pattern = re.compile(
            rf'{re.escape(name)}\s*'
            r'[-:]\s*(.+?)(?:\n\n|\n#|$)',
            re.IGNORECASE | re.DOTALL
        )

        match = pattern.search(content)
        if match:
            description = self._clean_text(match.group(1))[:300]
            return APIEndpoint(
                name=name,
                description=description,
                function_name=self._to_function_name(name),
            )

        # Return basic API if no definition found
        return APIEndpoint(
            name=name,
            description="",
            function_name=self._to_function_name(name),
        )

    def _extract_parameters(self, content: str) -> List[APIParameter]:
        """Extract API parameters from content."""
        parameters = []

        # Find parameters section
        param_match = re.search(
            r'(?:parameters?|inputs?|request)\s*[:\n](.+?)(?:\n\n|response|output|$)',
            content,
            re.IGNORECASE | re.DOTALL
        )

        if not param_match:
            return parameters

        param_section = param_match.group(1)

        # Try table format first
        rows = self._extract_table_rows(param_section)
        if rows:
            for row in rows[1:]:  # Skip header
                if len(row) >= 1:
                    name = row[0].strip()
                    if not name or name.startswith('-'):
                        continue
                    name = re.sub(r'[`*]', '', name)

                    param = APIParameter(
                        name=name,
                        type=row[1].strip() if len(row) > 1 else 'string',
                        description=row[2].strip() if len(row) > 2 else '',
                        required='required' in (row[3].lower() if len(row) > 3 else ''),
                    )
                    parameters.append(param)
        else:
            # Try list format
            items = self._extract_list_items(param_section)
            for item in items:
                # Pattern: param_name (type): description
                match = re.match(
                    r'[`*]?(\w+)[`*]?\s*(?:\(([^)]+)\))?\s*[-:]\s*(.+)',
                    item
                )
                if match:
                    param = APIParameter(
                        name=match.group(1),
                        type=match.group(2) or 'string',
                        description=match.group(3).strip(),
                    )
                    parameters.append(param)

        return parameters

    def _extract_response_extractions(self, content: str) -> List[APIExtraction]:
        """Extract response extraction rules from content."""
        extractions = []

        # Find response/extraction section
        resp_match = re.search(
            r'(?:response|output|extract(?:ion)?s?)\s*[:\n](.+?)(?:\n\n|error|$)',
            content,
            re.IGNORECASE | re.DOTALL
        )

        if not resp_match:
            return extractions

        resp_section = resp_match.group(1)

        # Pattern: variable_name <- response.path or variable_name from response.path
        patterns = [
            r'(\w+)\s*(?:<-|=|from)\s*(?:response\.)?([a-zA-Z0-9_.]+)',
            r'(?:extract|store)\s+(\w+)\s+from\s+([a-zA-Z0-9_.]+)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, resp_section, re.IGNORECASE):
                extraction = APIExtraction(
                    variable_name=match.group(1),
                    response_path=match.group(2),
                )
                extractions.append(extraction)

        return extractions

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

    def _parse_method(self, method_str: str) -> HTTPMethod:
        """Parse HTTP method from string."""
        method_str = method_str.upper().strip()
        try:
            return HTTPMethod(method_str)
        except ValueError:
            return HTTPMethod.POST

    def _to_function_name(self, name: str) -> str:
        """Convert API name to function name format."""
        # Remove special characters
        name = re.sub(r'[^\w\s]', '', name)
        # Convert to snake_case
        name = re.sub(r'\s+', '_', name.strip().lower())
        # Remove consecutive underscores
        name = re.sub(r'_+', '_', name)
        return name

    def _llm_extract_apis(
        self,
        content: str,
        llm_client: BaseLLMClient
    ) -> List[APIEndpoint]:
        """Use LLM to extract APIs from content."""
        prompt = """Extract API endpoints from this PRD document.

Return ONLY a JSON array of APIs with this structure:
[
  {
    "name": "API Name",
    "description": "What this API does",
    "function_name": "api_function_name",
    "method": "GET or POST",
    "endpoint": "/api/endpoint",
    "parameters": [
      {"name": "param1", "type": "string", "required": true}
    ]
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
                    apis = []
                    for item in data:
                        params = [
                            APIParameter(
                                name=p.get('name', ''),
                                type=p.get('type', 'string'),
                                description=p.get('description', ''),
                                required=p.get('required', True),
                            )
                            for p in item.get('parameters', [])
                        ]

                        api = APIEndpoint(
                            name=item.get('name', ''),
                            description=item.get('description', ''),
                            function_name=item.get('function_name', ''),
                            method=self._parse_method(item.get('method', 'POST')),
                            endpoint=item.get('endpoint', ''),
                            parameters=params,
                        )
                        if api.name:
                            apis.append(api)
                    return apis

        except Exception as e:
            logger.warning(f"LLM API extraction failed: {e}")

        return []
