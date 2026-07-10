"""Vercel serverless entrypoint.

Vercel's Python runtime serves the ASGI ``app`` exposed here; the FastAPI
application handles every route, including the static playground it mounts.
"""

from __future__ import annotations

from api.main import app

__all__ = ["app"]
