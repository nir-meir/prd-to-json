# PRD to JSON Generator

Enterprise-grade CLI tool for converting PRD (Product Requirements Document) files to INSAIT platform JSON format.

## Features

- **Multi-strategy generation**: Simple, Chunked, and Hybrid strategies based on PRD complexity
- **Intelligent parsing**: Extracts features, variables, APIs, and business rules from PRD documents
- **Auto-validation**: Validates generated JSON against INSAIT schema
- **Auto-fix**: Automatically fixes common validation issues
- **Multi-channel support**: Voice, Text, or Both channels
- **Multi-language**: Hebrew and English support with auto-detection

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials for Bedrock (optional - can use mock LLM for testing)
cp .env.example .env
# Edit .env with your AWS credentials
```

## Usage

### Command Line

```bash
# Basic usage - generates JSON to stdout
python -m src.cli input.md

# Save to file
python -m src.cli input.md -o output.json

# Use mock LLM for testing (no AWS credentials needed)
python -m src.cli input.md -o output.json --mock-llm

# Verbose mode
python -m src.cli input.md -o output.json --verbose

# Dry run - parse only, don't generate
python -m src.cli input.md --dry-run

# Strict mode - treat warnings as errors
python -m src.cli input.md -o output.json --strict

# Disable auto-fix
python -m src.cli input.md -o output.json --no-fix
```

### Programmatic Usage

```python
from src.cli import run_pipeline

# Run the full pipeline
result = run_pipeline(
    input_path="examples/test_prd.txt",
    output_path="output.json",
    use_mock_llm=True,  # Set False to use Bedrock
    auto_fix=True,
)

print(f"Generated agent: {result['name']}")
print(f"Nodes: {len(result['flow']['nodes'])}")
```

## Example

```bash
# Generate from example PRD
python -m src.cli examples/test_prd.txt -o agent.json --mock-llm --verbose
```

## PRD Format

Your PRD should include:

- **Overview/Description**: Agent name, purpose, language, channel
- **Features**: Numbered sections (e.g., "Feature F-01: Authentication")
- **Flow Steps**: Numbered steps describing the conversation flow
- **Variables**: Table or list of variables used
- **APIs**: Table or sections describing API endpoints
- **Business Rules**: Conditions and actions (optional)

### Example PRD Structure

```markdown
# Customer Service Bot PRD

## Overview
A customer service bot for handling inquiries.

Language: Hebrew
Channel: Voice

## Feature F-01: Authentication

### Description
Authenticate users with phone number.

### Flow (Audio)
1. Greet the user
2. Ask for phone number
3. Validate phone format
4. Look up customer

### Variables Used
- phone_number
- customer_id

## Variables

| Name | Type | Description |
|------|------|-------------|
| phone_number | string | Customer phone |
| customer_id | string | Customer ID |

## APIs

### lookup_customer
Method: POST
Endpoint: /api/crm/lookup
```

See `examples/` for more sample PRD files.

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/test_generator.py -v
```

## Project Structure

```
prdToJson/
├── src/
│   ├── cli.py              # Main CLI entry point
│   ├── parser/             # PRD parsing and extraction
│   │   ├── prd_parser.py   # Main parser
│   │   ├── extractors/     # Feature, variable, API extractors
│   │   └── models/         # Data models (ParsedPRD, Feature, etc.)
│   ├── generator/          # JSON generation
│   │   ├── simple_generator.py
│   │   ├── chunked_generator.py
│   │   ├── hybrid_generator.py
│   │   └── node_factory.py
│   ├── validator/          # Validation and auto-fix
│   │   ├── json_validator.py
│   │   └── auto_fixer.py
│   ├── llm/                # LLM clients (Bedrock, Mock)
│   ├── core/               # Config and context
│   └── utils/              # Utilities (ID generation, logging)
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── examples/               # Example PRD files
├── config/                 # Configuration files
└── prompts/                # LLM prompts
```

## License

Proprietary - INSAIT Platform
