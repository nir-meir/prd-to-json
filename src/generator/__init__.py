"""
Generator module - Convert parsed PRDs to INSAIT JSON format.

Provides multiple generation strategies:
- SimpleGenerator: For simple PRDs (1-3 features)
- ChunkedGenerator: For complex PRDs (generates per-feature)
- HybridGenerator: Adaptive strategy selection

Main entry point is the `create_generator` function which auto-selects strategy.
"""

from .base_generator import (
    BaseGenerator,
    GenerationStrategy,
    GenerationResult,
    select_strategy,
)
from .node_factory import NodeFactory, NodeType, NodePosition
from .simple_generator import SimpleGenerator
from .chunked_generator import ChunkedGenerator
from .hybrid_generator import HybridGenerator, create_generator

__all__ = [
    # Base classes
    'BaseGenerator',
    'GenerationStrategy',
    'GenerationResult',
    'select_strategy',
    # Generators
    'SimpleGenerator',
    'ChunkedGenerator',
    'HybridGenerator',
    'create_generator',
    # Node factory
    'NodeFactory',
    'NodeType',
    'NodePosition',
]
