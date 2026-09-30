"""The two credential values and the one way they may be printed."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import TYPE_CHECKING, Self

from open_mammotion.exceptions import ContractError

if TYPE_CHECKING:
    from collections.abc import Mapping

_FINGERPRINT_CHARS = 12


def fingerprint(token: str) -> str:
    """A short, non-reversible handle for a token, safe for log lines.

    Two log lines with the same fingerprint carry the same token; that is all it says.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:_FINGERPRINT_CHARS]


@dataclass(frozen=True, repr=False)
class ClientCredentials:
    """The developer-portal client id and secret. The secret never appears in ``repr``."""

    client_id: str
    client_secret: str

    def __repr__(self) -> str:
        return f"ClientCredentials(client_id={self.client_id!r}, client_secret=<redacted>)"


@dataclass(frozen=True, repr=False)
class TokenSet:
    """An issued access token, when it expires, and the refresh token if one was issued.

    ``expires_at_s`` is absolute Unix seconds computed by the caller from ``expires_in`` and
    its own clock, so freshness checks need no clock of their own beyond ``now_s``.
    """

    access_token: str
    expires_at_s: float
    refresh_token: str | None = None
    token_type: str = "Bearer"  # noqa: S105 — a scheme name, not a credential

    def is_fresh(self, now_s: float, *, lead_s: float = 0.0) -> bool:
        """Whether the token is still valid ``lead_s`` seconds from ``now_s``."""
        return self.expires_at_s - lead_s > now_s

    def to_dict(self) -> dict[str, str | float | None]:
        """A JSON-safe form for the host to persist (D12). Contains the secrets; store accordingly."""
        return {
            "access_token": self.access_token,
            "expires_at_s": self.expires_at_s,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        """Rebuild from :meth:`to_dict` output.

        Raises:
            ContractError: A required key is missing or has the wrong type.

        """
        access_token = data.get("access_token")
        expires_at_s = data.get("expires_at_s")
        refresh_token = data.get("refresh_token")
        token_type = data.get("token_type", "Bearer")
        if not isinstance(access_token, str) or not access_token:
            raise ContractError("TokenSet", "access_token missing or not a string")
        if not isinstance(expires_at_s, int | float) or isinstance(expires_at_s, bool):
            raise ContractError("TokenSet", "expires_at_s missing or not a number")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ContractError("TokenSet", "refresh_token not a string")
        if not isinstance(token_type, str):
            raise ContractError("TokenSet", "token_type not a string")
        return cls(
            access_token=access_token,
            expires_at_s=float(expires_at_s),
            refresh_token=refresh_token,
            token_type=token_type,
        )

    def __repr__(self) -> str:
        return (
            f"TokenSet(access_token=<{fingerprint(self.access_token)}>, expires_at_s={self.expires_at_s!r}, "
            f"refresh_token={'<present>' if self.refresh_token else None}, token_type={self.token_type!r})"
        )
