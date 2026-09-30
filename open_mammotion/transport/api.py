"""``ApiTransport``: the authenticated ``Requester`` — headers, the single 401 retry, status and envelope mapping."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import logging
from typing import TYPE_CHECKING

from mashumaro.exceptions import InvalidFieldValue, MissingField

from open_mammotion.const import API_BASE_URL, DEFAULT_LANGUAGE, REQUEST_TIMEOUT_S
from open_mammotion.exceptions import ApiError, ContractError, TransportError, UnauthorizedError
from open_mammotion.models.common import Envelope, describe_decode_error
from open_mammotion.transport.session import is_transient_status

if TYPE_CHECKING:
    from open_mammotion.auth.protocols import TokenProvider
    from open_mammotion.models.common import JsonObject, JsonValue
    from open_mammotion.transport.session import HttpResponse, HttpSession

_LOGGER = logging.getLogger(__name__)

_ENVELOPE_DECODE_ERRORS = (MissingField, InvalidFieldValue, TypeError, ValueError)


class _NotJson:
    """Marker for a body that did not parse as JSON."""


_NOT_JSON = _NotJson()


@dataclass(frozen=True)
class _Exchange:
    token: str
    status: int
    body: JsonValue | _NotJson


class ApiTransport:
    """``Requester`` over an ``HttpSession`` and a ``TokenProvider`` (``docs/architecture.md`` §2.1)."""

    def __init__(
        self,
        session: HttpSession,
        tokens: TokenProvider,
        *,
        api_base_url: str = API_BASE_URL,
        language: str = DEFAULT_LANGUAGE,
        timeout_s: float = REQUEST_TIMEOUT_S,
    ) -> None:
        self._session = session
        self._tokens = tokens
        self._base_url = api_base_url.rstrip("/")
        self._language = language
        self._timeout_s = timeout_s

    async def request(self, method: str, path: str, *, json: JsonObject | None = None) -> Envelope:
        """Call ``path`` (relative to the API base URL) and return its success envelope.

        A 401 invalidates the token that was sent and retries exactly once (D9).

        Raises:
            TransportError: Network failure, timeout, 408, 429, 5xx, or a non-JSON 2xx body.
            UnauthorizedError: 401 on the retry as well.
            CredentialsRejectedError: From the token provider, untouched.
            ApiError: A non-success envelope, or a non-JSON 4xx.
            ContractError: The body was JSON but not an envelope.

        """
        exchange = await self._send(method, path, json)
        if exchange.status == HTTPStatus.UNAUTHORIZED:
            self._tokens.invalidate(exchange.token)
            exchange = await self._send(method, path, json)
            if exchange.status == HTTPStatus.UNAUTHORIZED:
                raise UnauthorizedError(path)
        return self._to_envelope(path, exchange)

    async def _send(self, method: str, path: str, json: JsonObject | None) -> _Exchange:
        token = await self._tokens.get_access_token()
        response = await self._session.request(
            method,
            f"{self._base_url}/{path.lstrip('/')}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Language": self._language,
                "Accept": "application/json",
            },
            json=json,
            timeout_s=self._timeout_s,
        )
        body = _parse(response)
        request_id = body.get("requestId") if isinstance(body, dict) else None
        _LOGGER.debug("%s %s -> %s (requestId=%s)", method, path, response.status, request_id)
        return _Exchange(token, response.status, body)

    def _to_envelope(self, path: str, exchange: _Exchange) -> Envelope:
        status, body = exchange.status, exchange.body
        self._raise_for_status(status)
        if isinstance(body, _NotJson):
            if HTTPStatus.BAD_REQUEST <= status < HTTPStatus.INTERNAL_SERVER_ERROR:
                raise ApiError(status, f"HTTP {status} without an envelope", path=path)
            raise TransportError(f"{path}: non-JSON body with HTTP {status}", status=status)
        if not isinstance(body, dict):
            raise ContractError("Envelope", f"{path}: expected a JSON object, got {type(body).__name__}")
        try:
            envelope = Envelope.from_dict(body)
        except _ENVELOPE_DECODE_ERRORS as exc:
            raise ContractError("Envelope", f"{path}: {describe_decode_error(exc)}") from None
        self._raise_for_envelope(path, status, envelope)
        return envelope

    @staticmethod
    def _raise_for_status(status: int) -> None:
        """Raise ``TransportError`` for the statuses that mean "try again later", whatever the body."""
        if is_transient_status(status):
            raise TransportError(f"server unavailable: HTTP {status}", status=status)

    @staticmethod
    def _raise_for_envelope(path: str, status: int, envelope: Envelope) -> None:
        """Raise ``ApiError`` for a non-success envelope, or a success envelope on an HTTP 4xx."""
        if status >= HTTPStatus.BAD_REQUEST:
            code = envelope.code if not envelope.ok else status
            raise ApiError(code, envelope.msg or f"HTTP {status}", request_id=envelope.request_id, path=path)
        if not envelope.ok:
            raise ApiError(envelope.code, envelope.msg, request_id=envelope.request_id, path=path)


def _parse(response: HttpResponse) -> JsonValue | _NotJson:
    try:
        return response.json()
    except ValueError:
        return _NOT_JSON
