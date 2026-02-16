"""
Parser module - Extract structured data from PRD documents.
"""

from .models import (
    Channel,
    Complexity,
    VariableType,
    VariableSource,
    FlowStepType,
    HTTPMethod,
    ValidationRule,
    Variable,
    APIParameter,
    APIExtraction,
    APIEndpoint,
    BusinessRule,
    FlowStep,
    UserStory,
    Feature,
    AgentMetadata,
    ParsedPRD,
)
from .prd_parser import PRDParser, QuickParser, ParseResult
from .extractors import (
    BaseExtractor,
    MetadataExtractor,
    FeatureExtractor,
    VariableExtractor,
    APIExtractor,
    RuleExtractor,
)

__all__ = [
    # Models
    'Channel',
    'Complexity',
    'VariableType',
    'VariableSource',
    'FlowStepType',
    'HTTPMethod',
    'ValidationRule',
    'Variable',
    'APIParameter',
    'APIExtraction',
    'APIEndpoint',
    'BusinessRule',
    'FlowStep',
    'UserStory',
    'Feature',
    'AgentMetadata',
    'ParsedPRD',
    # Parsers
    'PRDParser',
    'QuickParser',
    'ParseResult',
    # Extractors
    'BaseExtractor',
    'MetadataExtractor',
    'FeatureExtractor',
    'VariableExtractor',
    'APIExtractor',
    'RuleExtractor',
]
