"""
LLM Factory for Maritime Message Loader.

Provides unified factory for instantiating Chat models supporting:
- Azure AI (OpenAI-compatible endpoint; any deployment, e.g. gpt-6-luna)
- OpenRouter (qwen/qwen-2.5-72b-instruct, google/gemma-4-31b-it:free, etc.)
- Groq (openai/gpt-oss-20b, etc.)
- Google Gemini (gemini-3.8-flash, etc.)
Configurable via environment variables:
- LLM_PROVIDER: "azure", "openrouter" (default if key present), "groq", or "gemini"
- AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT_NAME (+ optional AZURE_MAX_TOKENS, AZURE_TEMPERATURE)
- OPENROUTER_MODEL: default "qwen/qwen-2.5-72b-instruct"
- GROQ_MODEL: default "openai/gpt-oss-20b"
- GEMINI_MODEL: default "gemini-3.8-flash"

Azure is selected exactly as the agent selects it (ai_agent/src/agent/client/llm_client.py): explicitly through
LLM_PROVIDER, or automatically when AZURE_API_KEY is set and no provider is named. The Azure settings are read here
directly, rather than imported from the agent, so the knowledge-graph layer does not depend on the agent layer.
"""

import logging
import os
from typing import Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(override=True)

_AZURE_PROVIDERS = {"azure", "azure_openai", "azure_ai"}
# Reasoning / preview deployments reject temperature=0, so the temperature is omitted for them.
_NO_TEMPERATURE_MARKERS = ("luna", "o1", "o3", "reasoning", "preview")


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().strip("'\"")


def _azure_temperature(deployment: str, default: float) -> Optional[float]:
    """Temperature to send to Azure, or None to omit it (AZURE_TEMPERATURE / LLM_TEMPERATURE override)."""
    override = os.getenv("AZURE_TEMPERATURE", os.getenv("LLM_TEMPERATURE"))
    if override is not None and override.strip():
        if override.strip().lower() in ("none", "null", "default", "omit"):
            return None
        try:
            return float(override.strip())
        except ValueError:
            return None
    if any(marker in deployment.lower() for marker in _NO_TEMPERATURE_MARKERS):
        return None
    return default


def _build_azure_llm(model: Optional[str], temperature: float) -> Any:
    """Builds the Azure AI chat model. Raises a clear error if the settings are incomplete."""
    from langchain_openai import ChatOpenAI

    api_key = _clean(os.getenv("AZURE_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
    endpoint = _clean(os.getenv("AZURE_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT"))
    deployment = _clean(model or os.getenv("AZURE_DEPLOYMENT_NAME") or os.getenv("AZURE_MODEL"))

    missing = [
        name for name, value in (
            ("AZURE_API_KEY", api_key),
            ("AZURE_ENDPOINT", endpoint),
            ("AZURE_DEPLOYMENT_NAME", deployment),
        ) if not value
    ]
    if missing:
        raise ValueError("Azure LLM selected but these settings are missing: " + ", ".join(missing))

    kwargs = {
        "model": deployment,
        "openai_api_key": api_key,
        "openai_api_base": endpoint,
        "max_tokens": int(os.getenv("AZURE_MAX_TOKENS", os.getenv("MAX_TOKENS", "8192"))),
    }
    azure_temperature = _azure_temperature(deployment, temperature)
    if azure_temperature is not None:
        kwargs["temperature"] = azure_temperature

    logger.debug("Using Azure AI Chat model: %s (temperature: %s)", deployment, azure_temperature)
    return ChatOpenAI(**kwargs)


def get_chat_llm(model: Optional[str] = None, temperature: float = 0.0) -> Any:
    """
    Instantiates and returns the configured Chat LLM (Azure, OpenRouter, Groq, or Gemini).

    Args:
        model: Optional model (Azure: deployment) override name.
        temperature: Sampling temperature (default: 0.0 for deterministic extraction).

    Returns:
        BaseChatModel runnable instance.
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    azure_key = _clean(os.getenv("AZURE_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    # 0. Azure AI (explicitly requested, or auto-detected from its key when no provider is named, as in the agent)
    if provider in _AZURE_PROVIDERS or (not provider and azure_key):
        return _build_azure_llm(model, temperature)

    # 1. OpenRouter (highest priority if key present or explicitly requested)
    if (provider == "openrouter" or (not provider and openrouter_key)) and openrouter_key:
        from langchain_openai import ChatOpenAI
        target_model = model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-vision-exp")
        provider_name = os.getenv("OPENROUTER_PROVIDER_NAME", "deepinfra/fp8")
        max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "4096"))
        logger.debug("Using OpenRouter Chat model: %s (provider: %s, max_tokens: %d)", target_model, provider_name, max_tokens)

        extra_body = {
            "reasoning": {"enabled": True}
        }
        if provider_name:
            extra_body["provider"] = {
                "only": [provider_name],
                "allow_fallbacks": False
            }

        return ChatOpenAI(
            model=target_model,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body
        )



    # 2. Groq
    if (provider == "groq" or (not provider and groq_key)) and groq_key:
        from langchain_groq import ChatGroq
        target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        logger.debug("Using Groq Chat model: %s", target_model)
        return ChatGroq(
            model=target_model,
            api_key=groq_key,
            temperature=temperature
        )

    # 3. Google Gemini
    if gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        target_model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        logger.debug("Using Gemini Chat model: %s", target_model)
        return ChatGoogleGenerativeAI(
            model=target_model,
            api_key=gemini_key,
            temperature=temperature
        )

    # Fallback to OpenRouter or Groq
    if openrouter_key:
        from langchain_openai import ChatOpenAI
        max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "4096"))
        return ChatOpenAI(
            model=model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-vision-exp"),
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"reasoning": {"enabled": True}}
        )

    if groq_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model or "openai/gpt-oss-20b",
            api_key=groq_key,
            temperature=temperature
        )

    raise ValueError(
        "No valid LLM credentials found (AZURE_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY)."
    )

