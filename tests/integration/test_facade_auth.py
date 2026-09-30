"""The facade's credential lifecycle end to end: grants, reuse, lead-window refresh, 401 recovery, terminal rejection.

Assertions read the fake's own counters and request log, never the facade's internals.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from open_mammotion import CredentialsRejectedError, TokenSet
from tests.fakeserver.state import YUKA_ID
from tests.integration._fakeserver_client import bounded
from tests.integration._helpers import (
    INTO_LEAD_WINDOW_S,
    MOWERS,
    TOKEN,
    TOKEN_TTL_S,
    facade,
    grant_types,
    requests_since,
    secrets_in_text,
)

if TYPE_CHECKING:
    from open_mammotion import OpenMammotion
    from tests.fakeserver.clock import ManualClock
    from tests.fakeserver.server import FakeCloud

BURST = 5


class TestFirstCall:
    async def test_performs_one_client_credentials_grant_then_the_api_call(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.devices.list())

        assert requests_since(fake_cloud, 0) == [TOKEN, MOWERS]
        assert (await bounded(fake_cloud.control()))["token_grants"] == {"client_credentials": 1, "refresh_token": 0}

    async def test_second_call_reuses_the_token_without_a_grant(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.devices.list())
        start = fake_cloud.state.requests_total

        await bounded(api.devices.list())

        assert requests_since(fake_cloud, start) == [MOWERS]


class TestAuthenticate:
    async def test_obtains_the_token_before_any_api_call(self, api: OpenMammotion, fake_cloud: FakeCloud) -> None:
        token = await bounded(api.authenticate())

        assert requests_since(fake_cloud, 0) == [TOKEN]
        assert token == api.token
        assert token.access_token in fake_cloud.state.tokens


class TestLeadWindowRefresh:
    async def test_refreshes_with_the_refresh_token_once_inside_the_lead_window(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        await bounded(api.authenticate())
        fake_clock.advance(INTO_LEAD_WINDOW_S)

        await bounded(api.devices.list())

        assert grant_types(fake_cloud) == ["client_credentials", "refresh_token"]
        assert (await bounded(fake_cloud.control()))["token_grants"] == {"client_credentials": 1, "refresh_token": 1}

    async def test_does_not_refresh_just_outside_the_lead_window(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        await bounded(api.authenticate())
        fake_clock.advance(INTO_LEAD_WINDOW_S - 2)

        await bounded(api.devices.list())

        assert grant_types(fake_cloud) == ["client_credentials"]

    async def test_falls_back_to_client_credentials_when_the_refresh_is_rejected(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(reject_next_refresh=True))
        fake_clock.advance(INTO_LEAD_WINDOW_S)

        devices = await bounded(api.devices.list())

        assert grant_types(fake_cloud) == ["client_credentials", "refresh_token", "client_credentials"]
        assert len(devices) == 2
        assert api.credentials_rejected is None


class TestExpiredTokenRecovery:
    async def test_refreshes_after_one_401_and_retries_exactly_once(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(expire_tokens=True))
        start = fake_cloud.state.requests_total

        devices = await bounded(api.devices.list())

        assert requests_since(fake_cloud, start) == [MOWERS, TOKEN, MOWERS]
        assert grant_types(fake_cloud, start) == ["refresh_token"]
        assert len(devices) == 2

    async def test_concurrent_callers_on_one_dead_token_share_a_single_grant(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        """D9 end to end: a burst that all 401 on the same token produces one refresh, not one each."""
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(expire_tokens=True))
        start = fake_cloud.state.requests_total

        details = await bounded(asyncio.gather(*(api.devices.get(YUKA_ID) for _ in range(BURST))))

        assert [d.device_id for d in details] == [YUKA_ID] * BURST
        assert requests_since(fake_cloud, start).count(("GET", f"/v1/mower/{YUKA_ID}")) == 2 * BURST
        assert grant_types(fake_cloud, start) == ["refresh_token"]
        assert (await bounded(fake_cloud.control()))["token_grants"] == {"client_credentials": 1, "refresh_token": 1}


class TestRejectedClientCredentials:
    async def test_raises_credentials_rejected_and_sets_the_terminal_flag(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(fake_cloud.control(reject_client_credentials=True))

        with pytest.raises(CredentialsRejectedError) as caught:
            await bounded(api.devices.list())

        assert api.credentials_rejected is not None
        assert "40101" in api.credentials_rejected
        assert not secrets_in_text(str(caught.value), fake_cloud)

    async def test_a_later_call_fails_fast_without_any_request(self, api: OpenMammotion, fake_cloud: FakeCloud) -> None:
        await bounded(fake_cloud.control(reject_client_credentials=True))
        with pytest.raises(CredentialsRejectedError):
            await bounded(api.devices.list())
        start = fake_cloud.state.requests_total

        with pytest.raises(CredentialsRejectedError):
            await bounded(api.devices.get(YUKA_ID))

        assert requests_since(fake_cloud, start) == []


class TestTokenPersistence:
    async def test_on_token_updated_receives_every_issued_token_set(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        seen: list[TokenSet] = []

        async def record(token: TokenSet) -> None:
            seen.append(token)

        async with facade(fake_cloud, clock=fake_clock, on_token_updated=record) as client:
            await bounded(client.authenticate())
            fake_clock.advance(INTO_LEAD_WINDOW_S)
            await bounded(client.devices.list())

            assert len(seen) == 2
            assert seen[-1] == client.token
        assert [t.access_token for t in seen] == list(fake_cloud.state.tokens)

    async def test_a_resumed_token_set_serves_calls_without_a_grant(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        persisted = (await bounded(api.authenticate())).to_dict()
        start = fake_cloud.state.requests_total

        async with facade(fake_cloud, clock=fake_clock, tokens=TokenSet.from_dict(persisted)) as resumed:
            devices = await bounded(resumed.devices.list())

        assert requests_since(fake_cloud, start) == [MOWERS]
        assert len(devices) == 2

    async def test_a_resumed_token_set_past_its_expiry_is_renewed_with_its_refresh_token(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        persisted = (await bounded(api.authenticate())).to_dict()
        fake_clock.advance(TOKEN_TTL_S + 1)
        start = fake_cloud.state.requests_total

        async with facade(fake_cloud, clock=fake_clock, tokens=TokenSet.from_dict(persisted)) as resumed:
            await bounded(resumed.devices.list())

        assert requests_since(fake_cloud, start) == [TOKEN, MOWERS]
        assert grant_types(fake_cloud, start) == ["refresh_token"]

    async def test_a_failing_on_token_updated_does_not_fail_the_call(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        """D16: the grant succeeded, so a host storage failure neither fails the request nor forces another grant."""

        async def broken(token: TokenSet) -> None:
            raise OSError(token.token_type)

        async with facade(fake_cloud, clock=fake_clock, on_token_updated=broken) as client:
            devices = await bounded(client.devices.list())

        assert len(devices) == 2

    async def test_a_failing_on_token_updated_does_not_force_another_grant(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        """D16: the renewed token is kept in memory even though the host could not persist it."""

        async def broken(token: TokenSet) -> None:
            raise OSError(token.token_type)

        async with facade(fake_cloud, clock=fake_clock, on_token_updated=broken) as client:
            await bounded(client.devices.list())
            await bounded(client.devices.list())

        assert grant_types(fake_cloud) == ["client_credentials"]


class TestSuccessCodes:
    @pytest.mark.parametrize("code", [0, 200])
    async def test_either_success_code_is_accepted_for_grants_and_calls(
        self, api: OpenMammotion, fake_cloud: FakeCloud, code: int
    ) -> None:
        """D8: the portal's prose shows ``code: 0``, the OpenAPI examples ``200``."""
        await bounded(fake_cloud.control(envelope_code=code))

        devices = await bounded(api.devices.list())
        detail = await bounded(api.devices.get(YUKA_ID))

        assert len(devices) == 2
        assert detail.device_id == YUKA_ID
