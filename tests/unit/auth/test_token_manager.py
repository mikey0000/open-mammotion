from __future__ import annotations

import asyncio
from collections import deque
import logging
from typing import TYPE_CHECKING

import pytest

from open_mammotion.auth.token_manager import TokenManager
from open_mammotion.exceptions import CredentialsRejectedError, GrantRejectedError, TransportError
from tests._helpers import CREDENTIALS
from tests.unit._fakes import FakeTokenClient
from tests.unit._helpers import make_token_set

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from open_mammotion.auth.credentials import TokenSet
    from tests.unit._fakes import Outcome

NOW_S = 1_000.0
LEAD_S = 300.0


def make_granter(
    *,
    client_credentials: Iterable[Outcome[TokenSet]] = (),
    refresh: Iterable[Outcome[TokenSet]] = (),
) -> FakeTokenClient:
    return FakeTokenClient(client_credentials=deque(client_credentials), refresh=deque(refresh))


def make_manager(
    granter: FakeTokenClient,
    *,
    initial: TokenSet | None = None,
    clock: Callable[[], float] = lambda: NOW_S,
    on_token_updated: Callable[[TokenSet], Awaitable[None]] | None = None,
) -> TokenManager:
    return TokenManager(
        CREDENTIALS, granter, clock=clock, lead_s=LEAD_S, initial=initial, on_token_updated=on_token_updated
    )


def fresh_token(access_token: str = "access-token-1", *, refresh_token: str | None = "refresh-token-1") -> TokenSet:
    return make_token_set(access_token=access_token, expires_at_s=NOW_S + 3600, refresh_token=refresh_token)


def stale_token(access_token: str = "access-token-old", *, refresh_token: str | None = "refresh-token-old") -> TokenSet:
    return make_token_set(access_token=access_token, expires_at_s=NOW_S + LEAD_S - 1, refresh_token=refresh_token)


class TestFreshToken:
    async def test_returns_the_held_fresh_token_without_a_grant(self) -> None:
        granter = make_granter()
        manager = make_manager(granter, initial=fresh_token("access-token-held"))

        token = await manager.get_access_token()

        assert token == "access-token-held"
        assert granter.calls == []

    async def test_initial_seeds_the_held_token(self) -> None:
        seed = fresh_token("access-token-seed")

        manager = make_manager(make_granter(), initial=seed)

        assert manager.token == seed

    async def test_starts_with_no_token_and_no_terminal_reason(self) -> None:
        manager = make_manager(make_granter())

        assert manager.token is None
        assert manager.credentials_rejected is None


class TestRenewal:
    async def test_grants_client_credentials_when_no_token_is_held(self) -> None:
        granter = make_granter(client_credentials=[fresh_token("access-token-new")])
        manager = make_manager(granter)

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["client_credentials"]

    async def test_renews_a_token_inside_the_lead_window(self) -> None:
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=stale_token())

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["refresh_token"]

    async def test_renews_once_the_clock_enters_the_lead_window(self) -> None:
        now_s = [NOW_S]
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=make_token_set(expires_at_s=NOW_S + 1_000), clock=lambda: now_s[0])
        assert await manager.get_access_token() == "access-token-1"

        now_s[0] = NOW_S + 1_000 - LEAD_S

        assert await manager.get_access_token() == "access-token-new"

    async def test_tries_the_refresh_grant_with_the_held_refresh_token_first(self) -> None:
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=stale_token(refresh_token="refresh-token-old"))

        await manager.get_access_token()

        assert granter.seen_refresh_tokens == ["refresh-token-old"]

    async def test_uses_client_credentials_when_the_held_token_has_no_refresh_token(self) -> None:
        granter = make_granter(client_credentials=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=stale_token(refresh_token=None))

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["client_credentials"]

    async def test_falls_back_to_client_credentials_when_the_refresh_is_rejected(self) -> None:
        granter = make_granter(
            refresh=[GrantRejectedError("refresh_token", 40102, "expired")],
            client_credentials=[fresh_token("access-token-new")],
        )
        manager = make_manager(granter, initial=stale_token())

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["refresh_token", "client_credentials"]

    async def test_logs_a_warning_when_the_refresh_is_rejected(self, caplog: pytest.LogCaptureFixture) -> None:
        granter = make_granter(
            refresh=[GrantRejectedError("refresh_token", 40102, "expired")],
            client_credentials=[fresh_token()],
        )
        manager = make_manager(granter, initial=stale_token())

        await manager.get_access_token()

        assert any(r.levelno == logging.WARNING and "40102" in r.getMessage() for r in caplog.records)

    async def test_stores_the_renewed_token(self) -> None:
        renewed = fresh_token("access-token-new")
        manager = make_manager(make_granter(client_credentials=[renewed]))

        await manager.get_access_token()

        assert manager.token == renewed

    async def test_never_logs_a_token(self, caplog: pytest.LogCaptureFixture) -> None:
        manager = make_manager(make_granter(refresh=[fresh_token("access-token-new")]), initial=stale_token())

        await manager.get_access_token()

        assert "access-token-new" not in caplog.text
        assert "refresh-token-old" not in caplog.text


