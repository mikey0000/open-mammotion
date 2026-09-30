"""The one holder of an account's access token: freshness, the renewal order and the terminal flag."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from open_mammotion.auth.credentials import fingerprint
from open_mammotion.const import TOKEN_REFRESH_LEAD_S
from open_mammotion.exceptions import CredentialsRejectedError, GrantRejectedError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from open_mammotion.auth.credentials import ClientCredentials, TokenSet
    from open_mammotion.auth.protocols import TokenGranter

_LOGGER = logging.getLogger(__name__)


class TokenManager:
    """Implements ``TokenProvider``: hands out a fresh access token, renewing lazily (D6).

    Renewal is serialised behind one ``asyncio.Lock``, so concurrent callers holding a stale
    token share a single grant (D9). The order is refresh token, then client credentials
    (D7); a rejected client-credentials grant is terminal. ``TransportError`` from either
    grant propagates and changes no state.

    ``on_token_updated`` is awaited after every renewal so the host can persist the new
    ``TokenSet`` (D12). An exception it raises is logged and swallowed (D16): the renewal
    already succeeded, and a host's storage failure must not fail the request that needed it.
    """

    def __init__(
        self,
        credentials: ClientCredentials,
        granter: TokenGranter,
        *,
        clock: Callable[[], float] = time.time,
        lead_s: float = TOKEN_REFRESH_LEAD_S,
        initial: TokenSet | None = None,
        on_token_updated: Callable[[TokenSet], Awaitable[None]] | None = None,
    ) -> None:
        self._credentials = credentials
        self._granter = granter
        self._clock = clock
        self._lead_s = lead_s
        self._token = initial
        self._on_token_updated = on_token_updated
        self._invalidated = False
        self._rejected: str | None = None
        self._lock = asyncio.Lock()

    @property
    def token(self) -> TokenSet | None:
        """The held token set, for the host to persist; ``None`` before the first grant."""
        return self._token

    @property
    def credentials_rejected(self) -> str | None:
        """Why the client credentials were terminally rejected, or ``None`` if they were not."""
        return self._rejected

    async def ensure_token(self) -> TokenSet:
        """Return a token set fresh beyond the lead window, renewing if needed (see ``get_access_token``)."""
        await self.get_access_token()
        token = self._token
        assert token is not None  # noqa: S101 — get_access_token returned, so a token is held
        return token

    async def get_access_token(self) -> str:
        """Return an access token fresh beyond the lead window, renewing if needed.

        Raises:
            CredentialsRejectedError: The credentials are terminally rejected; no I/O is made.
            TransportError: Renewal was needed and the token endpoint was unavailable.

        """
        self._raise_if_rejected()
        if (token := self._fresh_token()) is not None:
            return token.access_token
        async with self._lock:
            self._raise_if_rejected()
            if (token := self._fresh_token()) is not None:
                return token.access_token
            return (await self._renew()).access_token

    def invalidate(self, stale_token: str) -> None:
        """Mark the held token dead if it is ``stale_token``; otherwise a no-op (D9).

        The token set is kept (its refresh token is still the first thing ``_renew`` tries);
        a flag makes the next ``get_access_token`` renew, and the next stored token clears it.
        """
        if self._token is not None and self._token.access_token == stale_token:
            self._invalidated = True

    def _raise_if_rejected(self) -> None:
        if self._rejected is not None:
            raise CredentialsRejectedError(self._rejected)

    def _fresh_token(self) -> TokenSet | None:
        token = self._token
        if token is None or self._invalidated or not token.is_fresh(self._clock(), lead_s=self._lead_s):
            return None
        return token

    async def _renew(self) -> TokenSet:
        if self._token is not None and (refresh_token := self._token.refresh_token):
            try:
                refreshed = await self._granter.grant_refresh_token(self._credentials, refresh_token)
            except GrantRejectedError as exc:
                _LOGGER.warning(
                    "Refresh token rejected (code=%s: %s); falling back to client credentials", exc.code, exc.msg
                )
            else:
                return await self._store(refreshed)
        try:
            granted = await self._granter.grant_client_credentials(self._credentials)
        except GrantRejectedError as exc:
            self._rejected = f"code={exc.code}: {exc.msg}"
            raise CredentialsRejectedError(self._rejected) from None
        return await self._store(granted)

    async def _store(self, token: TokenSet) -> TokenSet:
        self._token = token
        self._invalidated = False
        _LOGGER.info("Renewed access token %s (expires_at_s=%s)", fingerprint(token.access_token), token.expires_at_s)
        if self._on_token_updated is not None:
            try:
                await self._on_token_updated(token)
            except Exception as exc:  # noqa: BLE001 — D16: persistence must not fail a successful renewal
                _LOGGER.warning(
                    "on_token_updated raised %s; the renewed token is in use but was not persisted", type(exc).__name__
                )
        return token
