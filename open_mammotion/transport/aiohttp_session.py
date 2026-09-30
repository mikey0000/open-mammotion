"""``AiohttpSession``: the ``HttpSession`` implementation over aiohttp."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import aiohttp
import orjson

from open_mammotion.exceptions import TransportError
from open_mammotion.transport.session import HttpResponse

if TYPE_CHECKING:
    from collections.abc import Mapping

    from open_mammotion.models.common import JsonObject

_TRANSPORT_FAILURES = (aiohttp.ClientError, TimeoutError, OSError)


class RequestKwargs(TypedDict, total=False):
    """Keyword arguments for ``aiohttp.ClientSession.request``."""

    headers: dict[str, str]
    data: bytes | dict[str, str]
    timeout: aiohttp.ClientTimeout


def build_request_kwargs(
    *,
    headers: Mapping[str, str] | None,
    json: JsonObject | None,
    form: Mapping[str, str] | None,
    timeout_s: float | None,
) -> RequestKwargs:
    """Translate ``HttpSession.request`` options into aiohttp keyword arguments.

    ``json`` is sent as orjson bytes with ``Content-Type: application/json``, replacing any
    caller content type; ``form`` is passed as ``data`` for aiohttp to URL-encode.

    Raises:
        ValueError: Both ``json`` and ``form`` were given.

    """
    if json is not None and form is not None:
        raise ValueError("json and form are mutually exclusive")
    kwargs = RequestKwargs(headers=dict(headers or {}))
    if json is not None:
        kwargs["headers"] = {k: v for k, v in kwargs["headers"].items() if k.lower() != "content-type"}
        kwargs["headers"]["Content-Type"] = "application/json"
        kwargs["data"] = orjson.dumps(json)
    elif form is not None:
        kwargs["data"] = dict(form)
    if timeout_s is not None:
        kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout_s)
    return kwargs


class AiohttpSession:
    """``HttpSession`` over an ``aiohttp.ClientSession``.

    Given a session, borrows it and never closes it (Constitution §4). Given none, creates
    one on the first request and owns it; after ``close()`` a later request creates a new one.
    """

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owned = session is None

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
            TransportError: The request could not complete; the message names only the
                exception type.
            ValueError: Both ``json`` and ``form`` were given (before any I/O).

        """
        kwargs = build_request_kwargs(headers=headers, json=json, form=form, timeout_s=timeout_s)
        session = self._client_session()
        try:
            async with session.request(method, url, **kwargs) as response:
                body = await response.read()
                return HttpResponse(
                    status=response.status,
                    headers={str(k): v for k, v in response.headers.items()},
                    body=body,
                )
        except _TRANSPORT_FAILURES as exc:
            # from None: a ClientResponseError carries request headers, Authorization included
            raise TransportError(f"{method} request failed: {type(exc).__name__}") from None

    async def close(self) -> None:
        """Close the session if this adapter created it; idempotent, a no-op when borrowed."""
        if self._owned and self._session is not None:
            session, self._session = self._session, None
            await session.close()

    def _client_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
