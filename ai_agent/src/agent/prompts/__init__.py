"""
Maritime Operations AI Agent Prompts Package.
Exports system instructions and YAML prompt loader.
"""
from ai_agent.src.agent.prompts.prompt_loader import (
    load_agent_prompts,
    get_agent_prompt,
)

__all__ = [
    "load_agent_prompts",
    "get_agent_prompt",
]
