# Example PRD Files

This directory contains example PRD (Product Requirements Document) files for testing the PRD to JSON generator.

## Files

### test_prd.txt

A comprehensive example of a customer support agent PRD. This example demonstrates:

- **Agent persona definition**: Professional and empathetic support agent
- **Multiple conversation flows**: Order tracking, returns, product questions
- **Branching logic**: Different paths based on user intent
- **Error handling**: Invalid inputs, API failures
- **Escalation paths**: Human handoff for complex issues

## Usage

Generate JSON from the test PRD:

```bash
# Basic generation
python3 main.py generate examples/test_prd.txt --output customer_support_agent.json

# With verbose output
python3 main.py generate examples/test_prd.txt --output customer_support_agent.json --verbose

# Validate only (no generation)
python3 main.py generate examples/test_prd.txt --validate-only
```

## Writing Your Own PRD

When creating a PRD for the generator, include:

1. **Purpose/Objective**: What is the agent's main goal?
2. **Persona**: How should the agent communicate?
3. **Capabilities**: What can the agent do?
4. **Conversation Flow**: Step-by-step description of the interaction
5. **Error Handling**: How to handle edge cases
6. **Constraints**: What the agent should NOT do

### Tips

- Use clear, descriptive language
- Break down complex flows into numbered steps
- Specify input validation requirements
- Define all possible branches and outcomes
- Include escalation paths for edge cases

## Expected Output

The generator will produce JSON with:

- `metadata`: Agent name, version, description
- `agent`: Name, description, persona, capabilities, constraints
- `flow_definition`: Nodes and edges defining the conversation flow

See the main README for more details on the JSON schema.
