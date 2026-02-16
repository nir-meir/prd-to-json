"""
AWS Bedrock LLM Client implementation.

Provides Claude model access through AWS Bedrock service.
"""

import os
import json
from typing import Optional, Iterator
import time

from .base import BaseLLMClient, LLMConfig, LLMResponse, LLMMessage
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Lazy import boto3 to avoid import errors if not installed
boto3 = None
Config = None
ClientError = None
BotoCoreError = None


def _import_boto3():
    """Lazy import boto3 and related modules."""
    global boto3, Config, ClientError, BotoCoreError
    if boto3 is None:
        import boto3 as _boto3
        from botocore.config import Config as _Config
        from botocore.exceptions import ClientError as _ClientError, BotoCoreError as _BotoCoreError
        boto3 = _boto3
        Config = _Config
        ClientError = _ClientError
        BotoCoreError = _BotoCoreError


class BedrockClient(BaseLLMClient):
    """
    AWS Bedrock LLM client for Claude models.

    Supports authentication via:
    1. Bearer token (AWS_BEARER_TOKEN_BEDROCK)
    2. Access key + secret (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)
    3. Default AWS credential chain (IAM role, SSO, etc.)
    """

    DEFAULT_MODEL = "anthropic.claude-sonnet-4-20250514-v1:0"

    def __init__(self, config: Optional[LLMConfig] = None, region: Optional[str] = None):
        """
        Initialize the Bedrock client.

        Args:
            config: LLM configuration
            region: AWS region (default: from AWS_REGION env or us-east-1)
        """
        super().__init__(config)

        # Set default model if not specified
        if not self.config.model_id:
            self.config.model_id = os.getenv("BEDROCK_MODEL", self.DEFAULT_MODEL)

        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "bedrock"

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
        _import_boto3()

        bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        # Configure timeouts
        boto_config = Config(
            connect_timeout=30,
            read_timeout=self.config.timeout,
            retries={'max_attempts': self.config.max_retries}
        )

        if bearer_token:
            logger.debug("Using bearer token authentication")
            return boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id="",
                aws_secret_access_key="",
                aws_session_token=bearer_token,
                config=boto_config,
            )

        if access_key and secret_key:
            logger.debug("Using access key authentication")
            return boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=boto_config,
            )

        logger.debug("Using default AWS credential chain")
        return boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=boto_config
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response from Claude via Bedrock.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            **kwargs: Additional options (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with generated content or error
        """
        _import_boto3()

        # Merge kwargs with config
        temperature = kwargs.get('temperature', self.config.temperature)
        max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
        model_id = kwargs.get('model_id', self.config.model_id)

        # Build request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        if system_prompt:
            request_body["system"] = system_prompt

        if self.config.stop_sequences:
            request_body["stop_sequences"] = self.config.stop_sequences

        # Retry loop
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(f"Invoking model {model_id} (attempt {attempt + 1})")

                response = self.client.invoke_model(
                    modelId=model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(request_body)
                )

                response_body = json.loads(response["body"].read())

                # Extract token usage
                input_tokens = None
                output_tokens = None
                if "usage" in response_body:
                    input_tokens = response_body["usage"].get("input_tokens")
                    output_tokens = response_body["usage"].get("output_tokens")

                # Extract content
                if "content" not in response_body or not response_body["content"]:
                    return LLMResponse.error("Empty response from model")

                content = response_body["content"][0].get("text", "")
                finish_reason = response_body.get("stop_reason")

                return LLMResponse(
                    content=content,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=(input_tokens or 0) + (output_tokens or 0) if input_tokens or output_tokens else None,
                    model_id=model_id,
                    finish_reason=finish_reason,
                    raw_response=response_body,
                )

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                last_error = f"AWS error ({error_code}): {error_message}"

                if error_code == 'ThrottlingException' and attempt < self.config.max_retries:
                    logger.warning(f"Rate limited, retrying in {self.config.retry_delay}s...")
                    time.sleep(self.config.retry_delay * (attempt + 1))
                    continue

                logger.error(last_error)
                break

            except BotoCoreError as e:
                last_error = f"AWS connection error: {e}"
                logger.error(last_error)
                break

            except json.JSONDecodeError as e:
                last_error = f"Failed to parse response: {e}"
                logger.error(last_error)
                break

            except Exception as e:
                last_error = f"Unexpected error: {type(e).__name__}: {e}"
                logger.exception(last_error)
                break

        return LLMResponse.error(last_error or "Unknown error")

    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Generate a streaming response from Claude via Bedrock.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            **kwargs: Additional options

        Yields:
            Text chunks as they arrive
        """
        _import_boto3()

        # Merge kwargs with config
        temperature = kwargs.get('temperature', self.config.temperature)
        max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
        model_id = kwargs.get('model_id', self.config.model_id)

        # Build request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        if system_prompt:
            request_body["system"] = system_prompt

        try:
            response = self.client.invoke_model_with_response_stream(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body)
            )

            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])

                if chunk.get("type") == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if "text" in delta:
                        yield delta["text"]

        except Exception as e:
            logger.error(f"Streaming error: {type(e).__name__}: {e}")
            raise

    def is_available(self) -> bool:
        """
        Check if Bedrock is available and credentials are valid.

        Returns:
            True if service is reachable
        """
        try:
            _import_boto3()
            # Try a minimal request to verify credentials
            self.client.invoke_model(
                modelId=self.config.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "test"}]
                })
            )
            return True
        except Exception as e:
            logger.warning(f"Bedrock availability check failed: {e}")
            return False
