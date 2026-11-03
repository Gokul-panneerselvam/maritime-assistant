"""
API Routes Package.
Exports authentication, chat, and system health routers.
"""

from .auth import router as auth_router
from .chat import router as chat_router
from .system import router as system_router

__all__ = ["auth_router", "chat_router", "system_router"]
