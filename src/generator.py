"""
Generator - AWS Bedrock interaction for PRD to JSON conversion.

Handles communication with Claude via AWS Bedrock to generate
INSAIT platform JSON from PRD content.
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class GenerationConfig:
    """Configuration for JSON generation."""
    model_id: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 64000  # Increased to handle complex PRDs with many nodes
    timeout: int = 300  # Read timeout in seconds - time to wait for model response

    def __post_init__(self):
        if self.model_id is None:
            self.model_id = os.getenv(
                "BEDROCK_MODEL",
                "anthropic.claude-sonnet-4-20250514-v1:0"
            )


@dataclass
class GenerationResult:
    """Result of JSON generation."""
    success: bool
    json_content: Optional[str] = None
    raw_response: Optional[str] = None
    error_message: Optional[str] = None
    token_usage: Optional[dict] = None


class BedrockGenerator:
    """
    Generator for converting PRD to JSON using AWS Bedrock.

    Uses Claude Sonnet 4.5 to generate INSAIT platform JSON
    from plain English PRD documents.
    """

    def __init__(self, config: Optional[GenerationConfig] = None):
        """
        Initialize the generator.

        Args:
            config: Generation configuration
        """
        self.config = config or GenerationConfig()
        self._client = None

    @property
    def client(self):
        """Lazy-load Bedrock client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self):
        """
        Create a Bedrock Runtime client with proper authentication.

        Authentication priority:
        1. Bearer token (AWS_BEARER_TOKEN_BEDROCK)
        2. Access key + secret (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)
        3. Default AWS credential chain
        """
        region = os.getenv("AWS_REGION", "us-east-1")
        bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        # Configure timeouts: connect_timeout for initial connection,
        # read_timeout for waiting for response (generation can take a while)
        boto_config = Config(
            connect_timeout=30,
            read_timeout=self.config.timeout,  # Use the configured timeout
            retries={'max_attempts': 2}
        )

        if bearer_token:
            return boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id="",
                aws_secret_access_key="",
                aws_session_token=bearer_token,
                config=boto_config,
            )

        if access_key and secret_key:
            return boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=boto_config,
            )

        return boto3.client("bedrock-runtime", region_name=region, config=boto_config)

    def generate(
        self,
        prd_content: str,
        system_prompt: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> GenerationResult:
        """
        Generate JSON from PRD content.

        Args:
            prd_content: Plain English PRD content
            system_prompt: System prompt for generation
            progress_callback: Optional callback for progress updates

        Returns:
            GenerationResult with generated JSON or error
        """
        if progress_callback:
            progress_callback("Connecting to AWS Bedrock...")

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": prd_content
                }
            ]
        }

        try:
            if progress_callback:
                progress_callback(f"Invoking model: {self.config.model_id}")

            response = self.client.invoke_model(
                modelId=self.config.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body)
            )

            if progress_callback:
                progress_callback("Processing response...")

            response_body = json.loads(response["body"].read())

            # Extract token usage
            token_usage = None
            if "usage" in response_body:
                token_usage = {
                    "input_tokens": response_body["usage"].get("input_tokens"),
                    "output_tokens": response_body["usage"].get("output_tokens")
                }

            # Extract text content
            if "content" not in response_body or not response_body["content"]:
                return GenerationResult(
                    success=False,
                    error_message="Empty response from model"
                )

            raw_response = response_body["content"][0].get("text", "")

            return GenerationResult(
                success=True,
                json_content=raw_response,
                raw_response=raw_response,
                token_usage=token_usage
            )

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'ThrottlingException':
                return GenerationResult(
                    success=False,
                    error_message=f"Rate limited by AWS Bedrock. Please wait and retry. ({error_message})"
                )
            elif error_code == 'ValidationException':
                return GenerationResult(
                    success=False,
                    error_message=f"Invalid request: {error_message}"
                )
            elif error_code == 'AccessDeniedException':
                return GenerationResult(
                    success=False,
                    error_message=f"Access denied. Check your AWS credentials. ({error_message})"
                )
            else:
                return GenerationResult(
                    success=False,
                    error_message=f"AWS error ({error_code}): {error_message}"
                )

        except BotoCoreError as e:
            return GenerationResult(
                success=False,
                error_message=f"AWS connection error: {e}"
            )

        except json.JSONDecodeError as e:
            return GenerationResult(
                success=False,
                error_message=f"Failed to parse model response: {e}"
            )

        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"Unexpected error: {type(e).__name__}: {e}"
            )


def load_generation_prompt(prompt_path: Optional[str | Path] = None) -> str:
    """
    Load the generation prompt from file.

    Args:
        prompt_path: Path to prompt file (default: prompts/generation_prompt.md)

    Returns:
        Prompt content as string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    if prompt_path is None:
        # Default to prompts directory relative to project root
        project_root = Path(__file__).parent.parent
        prompt_path = project_root / "prompts" / "generation_prompt.md"

    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Generation prompt not found: {prompt_path}")

    return path.read_text(encoding='utf-8')


def generate_json(
    prd_content: str,
    prompt_path: Optional[str | Path] = None,
    config: Optional[GenerationConfig] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> GenerationResult:
    """
    Convenience function to generate JSON from PRD content.

    Args:
        prd_content: Plain English PRD content
        prompt_path: Path to generation prompt file
        config: Generation configuration
        progress_callback: Optional callback for progress updates

    Returns:
        GenerationResult with generated JSON or error
    """
    try:
        system_prompt = load_generation_prompt(prompt_path)
    except FileNotFoundError as e:
        return GenerationResult(
            success=False,
            error_message=str(e)
        )

    generator = BedrockGenerator(config)
    return generator.generate(prd_content, system_prompt, progress_callback)