class TestCredentialsRejected:
    async def test_raises_credentials_rejected_when_client_credentials_are_rejected(self) -> None:
        granter = make_granter(client_credentials=[GrantRejectedError("client_credentials", 40101, "bad client")])
        manager = make_manager(granter)

        with pytest.raises(CredentialsRejectedError) as exc_info:
            await manager.get_access_token()

        assert "40101" in exc_info.value.reason
        assert "bad client" in exc_info.value.reason
        assert CREDENTIALS.client_secret not in str(exc_info.value)

    async def test_records_the_terminal_reason(self) -> None:
        granter = make_granter(client_credentials=[GrantRejectedError("client_credentials", 40101, "bad client")])
        manager = make_manager(granter)

        with pytest.raises(CredentialsRejectedError):
            await manager.get_access_token()

        assert manager.credentials_rejected is not None
        assert "40101" in manager.credentials_rejected

    async def test_refuses_every_later_call_without_a_grant(self) -> None:
        granter = make_granter(client_credentials=[GrantRejectedError("client_credentials", 40101, "bad client")])
        manager = make_manager(granter)
        with pytest.raises(CredentialsRejectedError):
            await manager.get_access_token()
        granter.calls.clear()

        with pytest.raises(CredentialsRejectedError):
            await manager.get_access_token()

        assert granter.calls == []

    async def test_becomes_terminal_after_both_grants_are_rejected(self) -> None:
        granter = make_granter(
            refresh=[GrantRejectedError("refresh_token", 40102, "expired")],
            client_credentials=[GrantRejectedError("client_credentials", 40101, "bad client")],
        )
        manager = make_manager(granter, initial=stale_token())

        with pytest.raises(CredentialsRejectedError):
            await manager.get_access_token()

        assert granter.calls == ["refresh_token", "client_credentials"]
        assert manager.credentials_rejected is not None


class TestTransportFailure:
    async def test_propagates_a_transport_error_from_the_refresh_grant(self) -> None:
        held = stale_token()
        manager = make_manager(make_granter(refresh=[TransportError("down", status=503)]), initial=held)

        with pytest.raises(TransportError):
            await manager.get_access_token()

        assert manager.token == held
        assert manager.credentials_rejected is None

    async def test_propagates_a_transport_error_from_the_client_credentials_grant(self) -> None:
        held = stale_token()
        granter = make_granter(
            refresh=[GrantRejectedError("refresh_token", 40102, "expired")],
            client_credentials=[TransportError("down", status=503)],
        )
        manager = make_manager(granter, initial=held)

        with pytest.raises(TransportError):
            await manager.get_access_token()

        assert manager.token == held
        assert manager.credentials_rejected is None

    async def test_retries_the_grant_on_the_next_call_after_a_transport_error(self) -> None:
        granter = make_granter(client_credentials=[TransportError("down"), fresh_token("access-token-new")])
        manager = make_manager(granter)
        with pytest.raises(TransportError):
            await manager.get_access_token()

        token = await manager.get_access_token()

        assert token == "access-token-new"


