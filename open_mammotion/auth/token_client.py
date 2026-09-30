"""The two grants of ``POST /oauth2/token`` and the mapping of their responses to a ``TokenSet``."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from mashumaro.exceptions import InvalidFieldValue, MissingField

from open_mammotion.auth.credentials import TokenSet, fingerprint
from open_mammotion.const import AUTH_BASE_URL, DEFAULT_TOKEN_TTL_S, REQUEST_TIMEOUT_S, TOKEN_PATH
from open_mammotion.exceptions import ContractError, GrantRejectedError, TransportError
from open_mammotion.models.common import Envelope, describe_decode_error
from open_mammotion.transport.session import is_transient_status

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from open_mammotion.auth.credentials import ClientCredentials
    from open_mammotion.transport.session import HttpResponse, HttpSession

_LOGGER = logging.getLogger(__name__)

_GRANT_CLIENT_CREDENTIALS = "client_credentials"
_GRANT_REFRESH_TOKEN = "refresh_token"  # noqa: S105 — a grant name, not a credential
_HEADERS: Mapping[str, str] = {"Accept": "application/json"}


class TokenClient:
    """Implements ``TokenGranter`` over an ``HttpSession``.

    A 4xx other than 408/429 whose body is a success envelope is still a rejection: the
    status is the only signal, so it becomes the ``GrantRejectedError`` code.
    """

    def __init__(
        self,
        session: HttpSession,
        *,
        auth_base_url: str = AUTH_BASE_URL,
        clock: Callable[[], float] = time.time,
        timeout_s: float = REQUEST_TIMEOUT_S,
    ) -> None:
        self._session = session
        self._url = f"{auth_base_url.rstrip('/')}{TOKEN_PATH}"
        self._clock = clock
        self._timeout_s = timeout_s

    async def grant_client_credentials(self, credentials: ClientCredentials) -> TokenSet:
        """Mint a token set from the client id and secret.

        Raises:
            GrantRejectedError: The endpoint answered a non-success envelope.
            TransportError: Network failure, 408/429/5xx, or a non-JSON body.
            ContractError: The body is not an envelope carrying an ``AccessTokenVo``.

        """
        return await self._grant(_GRANT_CLIENT_CREDENTIALS, credentials, {})

    async def grant_refresh_token(self, credentials: ClientCredentials, refresh_token: str) -> TokenSet:
        """Rotate a token set using its refresh token.

        Raises:
            GrantRejectedError: The refresh token was rejected.
            TransportError: Network failure, 408/429/5xx, or a non-JSON body.
            ContractError: The body is not an envelope carrying an ``AccessTokenVo``.

        """
        return await self._grant(_GRANT_REFRESH_TOKEN, credentials, {"refresh_token": refresh_token})

    async def _grant(self, grant_type: str, credentials: ClientCredentials, extra: Mapping[str, str]) -> TokenSet:
        form = {
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "grant_type": grant_type,
            **extra,
        }
        response = await self._session.request(
            "POST", self._url, headers=_HEADERS, form=form, timeout_s=self._timeout_s
        )
        envelope = self._decode_envelope(response)
        if not envelope.ok:
            raise GrantRejectedError(grant_type, envelope.code, envelope.msg)
        if response.status >= 400:
            raise GrantRejectedError(grant_type, response.status, envelope.msg)
        token = self._decode_token_set(envelope.data)
        _LOGGER.debug("Granted token %s via %s", fingerprint(token.access_token), grant_type)
        return token

    @staticmethod
    def _decode_envelope(response: HttpResponse) -> Envelope:
        if is_transient_status(response.status):
            raise TransportError(f"token endpoint answered HTTP {response.status}", status=response.status)
        try:
            body = response.json()
        except ValueError:
            raise TransportError(
                f"token endpoint answered a non-JSON body (HTTP {response.status})", status=response.status
            ) from None
        if not isinstance(body, dict):
            raise ContractError("Envelope", f"body is a {type(body).__name__}, not an object")
        try:
            return Envelope.from_dict(body)
        except (MissingField, InvalidFieldValue, TypeError, ValueError) as exc:
            raise ContractError("Envelope", describe_decode_error(exc)) from None

    def _decode_token_set(self, data: object) -> TokenSet:
        if not isinstance(data, dict):
            raise ContractError("TokenSet", "data is not an object")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token") or None
        token_type = data.get("token_type", "Bearer")
        expires_in = data.get("expires_in")
        if not isinstance(access_token, str) or not access_token:
            raise ContractError("TokenSet", "access_token missing or not a string")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ContractError("TokenSet", "refresh_token not a string")
        if not isinstance(token_type, str):
            raise ContractError("TokenSet", "token_type not a string")
        if expires_in is None:
            _LOGGER.debug("Token response has no expires_in; assuming %s s", DEFAULT_TOKEN_TTL_S)
            expires_in = DEFAULT_TOKEN_TTL_S
        elif not isinstance(expires_in, int | float) or isinstance(expires_in, bool):
            raise ContractError("TokenSet", "expires_in not a number")
        return TokenSet(
            access_token=access_token,
            expires_at_s=self._clock() + expires_in,
            refresh_token=refresh_token,
            token_type=token_type,
        )
