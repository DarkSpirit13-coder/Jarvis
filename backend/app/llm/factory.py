"""Factory for configured LLM provider instances."""

from app.config.settings import get_settings
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.provider import BaseLLMProvider


def get_llm_provider() -> BaseLLMProvider:
    """Return the configured swappable LLM provider."""
    return OpenAICompatibleProvider(get_settings())
