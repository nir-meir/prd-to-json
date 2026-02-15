"""
Example usage of AWS Bedrock with Claude models.
"""

from bedrock_client import chat, chat_stream


def example_simple_chat():
    """Basic question-answer."""
    print("\n=== Simple Chat ===")
    response = chat("What are the 3 largest planets in our solar system?")
    print(response)


def example_custom_system_prompt():
    """Chat with custom persona."""
    print("\n=== Custom System Prompt ===")
    response = chat(
        message="How do I make pasta?",
        system_prompt="You are an Italian grandmother. Respond with warmth and include cultural tips.",
        temperature=0.9
    )
    print(response)


def example_code_generation():
    """Generate code."""
    print("\n=== Code Generation ===")
    response = chat(
        message="Write a Python function that checks if a number is prime",
        system_prompt="You are a senior Python developer. Write clean, efficient code with docstrings.",
        temperature=0.3  # Lower temperature for more precise code
    )
    print(response)


def example_streaming():
    """Stream response in real-time."""
    print("\n=== Streaming Response ===")
    print("Assistant: ", end="", flush=True)
    for chunk in chat_stream("Explain quantum computing in simple terms"):
        print(chunk, end="", flush=True)
    print()


def example_conversation():
    """Multi-turn conversation (stateless - you manage history)."""
    print("\n=== Multi-turn Conversation ===")

    # For multi-turn, you'd need to extend the client to accept message history
    # This is a simplified example showing the concept

    # Turn 1
    response1 = chat("My name is Nir. Remember that.")
    print(f"Turn 1: {response1}")

    # Turn 2 - Note: This is stateless, so we include context in the message
    response2 = chat(
        "I told you my name earlier. What is it?",
        system_prompt="The user's name is Nir. They mentioned it in a previous message."
    )
    print(f"Turn 2: {response2}")


if __name__ == "__main__":
    print("=" * 60)
    print("AWS Bedrock Examples")
    print("=" * 60)

    # Run examples
    example_simple_chat()
    example_streaming()

    # Uncomment to run more examples:
    # example_custom_system_prompt()
    # example_code_generation()
    # example_conversation()
