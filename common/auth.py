"""Google ID tokens for calls to private Cloud Run services (config.SERVICE_AUTH)."""

import asyncio
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import google.auth.transport.requests
import google.oauth2.id_token
import httpx

from common import config


def _audience(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def _id_token(url: str) -> str:
    # Cached by google-auth until close to expiry; on Cloud Run it comes from the metadata server.
    return google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), _audience(url))


class IdTokenAuth(httpx.Auth):
    """Adds `Authorization: Bearer <ID token>` for the request's own host."""

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await asyncio.to_thread(_id_token, str(request.url))
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def a2a_http_client() -> httpx.AsyncClient | None:
    """HTTP client for RemoteA2aAgent (agent card fetch and JSON-RPC calls), or None to use ADK's default."""
    if not config.SERVICE_AUTH:
        return None
    return httpx.AsyncClient(auth=IdTokenAuth(), timeout=httpx.Timeout(config.A2A_TIMEOUT))


def mcp_headers(_context) -> dict[str, str]:
    """McpToolset header_provider: a fresh ID token for the MCP server."""
    return {"Authorization": f"Bearer {_id_token(config.MCP_SERVER_URL)}"}
