"""Optional API-key authentication.

LeadForge is a single-user, self-hosted tool, so the local clone-and-run
experience must stay zero-config: no login, no token, no setup wizard. But
the moment the API port is reachable from a LAN (which the README explicitly
recommends), an unauthenticated API with ``CORS_ORIGINS="*"`` lets any
website on the internet delete the lead database and send cold email from
the user's mailbox.

The compromise: authentication is **off until a key is configured**.

    API_KEY=<anything>  -> every router except the mail tracker requires it
    API_KEY unset       -> unchanged local behaviour

The tracker (``/campaigns/tracker/*``) is deliberately exempt: it serves the
RFC 8058 one-click unsubscribe endpoint and the open-tracking pixel, which
are fetched by the recipient's mail client, not by the dashboard.
"""

import logging
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def auth_enabled() -> bool:
    """Whether the API key is actually being enforced."""
    return bool(settings.API_KEY) or bool(settings.REQUIRE_AUTH)


async def require_api_key(
    x_api_key: Optional[str] = Depends(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """FastAPI dependency enforcing the API key when one is configured."""
    if not auth_enabled():
        return

    expected = settings.API_KEY or ""
    if not expected:
        # REQUIRE_AUTH was set without a key - refuse everything rather than
        # silently serving an open API.
        logger.error("REQUIRE_AUTH is set but API_KEY is empty - refusing request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is required but no API_KEY is configured",
        )

    supplied = x_api_key or (bearer.credentials if bearer else "")
    if not supplied or not secrets.compare_digest(supplied, expected):
        logger.warning("rejected request with missing/invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
