"""
LLM Factory for Maritime Message Loader.

Provides unified factory for instantiating Chat models supporting:
- OpenRouter (qwen/qwen-2.5-72b-instruct, google/gemma-4-31b-it:free, etc.)
- Groq (openai/gpt-oss-20b, etc.)
- Google Gemini (gemini-3.8-flash, etc.)
Configurable via environment variables:
- LLM_PROVIDER: "openrouter" (default if key present), "groq", or "gemini"
- OPENROUTER_MODEL: default "qwen/qwen-2.5-72b-instruct"
- GROQ_MODEL: default "openai/gpt-oss-20b"
- GEMINI_MODEL: default "gemini-3.8-flash"
"""

import logging
import os
from typing import Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(override=True)


def get_chat_llm(model: Optional[str] = None, temperature: float = 0.0) -> Any:
    """
    Instantiates and returns the configured Chat LLM (OpenRouter, Groq, or Gemini).

    Args:
        model: Optional model override name.
        temperature: Sampling temperature (default: 0.0 for deterministic extraction).

    Returns:
        BaseChatModel runnable instance.
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

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

    raise ValueError("No valid LLM credentials found (OPENROUTER_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY).")

