"""How the facade surfaces server failures (architecture.md §2.3), and what it sends and leaves open."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from open_mammotion import ApiError, TransportError, UnauthorizedError
from open_mammotion.const import TOKEN_PATH
from tests.fakeserver.state import YUKA_ID
from tests.integration._fakeserver_client import bounded
from tests.integration._helpers import (
    INTO_LEAD_WINDOW_S,
    MOWERS,
    TOKEN,
    facade,
    grant_types,
    requests_since,
    secrets_in_text,
)

if TYPE_CHECKING:
    import aiohttp

    from open_mammotion import OpenMammotion
    from tests.fakeserver.clock import ManualClock
    from tests.fakeserver.server import FakeCloud


class TestTransientStatus:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
    async def test_a_transient_status_raises_transport_error_with_the_status(
        self, api: OpenMammotion, fake_cloud: FakeCloud, status: int
    ) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(next_status={"status": status}))

        with pytest.raises(TransportError) as caught:
            await bounded(api.devices.list())

        assert caught.value.status == status
        assert not secrets_in_text(str(caught.value), fake_cloud)

    async def test_a_503_leaves_the_token_in_use(self, api: OpenMammotion, fake_cloud: FakeCloud) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(next_status={"status": 503}))
        with pytest.raises(TransportError):
            await bounded(api.devices.list())

        devices = await bounded(api.devices.list())

        assert len(devices) == 2
        assert grant_types(fake_cloud) == ["client_credentials"]

    async def test_a_non_json_500_raises_transport_error(self, api: OpenMammotion, fake_cloud: FakeCloud) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(next_status={"status": 500, "non_json": True}))

        with pytest.raises(TransportError) as caught:
            await bounded(api.devices.get(YUKA_ID))

        assert caught.value.status == 500
        assert not secrets_in_text(str(caught.value), fake_cloud)


class TestClientErrorStatus:
    async def test_a_non_json_404_raises_api_error_with_the_status_as_code(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(next_status={"status": 404, "non_json": True}))

        with pytest.raises(ApiError) as caught:
            await bounded(api.devices.get(YUKA_ID))

        assert caught.value.code == 404
        assert not secrets_in_text(str(caught.value), fake_cloud)


class TestPersistentUnauthorized:
    async def test_a_second_401_after_the_refresh_raises_unauthorized_error(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.authenticate())
        start = fake_cloud.state.requests_total
        await bounded(fake_cloud.control(next_status={"status": 401, "count": 2}))

        with pytest.raises(UnauthorizedError) as caught:
            await bounded(api.devices.list())

        assert requests_since(fake_cloud, start) == [MOWERS, TOKEN, MOWERS]
        assert api.credentials_rejected is None
        assert not secrets_in_text(str(caught.value), fake_cloud)


class TestFailureEnvelope:
    async def test_a_failure_code_raises_api_error_with_code_and_msg(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(api.authenticate())
        await bounded(fake_cloud.control(next_envelope={"code": 500, "msg": "internal failure"}))

        with pytest.raises(ApiError) as caught:
            await bounded(api.devices.list())

        assert (caught.value.code, caught.value.msg) == (500, "internal failure")
        assert caught.value.request_id is not None
        assert not secrets_in_text(str(caught.value), fake_cloud)


class TestTokenEndpointUnavailable:
    async def test_a_503_on_a_needed_grant_raises_transport_error_and_is_not_terminal(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        await bounded(fake_cloud.control(token_next_status={"status": 503}))

        with pytest.raises(TransportError) as caught:
            await bounded(api.devices.list())

        assert caught.value.status == 503
        assert api.credentials_rejected is None
        assert [r.path for r in fake_cloud.state.requests] == [TOKEN_PATH]
        assert not secrets_in_text(str(caught.value), fake_cloud)

    async def test_the_next_call_grants_and_succeeds(self, api: OpenMammotion, fake_cloud: FakeCloud) -> None:
        await bounded(fake_cloud.control(token_next_status={"status": 503}))
        with pytest.raises(TransportError):
            await bounded(api.devices.list())

        devices = await bounded(api.devices.list())

        assert len(devices) == 2
        assert grant_types(fake_cloud) == ["client_credentials", "client_credentials"]

    async def test_a_503_on_a_refresh_keeps_the_refresh_token_for_the_next_call(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        await bounded(api.authenticate())
        fake_clock.advance(INTO_LEAD_WINDOW_S)
        await bounded(fake_cloud.control(token_next_status={"status": 503}))
        with pytest.raises(TransportError):
            await bounded(api.devices.list())

        await bounded(api.devices.list())

        assert grant_types(fake_cloud) == ["client_credentials", "refresh_token", "refresh_token"]
        assert (await bounded(fake_cloud.control()))["token_grants"] == {"client_credentials": 1, "refresh_token": 1}


class TestRequestHeaders:
    async def test_the_language_reaches_the_server_as_accept_language(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        async with facade(fake_cloud, clock=fake_clock, language="de-DE") as client:
            await bounded(client.devices.list())
            await bounded(client.devices.get(YUKA_ID))

        api_requests = [r for r in fake_cloud.state.requests if r.path.startswith("/v1/")]
        assert [r.accept_language for r in api_requests] == ["de-DE", "de-DE"]


class TestPathSafety:
    @pytest.mark.regression
    @pytest.mark.parametrize("device_id", [".", ".."])
    async def test_a_dot_segment_device_id_never_reaches_another_endpoint(
        self, api: OpenMammotion, fake_cloud: FakeCloud, device_id: str
    ) -> None:
        """``ApiGroup._mower_path`` percent-encodes each segment but leaves ``.``/``..`` as they are.

        The URL is then normalised before it is sent, so ``tasks("..")`` asks ``/v1/plan`` and ``tasks(".")``
        asks ``/v1/mower/plan``: a caller-supplied id silently addresses a different endpoint. The id must
        either be refused before any I/O or reach ``/v1/mower/{deviceId}/plan`` intact.
        """
        with pytest.raises((ValueError, ApiError)):
            await bounded(api.actions.tasks(device_id))

        sent = [r.path for r in fake_cloud.state.requests if r.path != TOKEN_PATH]
        assert sent in ([], [f"/v1/mower/{device_id}/plan"])


class TestSessionOwnership:
    async def test_a_borrowed_session_is_still_open_after_the_facade_closes(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock, raw_http: aiohttp.ClientSession
    ) -> None:
        async with facade(fake_cloud, clock=fake_clock, session=raw_http) as client:
            await bounded(client.devices.list())

        assert not raw_http.closed

    async def test_an_owned_session_is_released_on_close_and_reopened_on_demand(
        self, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        client = facade(fake_cloud, clock=fake_clock)
        await bounded(client.devices.list())
        await bounded(client.close())

        devices = await bounded(client.devices.list())
        await bounded(client.close())

        assert len(devices) == 2
