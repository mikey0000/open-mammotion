"""The two seams of the auth layer: who mints tokens, and who hands them out."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from open_mammotion.auth.credentials import ClientCredentials, TokenSet


class TokenGranter(Protocol):
    """Performs the two grants ``POST /oauth2/token`` offers (``docs/api/authentication.md``)."""

    async def grant_client_credentials(self, credentials: ClientCredentials) -> TokenSet:
        """Mint a token set from the client id and secret.

        Raises:
            GrantRejectedError: The endpoint answered a non-success envelope.
            TransportError: The endpoint was unreachable or unavailable.

        """
        ...

    async def grant_refresh_token(self, credentials: ClientCredentials, refresh_token: str) -> TokenSet:
        """Rotate a token set using its refresh token.

        Raises:
            GrantRejectedError: The refresh token was rejected.
            TransportError: The endpoint was unreachable or unavailable.

        """
        ...


class TokenProvider(Protocol):
    """Hands the transport a usable access token and accepts word that one is dead."""

    async def get_access_token(self) -> str:
        """Return an access token that is fresh beyond the lead window, renewing if needed.

        Raises:
            CredentialsRejectedError: The credential is terminally rejected (no I/O is made).
            TransportError: Renewal was needed and the token endpoint was unavailable.

        """
        ...

    def invalidate(self, stale_token: str) -> None:
        """Mark ``stale_token`` dead so the next ``get_access_token`` renews.

        A no-op when ``stale_token`` is not the token currently held: someone else has
        already rotated it, and the caller should simply retry (D9).
        """
        ...
