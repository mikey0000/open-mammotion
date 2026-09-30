"""The ``HttpSession`` seam: what the library needs from an HTTP client, and nothing more.

An implementation (``aiohttp_session.py``) raises ``TransportError`` for connection-level
failures and never raises for an HTTP status; status handling is ``api.py``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import orjson

if TYPE_CHECKING:
    from collections.abc import Mapping

    from open_mammotion.models.common import JsonObject, JsonValue


#: Statuses that mean "try again later" whatever the body carries (architecture §2.3).
TRANSIENT_STATUSES: frozenset[int] = frozenset({408, 429})


def is_transient_status(status: int) -> bool:
    """Whether ``status`` is a transient failure: 408, 429 or any 5xx."""
    return status in TRANSIENT_STATUSES or status >= 500


@dataclass(frozen=True)
class HttpResponse:
    """A completed HTTP exchange: status, headers and the raw body."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def content_type(self) -> str:
        """The ``Content-Type`` header's media type, lower-cased, without parameters."""
        raw = next((v for k, v in self.headers.items() if k.lower() == "content-type"), "")
        return raw.split(";", 1)[0].strip().lower()

    def json(self) -> JsonValue:
        """Decode the body as JSON.

        Raises:
            orjson.JSONDecodeError: The body is not valid JSON (a ``ValueError``).

        """
        return orjson.loads(self.body)


class HttpSession(Protocol):
    """An asynchronous HTTP client the library can drive.

    Exactly one of ``json`` and ``form`` may be given; ``form`` is sent as
    ``application/x-www-form-urlencoded`` (the token endpoint), ``json`` as
    ``application/json`` (everything else).
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: JsonObject | None = None,
        form: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse:
        """Send one request and return the response whatever its status.

        Raises:
            TransportError: The request could not complete (DNS, connect, TLS, timeout,
                connection reset).

        """
        ...

    async def close(self) -> None:
        """Release resources the session created itself; a no-op for a borrowed session."""
        ...
