"""Vercel serverless entrypoint.

Vercel's Python runtime serves the ASGI ``app`` exposed here; the FastAPI
application handles every route, including the static playground it mounts.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable so ``api`` and ``engine`` resolve
# regardless of the runtime's working directory.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.main import app  # noqa: E402  (import after sys.path setup)

__all__ = ["app"]
