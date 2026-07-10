"""FastAPI application exposing the recurrence engine over HTTP.

This is a thin, stateless boundary around the pure engine:

* Pydantic validates and documents the contract (OpenAPI at ``/docs``).
* slowapi applies per-client rate limiting.
* Because expansion is deterministic, identical requests yield identical
  responses, so a strong ETag is attached for conditional caching by clients
  and CDNs.

The engine works in calendar dates only. Time-of-day and timezone handling
belong here at the boundary: a caller localises the returned dates into
whatever timezone the task should fire in. Keeping that concern out of the
core is what makes the calendar math DST-proof and exhaustively testable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engine import get_occurrences
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .schemas import OccurrencesRequest, OccurrencesResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(
    title="Recurrence Engine API",
    version="1.0.0",
    summary="Expand recurrence rules into concrete, ordered task occurrences.",
    description=(
        "A deterministic HTTP wrapper around the recurrence engine. "
        "POST a rule and a query window; receive the ordered, de-duplicated "
        "occurrences inside that window."
    ),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# The bundled playground is same-origin and needs no CORS, but allowing any
# origin lets other clients call the API directly from a browser. Tighten to
# specific origins if the API should not be publicly consumable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["meta"], summary="Liveness probe")
def healthz() -> dict[str, str]:
    """Return a static OK payload for load balancers and uptime checks."""
    return {"status": "ok"}


@app.get("/info", tags=["meta"], summary="Service metadata")
def info() -> dict[str, Any]:
    return {
        "name": "recurrence-engine",
        "version": app.version,
        "docs": "/docs",
        "expand": {"method": "POST", "path": "/v1/occurrences"},
    }


def _etag(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'


@app.post(
    "/v1/occurrences",
    response_model=OccurrencesResponse,
    tags=["occurrences"],
    summary="Expand a recurrence rule within a window",
)
@limiter.limit("60/minute")
def expand_occurrences(request: Request, body: OccurrencesRequest, response: Response) -> Any:
    """Expand ``body.rule`` and return occurrences within the query window.

    The response carries a strong ``ETag`` and ``Cache-Control`` header:
    the same request always produces the same occurrences, so intermediaries
    and clients may cache aggressively.
    """
    rule = body.rule.to_domain()
    occurrences = get_occurrences(rule, body.window_start, body.window_end)
    payload = {
        "occurrences": [d.isoformat() for d in occurrences],
        "count": len(occurrences),
    }

    etag = _etag(payload)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=86400"
    return payload


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map engine-level validation errors to a structured 422 response.

    Pydantic rejects most malformed input before it reaches the engine; this
    is a defensive backstop for invariants only the engine can enforce.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# Serve the playground from the same origin as the API. Mounted last so the
# JSON API routes above always take precedence; the static mount only handles
# what they don't (/, /styles.css, /app.js). With one origin the browser needs
# no CORS and the client calls the API with a relative path.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="playground")
