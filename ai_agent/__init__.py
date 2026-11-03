"""
Maritime AI Agent root package.
"""

import sys
from ai_agent.src import utilities, schemas, repo, api

sys.modules["ai_agent.utilities"] = utilities
sys.modules["ai_agent.utilities.logger"] = utilities.logger
sys.modules["ai_agent.schemas"] = schemas
sys.modules["ai_agent.schemas.epistemic"] = schemas.epistemic
sys.modules["ai_agent.repo"] = repo
sys.modules["ai_agent.repo.database"] = repo.database
sys.modules["ai_agent.api"] = api

__all__ = ["utilities", "schemas", "repo", "api"]
