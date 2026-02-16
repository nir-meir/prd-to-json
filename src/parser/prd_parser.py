"""
PRD Parser - Main orchestrator for parsing PRD documents.

Coordinates multiple extractors to convert raw PRD text into
a structured ParsedPRD object ready for JSON generation.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import json

from .models import (
    ParsedPRD,
    AgentMetadata,
    Feature,
    Variable,
    APIEndpoint,
    BusinessRule,
    Channel,
    Complexity,
)
from .extractors.base import BaseExtractor
from .extractors.metadata_extractor import MetadataExtractor
from .extractors.feature_extractor import FeatureExtractor
from .extractors.variable_extractor import VariableExtractor
from .extractors.api_extractor import APIExtractor
from .extractors.rule_extractor import RuleExtractor

from ..core.config import AppConfig
from ..llm import BaseLLMClient, BedrockClient, create_client
from ..llm.base import LLMConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParseResult:
    """Result of parsing operation."""
    success: bool
    parsed_prd: Optional[ParsedPRD] = None
    error_message: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PRDParser:
    """
    Main PRD parser orchestrating multiple extractors.

    Parses raw PRD text through several stages:
    1. Metadata extraction (agent name, language, channel)
    2. Feature extraction (flows, user stories)
    3. Variable extraction
    4. API/endpoint extraction
    5. Business rule extraction
    6. Cross-reference validation

    Can use LLM-assisted parsing for complex PRDs or
    rule-based parsing for structured documents.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        """
        Initialize the parser.

        Args:
            config: Application configuration
            llm_client: LLM client for assisted parsing (auto-created if None)
        """
        self.config = config or AppConfig()
        self._llm_client = llm_client
        self._extractors: Dict[str, BaseExtractor] = {}

        # Initialize extractors
        self._init_extractors()

    def _init_extractors(self) -> None:
        """Initialize all extractors."""
        self._extractors = {
            'metadata': MetadataExtractor(),
            'features': FeatureExtractor(),
            'variables': VariableExtractor(),
            'apis': APIExtractor(),
            'rules': RuleExtractor(),
        }

    @property
    def llm_client(self) -> BaseLLMClient:
        """Lazy-load LLM client."""
        if self._llm_client is None:
            llm_config = LLMConfig(
                model_id=self.config.generation.llm.model,
                temperature=0.1,  # Low temperature for parsing accuracy
                max_tokens=self.config.generation.llm.max_tokens,
                timeout=self.config.generation.llm.timeout,
            )
            self._llm_client = BedrockClient(config=llm_config)
        return self._llm_client

    def parse(self, prd_content: str, source_file: Optional[str] = None) -> ParsedPRD:
        """
        Parse PRD content into structured ParsedPRD object.

        Args:
            prd_content: Raw PRD text content
            source_file: Optional source file path for reference

        Returns:
            ParsedPRD object with extracted components

        Raises:
            ValueError: If PRD content is empty or invalid
        """
        if not prd_content or not prd_content.strip():
            raise ValueError("PRD content is empty")

        logger.info("Starting PRD parsing...")

        warnings = []
        errors = []

        # Stage 1: Extract metadata
        logger.debug("Extracting metadata...")
        metadata = self._extract_metadata(prd_content)
        if not metadata.name:
            warnings.append("Could not extract agent name, using default")
            metadata.name = "Unnamed Agent"

        # Stage 2: Extract features
        logger.debug("Extracting features...")
        features = self._extract_features(prd_content)
        if not features:
            warnings.append("No features found in PRD")

        # Stage 3: Extract variables
        logger.debug("Extracting variables...")
        variables = self._extract_variables(prd_content, features)

        # Stage 4: Extract APIs
        logger.debug("Extracting API definitions...")
        apis = self._extract_apis(prd_content, features)

        # Stage 5: Extract business rules
        logger.debug("Extracting business rules...")
        rules = self._extract_rules(prd_content)

        # Stage 6: Cross-reference and validate
        logger.debug("Cross-referencing...")
        self._cross_reference(features, variables, apis, rules)

        # Build ParsedPRD
        parsed = ParsedPRD(
            raw_content=prd_content,
            source_file=source_file,
            metadata=metadata,
            features=features,
            variables=variables,
            apis=apis,
            business_rules=rules,
            parse_warnings=warnings,
            parse_errors=errors,
        )

        logger.info(f"Parsing complete: {parsed.summary()}")

        return parsed

    def parse_file(self, file_path: str | Path) -> ParsedPRD:
        """
        Parse a PRD file.

        Args:
            file_path: Path to PRD file

        Returns:
            ParsedPRD object
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PRD file not found: {file_path}")

        content = path.read_text(encoding='utf-8')
        return self.parse(content, source_file=str(path))

    def _extract_metadata(self, content: str) -> AgentMetadata:
        """Extract agent metadata from PRD content."""
        extractor = self._extractors['metadata']
        return extractor.extract(content, llm_client=self.llm_client)

    def _extract_features(self, content: str) -> List[Feature]:
        """Extract features from PRD content."""
        extractor = self._extractors['features']
        return extractor.extract(content, llm_client=self.llm_client)

    def _extract_variables(
        self,
        content: str,
        features: List[Feature]
    ) -> List[Variable]:
        """Extract variables from PRD content."""
        extractor = self._extractors['variables']
        return extractor.extract(content, features=features, llm_client=self.llm_client)

    def _extract_apis(
        self,
        content: str,
        features: List[Feature]
    ) -> List[APIEndpoint]:
        """Extract API definitions from PRD content."""
        extractor = self._extractors['apis']
        return extractor.extract(content, features=features, llm_client=self.llm_client)

    def _extract_rules(self, content: str) -> List[BusinessRule]:
        """Extract business rules from PRD content."""
        extractor = self._extractors['rules']
        return extractor.extract(content, llm_client=self.llm_client)

    def _cross_reference(
        self,
        features: List[Feature],
        variables: List[Variable],
        apis: List[APIEndpoint],
        rules: List[BusinessRule],
    ) -> None:
        """
        Cross-reference extracted components.

        Updates features with their referenced variables and APIs.
        """
        variable_names = {v.name for v in variables}
        api_names = {a.name for a in apis} | {a.function_name for a in apis}
        rule_ids = {r.id for r in rules}

        for feature in features:
            # Filter to only existing variables
            feature.variables_used = [
                v for v in feature.variables_used
                if v in variable_names
            ]

            # Filter to only existing APIs
            feature.apis_used = [
                a for a in feature.apis_used
                if a in api_names
            ]

            # Filter to only existing rules
            feature.rules_applied = [
                r for r in feature.rules_applied
                if r in rule_ids
            ]


class QuickParser:
    """
    Simplified parser for quick PRD analysis.

    Uses LLM to parse the entire PRD in a single pass.
    Best for simple to medium complexity PRDs.
    """

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        prompt_path: Optional[Path] = None,
    ):
        """
        Initialize quick parser.

        Args:
            llm_client: LLM client (auto-created if None)
            prompt_path: Path to parser prompt
        """
        self._llm_client = llm_client
        self.prompt_path = prompt_path or Path(__file__).parent.parent.parent / "prompts" / "system" / "parser_prompt.md"

    @property
    def llm_client(self) -> BaseLLMClient:
        """Lazy-load LLM client."""
        if self._llm_client is None:
            self._llm_client = BedrockClient()
        return self._llm_client

    def parse(self, prd_content: str) -> ParsedPRD:
        """
        Parse PRD in a single LLM pass.

        Args:
            prd_content: Raw PRD content

        Returns:
            ParsedPRD object
        """
        # Load prompt
        if self.prompt_path.exists():
            system_prompt = self.prompt_path.read_text()
        else:
            system_prompt = self._get_default_prompt()

        # Call LLM
        response = self.llm_client.generate(
            prompt=prd_content,
            system_prompt=system_prompt,
        )

        if not response.success:
            raise RuntimeError(f"LLM parsing failed: {response.error_message}")

        # Parse JSON response
        try:
            data = json.loads(response.content)
            return self._build_parsed_prd(data, prd_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}")

    def _build_parsed_prd(self, data: Dict[str, Any], raw_content: str) -> ParsedPRD:
        """Build ParsedPRD from LLM response data."""
        # Extract metadata
        meta_data = data.get('metadata', {})
        metadata = AgentMetadata(
            name=meta_data.get('name', 'Unnamed Agent'),
            description=meta_data.get('description', ''),
            language=meta_data.get('language', 'en-US'),
            channel=Channel.from_string(meta_data.get('channel', 'both')),
        )

        # Extract features
        features = []
        for f_data in data.get('features', []):
            feature = Feature(
                id=f_data.get('id', ''),
                name=f_data.get('name', ''),
                description=f_data.get('description', ''),
                channel=Channel.from_string(f_data.get('channel', 'both')),
                variables_used=f_data.get('variables_used', []),
                apis_used=f_data.get('apis_used', []),
            )
            features.append(feature)

        # Extract variables
        variables = []
        for v_data in data.get('variables', []):
            variable = Variable(
                name=v_data.get('name', ''),
                type=v_data.get('type', 'string'),
                description=v_data.get('description', ''),
                source=v_data.get('source', 'user'),
                required=v_data.get('required', False),
            )
            variables.append(variable)

        # Extract APIs
        apis = []
        for a_data in data.get('apis', []):
            api = APIEndpoint(
                name=a_data.get('name', ''),
                description=a_data.get('description', ''),
                function_name=a_data.get('function_name', a_data.get('name', '')),
                method=a_data.get('method', 'POST'),
                endpoint=a_data.get('endpoint', ''),
            )
            apis.append(api)

        return ParsedPRD(
            raw_content=raw_content,
            metadata=metadata,
            features=features,
            variables=variables,
            apis=apis,
        )

    def _get_default_prompt(self) -> str:
        """Get default parser prompt."""
        return """You are a PRD (Product Requirements Document) parser.

Analyze the provided PRD and extract structured information as JSON.

Output format:
{
  "metadata": {
    "name": "Agent name",
    "description": "Agent description",
    "language": "en-US or he-IL",
    "channel": "voice or text or both"
  },
  "features": [
    {
      "id": "F-01",
      "name": "Feature name",
      "description": "What this feature does",
      "channel": "voice or text or both",
      "variables_used": ["var1", "var2"],
      "apis_used": ["api1", "api2"]
    }
  ],
  "variables": [
    {
      "name": "variable_name",
      "type": "string or number or boolean",
      "description": "What this variable stores",
      "source": "user or collect or tool",
      "required": true
    }
  ],
  "apis": [
    {
      "name": "API Name",
      "function_name": "api_function_name",
      "description": "What this API does",
      "method": "GET or POST",
      "endpoint": "/api/endpoint"
    }
  ]
}

Output ONLY valid JSON, no explanations."""
