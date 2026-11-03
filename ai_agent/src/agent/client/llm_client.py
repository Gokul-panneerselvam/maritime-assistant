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
            target_model = model or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-scout")
            provider_name = (os.getenv("OPENROUTER_PROVIDER_NAME") or "").strip()
            max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "4096"))

            extra_body = {}
            if provider_name:
                extra_body["provider"] = {"only": [provider_name], "allow_fallbacks": True}

            logger.info("Configured OpenRouter model: %s (max_tokens: %d)", target_model, max_tokens)
            return ChatOpenAI(
                model=target_model,
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body if extra_body else None
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

            class RobustChatGroq(ChatGroq):
                """ChatGroq with parameter sanitization conforming to Groq's API constraints."""

                def with_structured_output(self, schema, **kwargs):
                    if "method" not in kwargs:
                        kwargs["method"] = "json_schema"
                    return super().with_structured_output(schema, **kwargs)

                @staticmethod
                def _sanitize_groq_params(params: dict) -> dict:
                    # Groq API rule: json mode cannot be combined with tool/function calling
                    if params.get("tools") and "response_format" in params:
                        cleaned = dict(params)
                        cleaned.pop("response_format", None)
                        return cleaned
                    return params

                def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                    message_dicts, params = self._create_message_dicts(messages, stop)
                    params = self._sanitize_groq_params({**params, **kwargs})
                    try:
                        response = self.client.create(messages=message_dicts, **params)
                        return self._create_chat_result(response, params)
                    except Exception as exc:
                        err_msg = str(exc).lower()
                        if ("rate_limit_exceeded" in err_msg or "413" in err_msg or "too large" in err_msg) and params.get("model") != "llama-3.3-70b-versatile":
                            logger.warning(
                                "Groq TPM limit reached for model '%s'. Falling back to 'llama-3.3-70b-versatile' (100k TPM)...",
                                params.get("model")
                            )
                            fallback_params = dict(params)
                            fallback_params["model"] = "llama-3.3-70b-versatile"
                            response = self.client.create(messages=message_dicts, **fallback_params)
                            return self._create_chat_result(response, fallback_params)
                        raise

                async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                    message_dicts, params = self._create_message_dicts(messages, stop)
                    params = self._sanitize_groq_params({**params, **kwargs})
                    try:
                        response = await self.async_client.create(messages=message_dicts, **params)
                        return self._create_chat_result(response, params)
                    except Exception as exc:
                        err_msg = str(exc).lower()
                        if ("rate_limit_exceeded" in err_msg or "413" in err_msg or "too large" in err_msg) and params.get("model") != "llama-3.3-70b-versatile":
                            logger.warning(
                                "Groq TPM limit reached for model '%s'. Falling back to 'llama-3.3-70b-versatile' (100k TPM)...",
                                params.get("model")
                            )
                            fallback_params = dict(params)
                            fallback_params["model"] = "llama-3.3-70b-versatile"
                            response = await self.async_client.create(messages=message_dicts, **fallback_params)
                            return self._create_chat_result(response, fallback_params)
                        raise

                def _stream(self, messages, stop=None, run_manager=None, **kwargs):
                    kwargs = self._sanitize_groq_params(kwargs)
                    return super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)

                async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
                    kwargs = self._sanitize_groq_params(kwargs)
                    async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                        yield chunk

            env_model = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
            # openai/gpt-oss-120b has an 8k TPM limit on Groq free tier which causes 413 Payload Too Large on complex prompts
            if env_model == "openai/gpt-oss-120b":
                target_model = model or "llama-3.3-70b-versatile"
            else:
                target_model = model or env_model
            max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "2048"))
            logger.debug("Configured Groq model: %s (max_tokens: %d)", target_model, max_tokens)
            return RobustChatGroq(
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
    def _build_bedrock_llm(model: Optional[str] = None, temperature: float = 0.0) -> Optional[Any]:
        arn = (
            model
            or os.getenv("ARN")
            or os.getenv("BEDROCK_MODEL_ARN")
            or os.getenv("AWS_BEDROCK_MODEL_ARN")
            or os.getenv("BEDROCK_MODEL_ID")
            or ""
        ).strip().strip("'\"")

        if not arn:
            logger.warning("No AWS Bedrock ARN found in environment (ARN / BEDROCK_MODEL_ARN).")
            return None

        try:
            from langchain_aws import ChatBedrockConverse

            # Extract region from ARN if present: arn:aws:bedrock:<region>:<account>:...
            region_name = (
                os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or ""
            ).strip().strip("'\"")

            if not region_name and ":bedrock:" in arn:
                parts = arn.split(":")
                if len(parts) >= 4:
                    region_name = parts[3]
            region_name = region_name or "ap-southeast-2"

            # Detect provider from ARN/model string (Bedrock requires provider when passing an ARN)
            provider = (os.getenv("BEDROCK_MODEL_PROVIDER") or "").strip().strip("'\"")
            if not provider:
                model_segment = arn.split("/")[-1] if "/" in arn else arn
                if "anthropic" in model_segment.lower():
                    provider = "anthropic"
                elif "amazon" in model_segment.lower():
                    provider = "amazon"
                elif "meta" in model_segment.lower():
                    provider = "meta"
                elif "cohere" in model_segment.lower():
                    provider = "cohere"
                elif "mistral" in model_segment.lower():
                    provider = "mistral"
                else:
                    provider = "anthropic"

            max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", os.getenv("MAX_TOKENS", "4096")))

            kwargs = {
                "model_id": arn,
                "provider": provider,
                "region_name": region_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            aws_access_key = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip().strip("'\"")
            aws_secret_key = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip().strip("'\"")
            aws_session_token = (os.getenv("AWS_SESSION_TOKEN") or "").strip().strip("'\"")

            if aws_access_key and aws_secret_key:
                kwargs["aws_access_key_id"] = aws_access_key
                kwargs["aws_secret_access_key"] = aws_secret_key
                if aws_session_token:
                    kwargs["aws_session_token"] = aws_session_token

            logger.info("Configured AWS Bedrock LLM: %s (region: %s, provider: %s)", arn, region_name, provider)
            return ChatBedrockConverse(**kwargs)

        except Exception as e:
            logger.error("Failed to configure AWS Bedrock LLM: %s", e, exc_info=True)
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

    @staticmethod
    def _build_azure_llm(model: Optional[str] = None, temperature: float = 0.0) -> Optional[Any]:
        azure_key = (
            os.getenv("AZURE_API_KEY")
            or os.getenv("AZURE_OPENAI_API_KEY")
            or ""
        ).strip().strip("'\"")
        if not azure_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
            target_model = (
                model
                or os.getenv("AZURE_DEPLOYMENT_NAME")
                or os.getenv("AZURE_MODEL")
                or "DeepSeek-V4-Pro"
            ).strip().strip("'\"")
            endpoint = (
                os.getenv("AZURE_ENDPOINT")
                or os.getenv("AZURE_OPENAI_ENDPOINT")
            ).strip().strip("'\"")

            max_tokens = int(os.getenv("AZURE_MAX_TOKENS", os.getenv("MAX_TOKENS", "8192")))

            # Check if environment specifies a temperature override or if target model
            # is a reasoning/preview model (e.g. gpt-6-luna, o1, o3) where temperature=0.0 is unsupported.
            env_temp = os.getenv("AZURE_TEMPERATURE", os.getenv("LLM_TEMPERATURE"))
            target_temp = temperature
            if env_temp is not None and env_temp.strip():
                if env_temp.strip().lower() in ("none", "null", "default", "omit"):
                    target_temp = None
                else:
                    try:
                        target_temp = float(env_temp.strip())
                    except ValueError:
                        target_temp = None
            else:
                # Models like gpt-6-luna, o1, o3 only support default (1) or omitting temperature
                if any(x in target_model.lower() for x in ("luna", "o1", "o3", "reasoning", "preview")):
                    target_temp = None

            llm_kwargs = {
                "model": target_model,
                "openai_api_key": azure_key,
                "openai_api_base": endpoint,
                "max_tokens": max_tokens,
            }
            if target_temp is not None:
                llm_kwargs["temperature"] = target_temp

            logger.info("Configured Azure AI LLM: %s at %s (max_tokens: %d, temperature: %s)", target_model, endpoint, max_tokens, target_temp)
            return ChatOpenAI(**llm_kwargs)
        except Exception as e:
            logger.error("Failed to configure Azure LLM: %s", e, exc_info=True)
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
        Provider is selected by LLM_PROVIDER ('azure', 'bedrock', 'groq', 'gemini', 'openrouter').
        """
        raw_provider = os.getenv("LLM_PROVIDER", "")
        provider = raw_provider.strip().lower() if raw_provider else ""

        # Auto-detect azure if AZURE_API_KEY is present and provider wasn't explicitly set to another
        if provider in ["azure", "azure_openai", "azure_ai"] or (not provider and os.getenv("AZURE_API_KEY")):
            provider = "azure"
        elif provider in ["bedrock", "aws", "aws_bedrock"] or (not provider and os.getenv("ARN")):
            provider = "bedrock"
        elif not provider:
            provider = "groq"

        valid_providers = ["azure", "azure_openai", "azure_ai", "bedrock", "aws", "aws_bedrock", "groq", "gemini", "openrouter"]
        if provider not in valid_providers:
            raise ValueError(f"No valid LLM provider '{provider}', must be one of {valid_providers}.")

        llm_instance = None
        if provider in ["azure", "azure_openai", "azure_ai"]:
            llm_instance = cls._build_azure_llm(model=model, temperature=temperature)
        elif provider in ["bedrock", "aws", "aws_bedrock"]:
            llm_instance = cls._build_bedrock_llm(model=model, temperature=temperature)
        elif provider == "groq":
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
