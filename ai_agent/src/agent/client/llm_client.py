"""
Settings, LLM provider selection, and environment configuration for Maritime AI Agent.
"""

import os
from typing import Any, List, Optional
from dotenv import load_dotenv

from ai_agent.src.utilities.logger import get_logger

logger = get_logger(__name__)
load_dotenv(override=True)


class LLMClient:
    """Client wrapper providing access to configured LLM instance."""

    @staticmethod
    def _build_openrouter_llm(model: Optional[str] = None, temperature: float = 0.0) -> Optional[Any]:
        openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not openrouter_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
            target_model = model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-vision-exp")
            provider_name = os.getenv("OPENROUTER_PROVIDER_NAME", "deepinfra/fp8")
            max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "2048"))

            extra_body = {"reasoning": {"enabled": True}}
            if provider_name:
                extra_body["provider"] = {"only": [provider_name], "allow_fallbacks": True}

            logger.debug("Configured OpenRouter model: %s (max_tokens: %d)", target_model, max_tokens)
            return ChatOpenAI(
                model=target_model,
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body
            )
        except Exception as e:
            logger.warning("Failed to configure OpenRouter LLM: %s", e)
            return None

    @staticmethod
    def _build_groq_llm(model: Optional[str] = None, temperature: float = 0.0) -> Optional[Any]:
        groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not groq_key:
            return None
        try:
            from langchain_groq import ChatGroq
            target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "2048"))
            logger.debug("Configured Groq model: %s (max_tokens: %d)", target_model, max_tokens)
            return ChatGroq(
                model=target_model,
                api_key=groq_key,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=2
            )
        except Exception as e:
            logger.warning("Failed to configure Groq LLM: %s", e)
            return None

    @staticmethod
    def _build_gemini_llm(model: Optional[str] = None, temperature: float = 0.0) -> Optional[Any]:
        gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if not gemini_key:
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            target_model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            logger.debug("Configured Gemini model: %s", target_model)
            return ChatGoogleGenerativeAI(model=target_model, api_key=gemini_key, temperature=temperature)
        except Exception as e:
            logger.warning("Failed to configure Gemini LLM: %s", e)
            return None

    @classmethod
    def get_agent_llm(
        cls,
        model: Optional[str] = None,
        temperature: float = 0.0,
        **kwargs: Any
    ) -> Any:
        """
        Instantiates and returns the configured Chat LLM.
        Provider is selected by LLM_PROVIDER ('openrouter', 'groq', 'gemini').
        """
        raw_provider = os.getenv("LLM_PROVIDER", "openrouter")
        provider = raw_provider.strip().lower() if raw_provider else "openrouter"
        if provider not in ['openrouter', 'groq', 'gemini']:
            raise ValueError(f"No valid LLM provider '{provider}', must be one of 'openrouter', 'groq', 'gemini'.")

        llm_instance = None
        if provider == "groq":
            llm_instance = cls._build_groq_llm(model=model, temperature=temperature)
        elif provider == "gemini":
            llm_instance = cls._build_gemini_llm(model=model, temperature=temperature)
        elif provider == "openrouter":
            llm_instance = cls._build_openrouter_llm(model=model, temperature=temperature)

        if llm_instance is None:
            raise RuntimeError(f"Failed to instantiate LLM for provider '{provider}'. Check your API keys in environment.")

        return llm_instance


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any
) -> Any:
    """Builds and returns the configured Chat LLM instance."""
    return LLMClient.get_agent_llm(model=model, temperature=temperature, **kwargs)


get_agent_llm = get_llm


def get_summarization_token_trigger() -> int:
    """Infers the token threshold trigger for LangGraph SummarizationMiddleware from environment."""
    env_limit = os.getenv("SUMMARIZATION_TOKEN_TRIGGER")
    if env_limit and env_limit.strip().isdigit():
        return int(env_limit.strip())
    for key in ["OPENROUTER_MAX_TOKENS", "GROQ_MAX_TOKENS"]:
        val = os.getenv(key)
        if val and val.strip().isdigit():
            return int(val.strip())
    return 2048


__all__ = ["LLMClient", "get_llm", "get_agent_llm", "get_summarization_token_trigger"]
