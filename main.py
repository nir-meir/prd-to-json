#!/usr/bin/env python3
"""
PRD to JSON Generator - CLI tool for converting PRD files to INSAIT platform JSON.

Usage:
    python main.py generate <prd_file> [--output <output_file>] [--validate-only] [--verbose]
    python main.py validate <json_file> [--verbose]

Examples:
    python main.py generate examples/test_prd.txt --output agent.json
    python main.py generate examples/test_prd.txt --validate-only
    python main.py generate examples/test_prd.txt --verbose
    python main.py validate agent.json
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

# ANSI color codes
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def color(text: str, color_code: str) -> str:
    """Apply color to text."""
    return f"{color_code}{text}{Colors.RESET}"


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(color(f"{'=' * 60}", Colors.CYAN))
    print(color(f"  {title}", Colors.BOLD + Colors.CYAN))
    print(color(f"{'=' * 60}", Colors.CYAN))


def print_success(message: str) -> None:
    """Print a success message."""
    print(color(f"[SUCCESS] {message}", Colors.GREEN))


def print_error(message: str) -> None:
    """Print an error message."""
    print(color(f"[ERROR] {message}", Colors.RED), file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(color(f"[WARNING] {message}", Colors.YELLOW))


def print_info(message: str) -> None:
    """Print an info message."""
    print(color(f"[INFO] {message}", Colors.BLUE))


def print_step(message: str) -> None:
    """Print a step/progress message."""
    print(color(f"  -> {message}", Colors.DIM))


def print_validation_report(report, verbose: bool = False) -> None:
    """
    Print a formatted validation report.

    Args:
        report: ValidationReport from json_validator
        verbose: Show all details
    """
    from src.json_validator import ValidationCategory

    if report.is_valid and not report.warnings:
        print_success("JSON validation passed")
        return

    # Print errors by category
    for category in ValidationCategory:
        issues = report.get_by_category(category)
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        if errors:
            print()
            print(color(f"{category.value}:", Colors.RED + Colors.BOLD))
            for issue in errors:
                if issue.path:
                    print(f"  {color('-', Colors.RED)} {color(issue.path, Colors.DIM)}")
                    print(f"    {issue.message}")
                else:
                    print(f"  {color('-', Colors.RED)} {issue.message}")

        if warnings and verbose:
            if not errors:
                print()
                print(color(f"{category.value}:", Colors.YELLOW + Colors.BOLD))
            for issue in warnings:
                if issue.path:
                    print(f"  {color('~', Colors.YELLOW)} {color(issue.path, Colors.DIM)}")
                    print(f"    {issue.message}")
                else:
                    print(f"  {color('~', Colors.YELLOW)} {issue.message}")

    # Summary
    error_count = len(report.errors)
    warning_count = len(report.warnings)

    print()
    if error_count > 0:
        print(color(
            f"Found {error_count} error(s) and {warning_count} warning(s)",
            Colors.RED
        ))
    elif warning_count > 0:
        print(color(
            f"Validation passed with {warning_count} warning(s)",
            Colors.YELLOW
        ))


def validate_json_command(
    json_file: str,
    verbose: bool = False
) -> int:
    """
    Validate an existing JSON file.

    Args:
        json_file: Path to JSON file
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for errors)
    """
    from src.json_validator import validate_json_file

    print_header("INSAIT JSON Validator")

    print()
    print(color("Validating JSON file...", Colors.BOLD))
    print_step(f"File: {json_file}")

    report = validate_json_file(json_file)

    print()
    print_validation_report(report, verbose)

    # Print stats
    if report.stats and verbose:
        print()
        print(color("Statistics:", Colors.BOLD))
        if 'agent_name' in report.stats:
            print_step(f"Agent: {report.stats['agent_name']}")
        if 'node_count' in report.stats:
            print_step(f"Nodes: {report.stats['node_count']}")
        if 'exit_count' in report.stats:
            print_step(f"Exits: {report.stats['exit_count']}")
        if 'node_types' in report.stats:
            print_step(f"Node types: {report.stats['node_types']}")

    print()
    if report.is_valid:
        print(color("=" * 60, Colors.GREEN))
        print(color("  Validation Passed!", Colors.BOLD + Colors.GREEN))
        print(color("=" * 60, Colors.GREEN))
        return 0
    else:
        print(color("=" * 60, Colors.RED))
        print(color("  Validation Failed!", Colors.BOLD + Colors.RED))
        print(color("=" * 60, Colors.RED))
        return 1


def generate_command(
    prd_file: str,
    output_file: str = "output.json",
    validate_only: bool = False,
    verbose: bool = False,
    force_save: bool = False
) -> int:
    """
    Generate JSON from PRD file.

    Args:
        prd_file: Path to PRD file
        output_file: Path to output JSON file
        validate_only: Only validate PRD, don't generate
        verbose: Show detailed output
        force_save: Save file even if validation fails

    Returns:
        Exit code (0 for success)
    """
    from src.validator import validate_prd_file
    from src.json_validator import validate_insait_json
    from src.generator import generate_json, GenerationConfig
    from src.utils import extract_json_from_response, format_json, read_file, write_file

    print_header("PRD to JSON Generator")

    # Step 1: Validate PRD
    print()
    print(color("Step 1: Validating PRD", Colors.BOLD))
    print_step(f"Reading: {prd_file}")

    prd_result = validate_prd_file(prd_file)

    if prd_result.errors:
        print_error("PRD validation failed:")
        for error in prd_result.errors:
            print(f"    {color('-', Colors.RED)} {error}")
        return 1

    if prd_result.warnings:
        for warning in prd_result.warnings:
            print_warning(warning)

    print_success("PRD validation passed")

    if validate_only:
        print()
        print_info("Validation-only mode. Skipping generation.")
        return 0

    # Step 2: Read PRD content
    try:
        prd_content = read_file(prd_file)
        if verbose:
            print_step(f"PRD content length: {len(prd_content)} characters")
    except Exception as e:
        print_error(f"Failed to read PRD file: {e}")
        return 1

    # Step 3: Generate JSON
    print()
    print(color("Step 2: Generating JSON", Colors.BOLD))

    def progress_callback(message: str) -> None:
        if verbose:
            print_step(message)

    if verbose:
        print_step("Loading generation prompt...")

    config = GenerationConfig(
        temperature=0.3,
        max_tokens=16000
    )

    result = generate_json(
        prd_content=prd_content,
        config=config,
        progress_callback=progress_callback if verbose else None
    )

    if not result.success:
        print_error(f"Generation failed: {result.error_message}")
        return 1

    if verbose and result.token_usage:
        print_step(
            f"Token usage: {result.token_usage.get('input_tokens', '?')} input, "
            f"{result.token_usage.get('output_tokens', '?')} output"
        )

    # Step 4: Extract and format JSON
    print()
    print(color("Step 3: Processing Response", Colors.BOLD))

    try:
        json_content = extract_json_from_response(result.json_content)
        formatted_json = format_json(json_content)
        print_success("JSON extracted successfully")
    except ValueError as e:
        print_error(f"Failed to extract JSON: {e}")
        if verbose:
            print_info("Raw response (first 500 chars):")
            print(result.raw_response[:500] if result.raw_response else "None")
        return 1
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON syntax: {e}")
        return 1

    # Step 5: Comprehensive JSON validation
    print()
    print(color("Step 4: Validating Generated JSON", Colors.BOLD))

    validation_report = validate_insait_json(formatted_json)
    print_validation_report(validation_report, verbose)

    # Print stats
    if verbose and validation_report.stats:
        print()
        print(color("Statistics:", Colors.BOLD))
        if 'agent_name' in validation_report.stats:
            print_step(f"Agent: {validation_report.stats['agent_name']}")
        if 'node_count' in validation_report.stats:
            print_step(f"Nodes: {validation_report.stats['node_count']}")
        if 'exit_count' in validation_report.stats:
            print_step(f"Exits: {validation_report.stats['exit_count']}")
        if 'node_types' in validation_report.stats:
            print_step(f"Node types: {validation_report.stats['node_types']}")

    # Step 6: Save output (or not)
    print()
    print(color("Step 5: Saving Output", Colors.BOLD))

    if not validation_report.is_valid and not force_save:
        # Save to .invalid.json for debugging
        invalid_file = output_file.replace('.json', '.invalid.json')
        try:
            write_file(invalid_file, formatted_json)
            print_warning(f"Validation failed. Saved to: {invalid_file}")
            print_info("Use --force-save to save despite errors")
        except Exception as e:
            print_error(f"Failed to save file: {e}")
        return 1

    try:
        write_file(output_file, formatted_json)
        print_success(f"JSON saved to: {output_file}")
    except Exception as e:
        print_error(f"Failed to save file: {e}")
        return 1

    # Final summary
    print()
    if validation_report.is_valid:
        print(color("=" * 60, Colors.GREEN))
        print(color("  Generation Complete!", Colors.BOLD + Colors.GREEN))
        print(color("=" * 60, Colors.GREEN))
    else:
        print(color("=" * 60, Colors.YELLOW))
        print(color("  Generation Complete (with warnings)", Colors.BOLD + Colors.YELLOW))
        print(color("=" * 60, Colors.YELLOW))

    print()
    print(f"  Output file: {color(output_file, Colors.CYAN)}")
    if validation_report.stats.get('node_count'):
        print(f"  Nodes: {validation_report.stats['node_count']}")
    if validation_report.stats.get('exit_count'):
        print(f"  Exits: {validation_report.stats['exit_count']}")
    print()

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PRD to JSON Generator - Convert PRD files to INSAIT platform JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate JSON from PRD
  python main.py generate examples/test_prd.txt --output agent.json

  # Validate PRD only (no generation)
  python main.py generate examples/test_prd.txt --validate-only

  # Generate with verbose output
  python main.py generate examples/test_prd.txt --verbose

  # Validate existing JSON file
  python main.py validate agent.json

  # Validate with verbose output
  python main.py validate agent.json --verbose
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate JSON from a PRD file"
    )
    gen_parser.add_argument(
        "prd_file",
        help="Path to input PRD text file"
    )
    gen_parser.add_argument(
        "--output", "-o",
        default="output.json",
        help="Path to output JSON file (default: output.json)"
    )
    gen_parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate PRD without generating"
    )
    gen_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress and all warnings"
    )
    gen_parser.add_argument(
        "--force-save",
        action="store_true",
        help="Save output file even if validation fails"
    )

    # Validate command
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate an existing JSON file against INSAIT schema"
    )
    val_parser.add_argument(
        "json_file",
        help="Path to JSON file to validate"
    )
    val_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including warnings"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "generate":
        return generate_command(
            prd_file=args.prd_file,
            output_file=args.output,
            validate_only=args.validate_only,
            verbose=args.verbose,
            force_save=args.force_save
        )
    elif args.command == "validate":
        return validate_json_command(
            json_file=args.json_file,
            verbose=args.verbose
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
