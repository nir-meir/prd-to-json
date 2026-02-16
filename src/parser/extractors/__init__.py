"""
PRD Extractors - Component extractors for parsing PRD documents.

Each extractor handles a specific component type:
- MetadataExtractor: Agent metadata (name, language, channel)
- FeatureExtractor: Features and user stories
- VariableExtractor: Variable definitions
- APIExtractor: API endpoint definitions
- RuleExtractor: Business rules
"""

from .base import BaseExtractor
from .metadata_extractor import MetadataExtractor
from .feature_extractor import FeatureExtractor
from .variable_extractor import VariableExtractor
from .api_extractor import APIExtractor
from .rule_extractor import RuleExtractor

__all__ = [
    'BaseExtractor',
    'MetadataExtractor',
    'FeatureExtractor',
    'VariableExtractor',
    'APIExtractor',
    'RuleExtractor',
]
