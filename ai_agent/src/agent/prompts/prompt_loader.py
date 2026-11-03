"""
Prompt Loader for Maritime Operations AI Agent.
Loads structured YAML prompts from prompts/agent_prompts.yaml.
"""

from pathlib import Path
from typing import Any, Dict
import yaml

PROMPTS_PATH = None
for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
    candidate = parent / "prompts" / "agent_prompts.yaml"
    if candidate.exists():
        PROMPTS_PATH = candidate.resolve()
        break

if PROMPTS_PATH is None:
    PROMPTS_PATH = (Path(__file__).resolve().parents[4] / "prompts" / "agent_prompts.yaml").resolve()

_agent_prompts_cache: Dict[str, Any] = {}


def load_agent_prompts(reload: bool = False) -> Dict[str, Any]:
    """Loads prompt templates from prompts/agent_prompts.yaml."""
    global _agent_prompts_cache
    if not _agent_prompts_cache or reload:
        if not PROMPTS_PATH.exists():
            raise FileNotFoundError(f"Agent prompts YAML file not found at: {PROMPTS_PATH}")
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            _agent_prompts_cache = yaml.safe_load(f)
    return _agent_prompts_cache


def get_agent_prompt(section: str) -> Dict[str, Any]:
    """Retrieves a specific prompt section (e.g. 'input_guardrail', 'entity_resolution')."""
    prompts = load_agent_prompts()
    if section not in prompts:
        raise KeyError(f"Prompt section '{section}' not found in {PROMPTS_PATH}")
    return prompts[section]

