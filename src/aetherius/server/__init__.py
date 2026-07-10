"""The local daemon exposing Aetherius to any language over HTTP and WebSocket.

Import stays light (FastAPI/uvicorn are base dependencies): ``create_app`` builds the ASGI app and
``DaemonConfig`` carries its bind address and optional token. Nothing here pulls an Act extra.
"""

from __future__ import annotations

from .app import create_app
from .config import DaemonConfig

__all__ = ["create_app", "DaemonConfig"]
