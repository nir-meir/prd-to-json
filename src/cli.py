"""
CLI - Command-line interface for PRD to JSON conversion.

Main entry point for the application. Orchestrates:
1. PRD file loading
2. Parsing with extractors
3. JSON generation with strategy selection
4. Validation and auto-fixing
5. Output to file or stdout
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .parser import PRDParser, ParsedPRD
from .generator import create_generator, GenerationResult
from .validator import INSAITValidator, AutoFixer
from .core.config import AppConfig
from .llm import BedrockClient, MockLLMClient
from .utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert PRD documents to INSAIT JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.md -o output.json
  %(prog)s input.md --strategy simple --no-fix
  %(prog)s input.md --dry-run --verbose
        """,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input PRD file (markdown or text)",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output JSON file (default: stdout)",
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Configuration file (YAML)",
    )

    parser.add_argument(
        "-s", "--strategy",
        choices=["auto", "simple", "chunked", "hybrid"],
        default="auto",
        help="Generation strategy (default: auto)",
    )

    parser.add_argument(
        "--no-fix",
        action="store_true",
        help="Disable auto-fixing of validation issues",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only, don't generate output",
    )

    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM for testing (no API calls)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)",
    )

    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    args = parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)

    logger.info(f"PRD to JSON Generator")
    logger.info(f"Input: {args.input}")

    # Validate input file
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    # Load configuration
    config = AppConfig()
    if args.config and args.config.exists():
        config = AppConfig.from_yaml(args.config)
        logger.info(f"Loaded config from: {args.config}")

    # Create LLM client
    if args.mock_llm:
        llm_client = MockLLMClient(default_response="{}")
        logger.info("Using mock LLM client")
    else:
        llm_client = BedrockClient()
        logger.info("Using Bedrock LLM client")

    try:
        # Step 1: Parse PRD
        logger.info("Step 1: Parsing PRD...")
        parser = PRDParser(config=config, llm_client=llm_client)
        parsed_prd = parser.parse_file(args.input)

        logger.info(f"Parsed: {parsed_prd.metadata.name}")
        logger.info(f"  Complexity: {parsed_prd.complexity.value}")
        logger.info(f"  Features: {len(parsed_prd.features)}")
        logger.info(f"  Variables: {len(parsed_prd.variables)}")
        logger.info(f"  APIs: {len(parsed_prd.apis)}")

        if args.dry_run:
            logger.info("Dry run - stopping after parse")
            print(parsed_prd.summary())
            return 0

        # Step 2: Generate JSON
        logger.info("Step 2: Generating JSON...")
        generator = create_generator(parsed_prd, config, llm_client)
        result = generator.generate(parsed_prd)

        if not result.success:
            logger.error(f"Generation failed: {result.error_message}")
            return 1

        logger.info(f"Generated: {result.stats}")

        # Step 3: Validate
        logger.info("Step 3: Validating...")
        validator = INSAITValidator(strict_mode=args.strict)
        validation = validator.validate(result.json_output)

        logger.info(f"Validation: valid={validation.valid}, "
                   f"errors={len(validation.errors)}, "
                   f"warnings={len(validation.warnings)}")

        # Step 4: Auto-fix if needed
        output_json = result.json_output
        if not validation.valid and not args.no_fix:
            if validation.auto_fixable_count > 0:
                logger.info(f"Step 4: Auto-fixing {validation.auto_fixable_count} issues...")
                fixer = AutoFixer()
                fix_result = fixer.fix(output_json, validation)

                logger.info(f"Applied {len(fix_result.fixes_applied)} fixes")
                if fix_result.fixes_failed:
                    for fail in fix_result.fixes_failed:
                        logger.warning(f"  Failed: {fail}")

                output_json = fix_result.fixed_data

                # Re-validate
                validation = validator.validate(output_json)
                logger.info(f"After fixes: valid={validation.valid}")

        # Report remaining issues
        if validation.errors:
            logger.error("Remaining errors:")
            for issue in validation.errors[:5]:
                logger.error(f"  - {issue.code}: {issue.message}")

        if validation.warnings:
            logger.warning("Warnings:")
            for issue in validation.warnings[:5]:
                logger.warning(f"  - {issue.code}: {issue.message}")

        # Step 5: Output
        logger.info("Step 5: Writing output...")

        if args.pretty:
            json_str = json.dumps(output_json, indent=args.indent, ensure_ascii=False)
        else:
            json_str = json.dumps(output_json, ensure_ascii=False)

        if args.output:
            args.output.write_text(json_str, encoding="utf-8")
            logger.info(f"Output written to: {args.output}")
        else:
            print(json_str)

        # Return based on validation status
        if validation.errors:
            logger.warning("Completed with errors")
            return 1 if args.strict else 0
        elif validation.warnings:
            logger.info("Completed with warnings")
            return 0
        else:
            logger.info("Completed successfully")
            return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def run_pipeline(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    config: Optional[AppConfig] = None,
    use_mock_llm: bool = False,
    auto_fix: bool = True,
) -> dict:
    """
    Programmatic interface to run the full pipeline.

    Args:
        input_path: Path to PRD file
        output_path: Optional path to write output
        config: Optional configuration
        use_mock_llm: Use mock LLM for testing
        auto_fix: Enable auto-fixing

    Returns:
        Generated JSON dict
    """
    config = config or AppConfig()
    input_path = Path(input_path)

    # Create LLM client
    if use_mock_llm:
        llm_client = MockLLMClient(default_response="{}")
    else:
        llm_client = BedrockClient()

    # Parse
    parser = PRDParser(config=config, llm_client=llm_client)
    parsed_prd = parser.parse_file(input_path)

    # Generate
    generator = create_generator(parsed_prd, config, llm_client)
    result = generator.generate(parsed_prd)

    if not result.success:
        raise RuntimeError(f"Generation failed: {result.error_message}")

    # Validate and fix
    output_json = result.json_output
    if auto_fix:
        validator = INSAITValidator()
        validation = validator.validate(output_json)

        if not validation.valid and validation.auto_fixable_count > 0:
            fixer = AutoFixer()
            fix_result = fixer.fix(output_json, validation)
            output_json = fix_result.fixed_data

    # Output
    if output_path:
        output_path = Path(output_path)
        output_path.write_text(
            json.dumps(output_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return output_json


if __name__ == "__main__":
    sys.exit(main())
