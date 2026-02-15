# PRD to JSON Generator

CLI tool for converting PRD (Product Requirements Document) files to INSAIT platform JSON.

## Setup

```bash
pip install -r requirements.txt
```

Configure your `.env` file with AWS credentials for Bedrock.

## Usage

```bash
# Generate JSON from PRD
python main.py generate <prd_file> --output <output.json>

# Validate existing JSON
python main.py validate <json_file>

# Verbose mode
python main.py generate <prd_file> --output <output.json> --verbose
```

## Example

```bash
python main.py generate examples/test_prd.txt --output agent.json
```

## PRD Format

Your PRD should include:
- Purpose/Objective
- Agent persona
- Capabilities
- Conversation flow (step-by-step)
- Error handling
- Constraints

See `examples/` for sample PRD files.