class TestInvalidate:
    async def test_invalidating_the_current_token_forces_a_renewal(self) -> None:
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=fresh_token("access-token-held"))

        manager.invalidate("access-token-held")
        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["refresh_token"]

    async def test_invalidating_a_token_that_is_not_current_is_a_no_op(self) -> None:
        granter = make_granter()
        manager = make_manager(granter, initial=fresh_token("access-token-held"))

        manager.invalidate("access-token-rotated-away")
        token = await manager.get_access_token()

        assert token == "access-token-held"
        assert granter.calls == []

    async def test_invalidating_with_no_token_held_is_a_no_op(self) -> None:
        manager = make_manager(make_granter())

        manager.invalidate("access-token-held")

        assert manager.token is None

    async def test_the_renewed_token_is_not_treated_as_invalidated(self) -> None:
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        manager = make_manager(granter, initial=fresh_token("access-token-held"))
        manager.invalidate("access-token-held")
        await manager.get_access_token()

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert granter.calls == ["refresh_token"]


class TestConcurrency:
    async def test_shares_one_renewal_across_concurrent_callers(self) -> None:
        granter = make_granter(client_credentials=[fresh_token("access-token-new")])
        granter.gate = asyncio.Event()
        manager = make_manager(granter)

        tasks = [asyncio.create_task(manager.get_access_token()) for _ in range(5)]
        await asyncio.sleep(0)
        granter.gate.set()
        tokens = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert set(tokens) == {"access-token-new"}
        assert granter.calls == ["client_credentials"]

    async def test_concurrent_invalidations_of_one_token_share_one_renewal(self) -> None:
        granter = make_granter(refresh=[fresh_token("access-token-new")])
        granter.gate = asyncio.Event()
        manager = make_manager(granter, initial=fresh_token("access-token-dead"))
        for _ in range(5):
            manager.invalidate("access-token-dead")

        tasks = [asyncio.create_task(manager.get_access_token()) for _ in range(5)]
        await asyncio.sleep(0)
        manager.invalidate("access-token-dead")
        granter.gate.set()
        tokens = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert set(tokens) == {"access-token-new"}
        assert granter.calls == ["refresh_token"]

    async def test_waiting_callers_fail_fast_once_the_first_is_rejected(self) -> None:
        granter = make_granter(client_credentials=[GrantRejectedError("client_credentials", 40101, "bad client")])
        granter.gate = asyncio.Event()
        manager = make_manager(granter)

        tasks = [asyncio.create_task(manager.get_access_token()) for _ in range(3)]
        await asyncio.sleep(0)
        granter.gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)

        assert all(isinstance(r, CredentialsRejectedError) for r in results)
        assert granter.calls == ["client_credentials"]


class TestOnTokenUpdated:
    async def test_awaits_the_callback_with_the_new_token_set(self) -> None:
        renewed = fresh_token("access-token-new")
        seen: list[TokenSet] = []

        async def on_token_updated(token: TokenSet) -> None:
            seen.append(token)

        manager = make_manager(make_granter(client_credentials=[renewed]), on_token_updated=on_token_updated)

        await manager.get_access_token()

        assert seen == [renewed]

    async def test_is_not_called_when_the_held_token_is_fresh(self) -> None:
        seen: list[TokenSet] = []

        async def on_token_updated(token: TokenSet) -> None:
            seen.append(token)

        manager = make_manager(make_granter(), initial=fresh_token(), on_token_updated=on_token_updated)

        await manager.get_access_token()

        assert seen == []

    async def test_a_raising_callback_does_not_fail_the_renewal(self) -> None:
        async def on_token_updated(token: TokenSet) -> None:
            raise OSError("disk full")

        manager = make_manager(
            make_granter(client_credentials=[fresh_token("access-token-new")]), on_token_updated=on_token_updated
        )

        token = await manager.get_access_token()

        assert token == "access-token-new"
        assert manager.token is not None
        assert manager.token.access_token == "access-token-new"

    async def test_a_raising_callback_is_logged_as_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        async def on_token_updated(token: TokenSet) -> None:
            raise OSError("disk full")

        manager = make_manager(
            make_granter(client_credentials=[fresh_token("access-token-new")]), on_token_updated=on_token_updated
        )

        await manager.get_access_token()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("OSError" in r.getMessage() for r in warnings)
        assert "access-token-new" not in caplog.text
