"""Hosts, paths and timing constants; the only place a URL or a duration is spelled out.

The two base URLs read the environment so a fake server can stand in for the cloud
without patching (D11). Callers may still pass explicit URLs to the facade.
"""

from __future__ import annotations

import os

API_BASE_URL: str = os.environ.get("OPEN_MAMMOTION_API_URL", "https://api-open.mammotion.com")
AUTH_BASE_URL: str = os.environ.get("OPEN_MAMMOTION_AUTH_URL", "https://id.mammotion.com")

TOKEN_PATH = "/oauth2/token"  # noqa: S105 — a URL path, not a credential

DEFAULT_LANGUAGE = "en-US"

REQUEST_TIMEOUT_S = 30.0
TOKEN_REFRESH_LEAD_S = 300.0
DEFAULT_TOKEN_TTL_S = 3600.0
