"""Tests for the mounted /mcp surface's auth gate (webapp/mcp_auth.py).

Covers only the auth boundary - the MCP protocol/tool behavior itself is
covered by tests/test_mcp_server.py against the FastMCP object directly (the
correct level for exercising tools/list, tools/call, and Pydantic validation).
Here we only need: no key -> 401, wrong key -> 401, valid key -> past the gate
(never a 401), and the existing rate limiter still applies underneath.
"""

import pytest

pytest.importorskip("fastapi")
try:
    import python_multipart  # noqa: F401
except ImportError:
    pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

import webapp.app as app_module  # noqa: E402
from src.mcp_keys import McpKeyStore  # noqa: E402
from webapp import security  # noqa: E402

client = TestClient(app_module.app)
_MCP_RPC_BODY = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _isolated_key_store(monkeypatch):
    """Every test gets its own in-memory key store - never touches a real key file,
    never leaks state between tests."""
    store = McpKeyStore(":memory:")
    monkeypatch.setattr(app_module, "_get_mcp_key_store", lambda: store)
    security.reset_rate_limit()
    monkeypatch.setattr(security, "RATE_LIMIT", 0)
    yield store


def test_missing_api_key_is_rejected():
    r = client.post("/mcp/", json=_MCP_RPC_BODY, headers=_MCP_HEADERS)
    assert r.status_code == 401
    assert "invalid or missing" in r.json()["error"]


def test_wrong_api_key_is_rejected(_isolated_key_store):
    _isolated_key_store.issue("Acme Co")  # some other client's key exists, irrelevant here

    r = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": "not-a-real-key"})

    assert r.status_code == 401


def test_revoked_api_key_is_rejected(_isolated_key_store):
    key = _isolated_key_store.issue("Acme Co")
    _isolated_key_store.revoke(key)

    r = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key})

    assert r.status_code == 401


def test_valid_api_key_passes_the_auth_gate(_isolated_key_store):
    key = _isolated_key_store.issue("Acme Co")

    r = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key})

    # The auth gate's only job is to not reject this - whatever the MCP protocol
    # layer does next (session handshake, etc.) is out of scope here.
    assert r.status_code != 401


def test_rate_limit_applies_even_with_a_valid_key(monkeypatch, _isolated_key_store):
    key = _isolated_key_store.issue("Acme Co")
    monkeypatch.setattr(security, "RATE_LIMIT", 1)
    monkeypatch.setattr(security, "RATE_WINDOW", 60)

    first = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key})
    second = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key})

    assert first.status_code != 429
    assert second.status_code == 429


def test_rate_limit_quota_is_per_client_not_per_shared_ip(monkeypatch, _isolated_key_store):
    """Repro of an audited gap: TestClient (like a NAT'd office, or two tenants
    behind one proxy) always presents the same source IP. Two DISTINCT clients
    must not throttle each other just because their traffic looks same-origin -
    each gets its own quota, keyed by their resolved client_name post-auth."""
    key_a = _isolated_key_store.issue("Acme Co")
    key_b = _isolated_key_store.issue("Globex")
    monkeypatch.setattr(security, "RATE_LIMIT", 1)
    monkeypatch.setattr(security, "RATE_WINDOW", 60)

    a_first = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key_a})
    b_first = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key_b})
    a_second = client.post("/mcp/", json=_MCP_RPC_BODY, headers={**_MCP_HEADERS, "X-API-Key": key_a})

    assert a_first.status_code != 429  # Acme's first call: fine
    assert b_first.status_code != 429  # Globex's first call: fine too, not throttled by Acme's usage
    assert a_second.status_code == 429  # Acme's OWN second call within the window: throttled
