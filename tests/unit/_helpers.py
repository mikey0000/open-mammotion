"""Builders shared by more than one unit-test package (docs/testing.md §2)."""

from __future__ import annotations

from open_mammotion.auth.credentials import TokenSet
from tests._helpers import ACCESS_TOKEN, REFRESH_TOKEN


def make_token_set(
    *,
    access_token: str = ACCESS_TOKEN,
    expires_at_s: float = 10_000.0,
    refresh_token: str | None = REFRESH_TOKEN,
) -> TokenSet:
    return TokenSet(access_token=access_token, expires_at_s=expires_at_s, refresh_token=refresh_token)
