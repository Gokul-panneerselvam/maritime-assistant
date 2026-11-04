"""
Tests for the ingestion (message loader) LLM factory: Azure selection, settings and temperature handling,
and that the existing providers still work. No network calls: clients are only constructed.
"""

import pytest

from knowledge_graph.kg_loader.message_loader import llm_factory
from knowledge_graph.kg_loader.message_loader.llm_factory import get_chat_llm

ENV_KEYS = [
    "LLM_PROVIDER", "LLM_TEMPERATURE",
    "AZURE_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT",
    "AZURE_DEPLOYMENT_NAME", "AZURE_MODEL", "AZURE_MAX_TOKENS", "AZURE_TEMPERATURE", "MAX_TOKENS",
    "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_PROVIDER_NAME", "OPENROUTER_MAX_TOKENS",
    "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
]
ENDPOINT = "https://example-resource.services.ai.azure.com/openai/v1"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Importing the module loads the developer's real .env; start every test from a blank slate."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def azure_env(monkeypatch, deployment="my-deployment", **extra):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_DEPLOYMENT_NAME", deployment)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_azure_builds_client_from_settings(monkeypatch):
    azure_env(monkeypatch)
    llm = get_chat_llm()
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "my-deployment"
    assert llm.openai_api_base == ENDPOINT
    assert llm.max_tokens == 8192
    assert llm.temperature == 0.0


def test_azure_max_tokens_and_model_override(monkeypatch):
    azure_env(monkeypatch, AZURE_MAX_TOKENS="2048")
    llm = get_chat_llm(model="other-deployment")
    assert llm.model_name == "other-deployment"
    assert llm.max_tokens == 2048


@pytest.mark.parametrize("deployment", ["gpt-6-luna", "my-o3-mini", "Reasoning-X", "model-preview"])
def test_azure_omits_temperature_for_reasoning_deployments(monkeypatch, deployment):
    azure_env(monkeypatch, deployment=deployment)
    assert get_chat_llm().temperature is None


def test_azure_temperature_override(monkeypatch):
    azure_env(monkeypatch, AZURE_TEMPERATURE="0.3")
    assert get_chat_llm().temperature == pytest.approx(0.3)


@pytest.mark.parametrize("value", ["none", "OMIT", "null", "default"])
def test_azure_temperature_can_be_omitted(monkeypatch, value):
    azure_env(monkeypatch, AZURE_TEMPERATURE=value)
    assert get_chat_llm().temperature is None


def test_azure_alternate_variable_names(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_MODEL", "alt-deployment")
    assert get_chat_llm().model_name == "alt-deployment"


def test_azure_detected_from_key_when_no_provider_named(monkeypatch):
    # Same rule as the agent: an Azure key wins even if another provider's key is present.
    monkeypatch.setenv("AZURE_API_KEY", "k")
    monkeypatch.setenv("AZURE_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_DEPLOYMENT_NAME", "auto-deployment")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    llm = get_chat_llm()
    assert llm.model_name == "auto-deployment" and llm.openai_api_base == ENDPOINT


@pytest.mark.parametrize("missing", ["AZURE_API_KEY", "AZURE_ENDPOINT", "AZURE_DEPLOYMENT_NAME"])
def test_azure_incomplete_settings_raise_clear_error(monkeypatch, missing):
    azure_env(monkeypatch)
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match=missing):
        get_chat_llm()


def test_explicit_azure_does_not_fall_back_to_other_providers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")  # present, but Azure was asked for and is not configured
    with pytest.raises(ValueError, match="AZURE_API_KEY"):
        get_chat_llm()


def test_openrouter_still_works(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    llm = get_chat_llm()
    assert llm.openai_api_base == "https://openrouter.ai/api/v1"


def test_no_credentials_error_mentions_azure(monkeypatch):
    with pytest.raises(ValueError, match="AZURE_API_KEY"):
        get_chat_llm()
