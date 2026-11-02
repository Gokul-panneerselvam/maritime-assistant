import os
from pathlib import Path
from typing import Any, Dict
import yaml

PROMPTS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "message_loader_prompts.yaml"

_prompts_cache: Dict[str, Any] = {}

def load_prompts(reload: bool = False) -> Dict[str, Any]:
    """Loads prompt templates from prompts/message_loader_prompts.yaml."""
    global _prompts_cache
    if not _prompts_cache or reload:
        if not PROMPTS_PATH.exists():
            raise FileNotFoundError(f"Prompts YAML file not found at: {PROMPTS_PATH}")
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            _prompts_cache = yaml.safe_load(f)
    return _prompts_cache

def get_prompt_template(section: str) -> Dict[str, str]:
    """Retrieves a specific prompt section (e.g. 'sender_resolution', 'entity_normalization')."""
    prompts = load_prompts()
    if section not in prompts:
        raise KeyError(f"Prompt section '{section}' not found in {PROMPTS_PATH}")
    return prompts[section]

