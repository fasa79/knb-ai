"""Swappable LLM client — abstracts provider behind a unified interface.

Supports: Google Gemini, Groq, Ollama. Switch via LLM_PROVIDER env var.
To add a new provider: implement BaseLLMClient and register in get_llm_client().
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Retry config for rate-limited APIs
MAX_RETRIES = 1
RETRY_BASE_DELAY = 5  # seconds


class BaseLLMClient(ABC):
    """Abstract LLM client — every provider implements this."""

    @abstractmethod
    def get_chat_model(self, temperature: float = 0.1, model_override: str | None = None, **kwargs: Any) -> BaseChatModel:
        """Return a LangChain-compatible chat model instance."""
        ...

    @abstractmethod
    def get_structured_model(self, schema: type, temperature: float = 0.0, **kwargs: Any) -> BaseChatModel:
        """Return a chat model configured for structured (JSON) output."""
        ...

    async def generate(self, prompt: str, system_prompt: str | None = None, temperature: float = 0.1, model_override: str | None = None) -> str:
        """Simple text generation helper with retry for rate limits."""
        model = self.get_chat_model(temperature=temperature, model_override=model_override)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await model.ainvoke(messages)
                return response.content
            except Exception as e:
                err_str = str(e)
                is_retryable = ("429" in err_str or "quota" in err_str.lower()) and "404" not in err_str
                if is_retryable and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                raise

    async def generate_structured(
        self, prompt: str, schema: type, system_prompt: str | None = None, temperature: float = 0.0
    ) -> Any:
        """Generate structured output conforming to a Pydantic schema."""
        model = self.get_structured_model(schema=schema, temperature=temperature)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = await model.ainvoke(messages)
        return response


class GeminiClient(BaseLLMClient):
    """Google Gemini LLM client."""

    def __init__(self, settings: Settings):
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required when using google_gemini provider")

    def get_chat_model(self, temperature: float = 0.1, model_override: str | None = None, **kwargs: Any) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_override or self.model_name,
            google_api_key=self.api_key,
            temperature=temperature,
            max_retries=0,
            **kwargs,
        )

    def get_structured_model(self, schema: type, temperature: float = 0.0, **kwargs: Any) -> BaseChatModel:
        model = self.get_chat_model(temperature=temperature, **kwargs)
        return model.with_structured_output(schema)


class GroqClient(BaseLLMClient):
    """Groq LLM client."""

    def __init__(self, settings: Settings):
        self.api_key = settings.groq_api_key
        self.model_name = settings.groq_model
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required when using groq provider")

    def get_chat_model(self, temperature: float = 0.1, model_override: str | None = None, **kwargs: Any) -> BaseChatModel:
        from langchain_community.chat_models import ChatGroq

        return ChatGroq(
            model=model_override or self.model_name,
            groq_api_key=self.api_key,
            temperature=temperature,
            **kwargs,
        )

    def get_structured_model(self, schema: type, temperature: float = 0.0, **kwargs: Any) -> BaseChatModel:
        model = self.get_chat_model(temperature=temperature, **kwargs)
        return model.with_structured_output(schema)


class OllamaClient(BaseLLMClient):
    """Ollama (local) LLM client."""

    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_base_url
        self.model_name = settings.ollama_model

    def get_chat_model(self, temperature: float = 0.1, model_override: str | None = None, **kwargs: Any) -> BaseChatModel:
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            model=model_override or self.model_name,
            base_url=self.base_url,
            temperature=temperature,
            **kwargs,
        )

    def get_structured_model(self, schema: type, temperature: float = 0.0, **kwargs: Any) -> BaseChatModel:
        model = self.get_chat_model(temperature=temperature, format="json", **kwargs)
        return model.with_structured_output(schema)


# ── Provider Registry ─────────────────────────────────────────────

_PROVIDERS: dict[str, type[BaseLLMClient]] = {
    "google_gemini": GeminiClient,
    "groq": GroqClient,
    "ollama": OllamaClient,
}

_client_instance: BaseLLMClient | None = None


def get_llm_client(settings: Settings | None = None) -> BaseLLMClient:
    """Return a singleton LLM client based on the configured provider."""
    global _client_instance
    if _client_instance is None:
        settings = settings or get_settings()
        provider = settings.llm_provider.lower()
        if provider not in _PROVIDERS:
            raise ValueError(f"Unknown LLM provider: {provider}. Available: {list(_PROVIDERS.keys())}")
        _client_instance = _PROVIDERS[provider](settings)
        logger.info(f"Initialized LLM client: {provider}")
    return _client_instance


def reset_llm_client() -> None:
    """Reset the singleton (useful for testing or provider switching)."""
    global _client_instance
    _client_instance = None


# ── Available Models (for frontend selection) ─────────────────────

AVAILABLE_MODELS = [
    {"id": "gemini-3.1-flash-lite-preview", "name": "Gemini 3.1 Flash Lite", "rpm": 15, "rpd": 500, "provider": "google_gemini"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "rpm": 5, "rpd": 20, "provider": "google_gemini"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "rpm": 10, "rpd": 20, "provider": "google_gemini"},
    {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash", "rpm": 5, "rpd": 20, "provider": "google_gemini"},
]
