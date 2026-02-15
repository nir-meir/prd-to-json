"""
AWS Bedrock Client - Simple connection to Claude models via AWS Bedrock.

Usage:
    python bedrock_client.py

Or import and use:
    from bedrock_client import chat
    response = chat("Hello, how are you?")
"""

import os
import json
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_bedrock_client():
    """
    Create a Bedrock Runtime client with proper authentication.

    Authentication priority:
    1. Bearer token (AWS_BEARER_TOKEN_BEDROCK) - fastest setup
    2. Access key + secret (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)
    3. Default AWS credential chain (IAM role, SSO profile, etc.)
    """
    region = os.getenv("AWS_REGION", "us-east-1")
    bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    # Option 1: Bearer token authentication
    if bearer_token:
        print(f"[Auth] Using bearer token authentication")
        return boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id="",  # Required but can be empty with session token
            aws_secret_access_key="",  # Required but can be empty with session token
            aws_session_token=bearer_token,
        )

    # Option 2: Access key + secret authentication
    if access_key and secret_key:
        print(f"[Auth] Using access key authentication")
        return boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    # Option 3: Default credential chain (SSO, IAM role, etc.)
    print(f"[Auth] Using default AWS credential chain")
    return boto3.client("bedrock-runtime", region_name=region)


def chat(
    message: str,
    model_id: str = None,
    system_prompt: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    Send a message to Claude via AWS Bedrock and get a response.

    Args:
        message: The user message to send
        model_id: Bedrock model ID (default: from .env or claude-sonnet)
        system_prompt: System instructions for the model
        max_tokens: Maximum tokens in response
        temperature: Creativity (0.0-1.0)

    Returns:
        The assistant's response text
    """
    client = get_bedrock_client()

    # Get model from env or use default
    if model_id is None:
        model_id = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-20250514-v1:0")

    print(f"[Model] Using: {model_id}")

    # Build the request body (Anthropic Claude format)
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ]
    }

    # Call Bedrock
    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body)
    )

    # Parse response
    response_body = json.loads(response["body"].read())

    # Extract text from Claude's response format
    if "content" in response_body and len(response_body["content"]) > 0:
        return response_body["content"][0]["text"]

    return str(response_body)


def chat_stream(
    message: str,
    model_id: str = None,
    system_prompt: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    temperature: float = 0.7,
):
    """
    Stream a response from Claude via AWS Bedrock.

    Yields:
        Text chunks as they arrive
    """
    client = get_bedrock_client()

    if model_id is None:
        model_id = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-20250514-v1:0")

    print(f"[Model] Using: {model_id}")

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ]
    }

    # Call Bedrock with streaming
    response = client.invoke_model_with_response_stream(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body)
    )

    # Process the stream
    for event in response["body"]:
        chunk = json.loads(event["chunk"]["bytes"])

        if chunk["type"] == "content_block_delta":
            if "delta" in chunk and "text" in chunk["delta"]:
                yield chunk["delta"]["text"]


# ============================================================================
# MAIN - Test the connection
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("AWS Bedrock Connection Test")
    print("=" * 60)

    test_message = "Say hello and tell me what model you are in one sentence."

    print(f"\n[User] {test_message}\n")
    print("[Assistant] ", end="", flush=True)

    try:
        # Test streaming response
        for chunk in chat_stream(test_message):
            print(chunk, end="", flush=True)
        print("\n")
        print("=" * 60)
        print("SUCCESS! Connection to AWS Bedrock is working.")
        print("=" * 60)

    except Exception as e:
        print(f"\n\nERROR: {type(e).__name__}: {e}")
        print("\nTroubleshooting:")
        print("1. Check your .env file has valid credentials")
        print("2. Ensure the model ID is correct and enabled in your AWS account")
        print("3. Verify your AWS region has Bedrock access")
