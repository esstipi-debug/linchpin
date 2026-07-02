"""Per-client key auth for the mounted MCP server (``webapp/mcp_server.py``).

Distinct from ``webapp/security.py``'s ``require_api_key``: that gates the
operator's own dashboard/``POST /api/jobs`` with ONE shared secret
(``LINCHPIN_API_KEY``). The MCP surface sells access to multiple distinct
paying clients (Phase A go-to-market), each needing their own revocable
credential - so it is gated by ``src.mcp_keys.McpKeyStore`` instead.

Rate limiting is identity-aware, via ``security.rate_limit``'s existing
sliding-window logic (not a second limiter): a request with a VALID key is
throttled by its own resolved client_name (bucket key ``"mcp:" + client_name``),
never by source IP - so one paying client's usage can't throttle (or be
throttled by) an unrelated dashboard user or a different MCP client sharing an
egress IP (NAT, a corporate proxy, ...). Only requests that fail auth (missing
or invalid key) fall back to the default per-IP bucket, since there is no
client identity yet to key by. Sharing one IP-keyed bucket across every caller
on a paid, multi-tenant surface - the naive "always rate-limit before auth"
approach - was an audited gap: two legitimate, distinct, already-authenticated
clients behind the same IP would throttle each other.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.mcp_keys import McpKeyStore
from webapp import security


class McpKeyAuthMiddleware(BaseHTTPMiddleware):
    """Requires a valid, active ``X-API-Key`` (issued via ``McpKeyStore.issue``)
    on every request to the mounted MCP app. On success, stashes the resolved
    client name on ``request.state.mcp_client_name`` for downstream logging.

    Takes a zero-arg ``key_store_getter`` rather than a fixed ``McpKeyStore``
    instance - resolved fresh on every request, the same "module global read at
    call time" pattern ``webapp/security.py`` already uses, so tests can swap in
    an in-memory store via ``monkeypatch`` without rebuilding the whole app.
    """

    def __init__(self, app, key_store_getter: Callable[[], McpKeyStore]) -> None:
        super().__init__(app)
        self._key_store_getter = key_store_getter

    async def dispatch(self, request: Request, call_next):
        presented = request.headers.get("x-api-key", "")
        client_name = self._key_store_getter().validate(presented)
        rate_limit_key = f"mcp:{client_name}" if client_name is not None else None

        try:
            security.rate_limit(request, key=rate_limit_key)
        except HTTPException as exc:
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=dict(exc.headers or {}))

        if client_name is None:
            return JSONResponse({"error": "invalid or missing API key"}, status_code=401)

        request.state.mcp_client_name = client_name
        return await call_next(request)
