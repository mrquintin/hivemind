"""WebSocket transport for Hivemind.

Provides real-time streaming of analysis progress and results.
"""

from app.ws.handlers import router

__all__ = ["router"]
