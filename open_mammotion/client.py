"""``OpenMammotion``: the facade that wires one credential to every API group.

Composition only. Behaviour lives in the layers below; this module decides which
concrete classes plug into which protocols and owns their lifetime.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Self

import aiohttp

from open_mammotion.api.actions import ActionsApi
from open_mammotion.api.devices import DevicesApi
from open_mammotion.api.faults import FaultsApi
from open_mammotion.api.local_network import LocalNetworkApi
from open_mammotion.api.work_reports import WorkReportsApi
from open_mammotion.auth.token_client import TokenClient
from open_mammotion.auth.token_manager import TokenManager
from open_mammotion.const import API_BASE_URL, AUTH_BASE_URL, DEFAULT_LANGUAGE, REQUEST_TIMEOUT_S
from open_mammotion.transport.aiohttp_session import AiohttpSession
from open_mammotion.transport.api import ApiTransport

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from open_mammotion.auth.credentials import ClientCredentials, TokenSet
    from open_mammotion.transport.session import HttpSession


class OpenMammotion:
    """One developer credential, one token manager, one transport, every API group.

    Use as an async context manager, or call :meth:`close` yourself. An
    ``aiohttp.ClientSession`` the host passes in is borrowed and never closed; an
    ``HttpSession`` implementation the host passes in decides for itself what its
    ``close`` releases; a session the facade creates is closed on :meth:`close`.

    Attributes:
        devices: ``GET /v1/mowers`` and ``GET /v1/mower/{deviceId}``.
        actions: work actions, current work parameters, task list.
        work_reports: summary, search, detail.
        faults: the per-device fault history.
        local_network: HA local-network configuration and the LAN WebSocket ticket.

    A terminal credential rejection (``credentials_rejected``) is cleared only by
    building a new facade with new credentials.

    Args:
        credentials: The developer-portal client id and secret.
        session: An ``aiohttp.ClientSession`` to borrow, any ``HttpSession``
            implementation, or ``None`` to create and own an ``AiohttpSession``.
        language: Sent as ``Accept-Language`` on every API call (Q11).
        tokens: A previously persisted :class:`TokenSet` to resume with.
        on_token_updated: Awaited with each newly issued :class:`TokenSet` so the
            host can persist it (D12).
        clock: Unix-seconds clock, injectable for tests.
        api_url: Override the API base URL (D11).
        auth_url: Override the token endpoint base URL (D11).
        timeout_s: Per-request timeout.

    """

    def __init__(  # noqa: PLR0913 — the facade's keyword-only options are its whole configuration surface
        self,
        credentials: ClientCredentials,
        *,
        session: aiohttp.ClientSession | HttpSession | None = None,
        language: str = DEFAULT_LANGUAGE,
        tokens: TokenSet | None = None,
        on_token_updated: Callable[[TokenSet], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.time,
        api_url: str = API_BASE_URL,
        auth_url: str = AUTH_BASE_URL,
        timeout_s: float = REQUEST_TIMEOUT_S,
    ) -> None:
        self._http: HttpSession = (
            AiohttpSession(session) if session is None or isinstance(session, aiohttp.ClientSession) else session
        )
        self._tokens = TokenManager(
            credentials,
            TokenClient(self._http, auth_base_url=auth_url, clock=clock, timeout_s=timeout_s),
            clock=clock,
            initial=tokens,
            on_token_updated=on_token_updated,
        )
        transport = ApiTransport(self._http, self._tokens, api_base_url=api_url, language=language, timeout_s=timeout_s)
        self.devices = DevicesApi(transport)
        self.actions = ActionsApi(transport)
        self.work_reports = WorkReportsApi(transport)
        self.faults = FaultsApi(transport)
        self.local_network = LocalNetworkApi(transport, clock=clock)

    @property
    def token(self) -> TokenSet | None:
        """The token set currently held, if any."""
        return self._tokens.token

    @property
    def credentials_rejected(self) -> str | None:
        """Why the credential is terminally rejected, or ``None`` while it is usable."""
        return self._tokens.credentials_rejected

    async def authenticate(self) -> TokenSet:
        """Obtain a token now rather than on the first API call.

        A host's setup or validation step uses this to fail early.

        Raises:
            CredentialsRejectedError: The client id/secret was rejected.
            TransportError: The token endpoint was unreachable.

        """
        return await self._tokens.ensure_token()

    async def close(self) -> None:
        """Release the HTTP session if this facade created it."""
        await self._http.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
