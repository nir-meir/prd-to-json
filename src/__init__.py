"""
PRD to JSON Generator - Convert PRD documents to INSAIT JSON format.

Main modules:
- parser: Parse PRD documents into structured format
- generator: Generate INSAIT JSON from parsed PRDs
- validator: Validate and auto-fix generated JSON
- llm: LLM client abstractions
- cli: Command-line interface
"""

from .cli import run_pipeline

__version__ = "1.0.0"

__all__ = [
    'run_pipeline',
    '__version__',
]
