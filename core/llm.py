"""Factory for the configured Groq chat model."""

import os

from .errors import LLMError


def create_chat_model():
    """Create a low-temperature ChatGroq client from environment settings."""

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")
    if not api_key or not model:
        raise LLMError("GROQ_API_KEY and GROQ_MODEL must be configured")
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise LLMError("langchain-groq is not installed") from exc
    return ChatGroq(
        api_key=api_key,
        model=model,
        temperature=0.1,
        timeout=30,
        max_retries=2,
    )
