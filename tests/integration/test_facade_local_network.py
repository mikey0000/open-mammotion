"""``OpenMammotion.local_network``: configuration dispatch per device and the LAN WebSocket ticket."""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_mammotion import LocalNetworkDevice
from open_mammotion.models.local_network import DispatchStatus
from tests._helpers import CREDENTIALS
from tests.fakeserver.state import LUBA_NAME, YUKA_NAME
from tests.integration._fakeserver_client import bounded

if TYPE_CHECKING:
    from open_mammotion import OpenMammotion
    from tests.fakeserver.clock import ManualClock
    from tests.fakeserver.server import FakeCloud

CLIENT_ID = CREDENTIALS.client_id
TICKET_PATH = "/v1/mower/ws/ticket"


class TestSave:
    async def test_dispatches_to_the_online_mower(self, api: OpenMammotion) -> None:
        [config] = await bounded(api.local_network.save(CLIENT_ID, [LocalNetworkDevice(YUKA_NAME, enabled=True)]))

        assert (config.dispatch_status, config.fail_reason) == (DispatchStatus.SUCCESS, None)
        assert (config.enabled, config.client_id) == (True, CLIENT_ID)

    async def test_reports_a_failed_dispatch_for_the_offline_mower(self, api: OpenMammotion) -> None:
        devices = [LocalNetworkDevice(YUKA_NAME, enabled=True), LocalNetworkDevice(LUBA_NAME, enabled=True)]

        configs = await bounded(api.local_network.save(CLIENT_ID, devices))

        by_name = {c.device_name: c for c in configs}
        assert by_name[YUKA_NAME].dispatch_status is DispatchStatus.SUCCESS
        assert (by_name[LUBA_NAME].dispatch_status, by_name[LUBA_NAME].fail_reason) == (
            DispatchStatus.FAILED,
            "device offline",
        )

    async def test_a_saved_configuration_is_returned_by_query(self, api: OpenMammotion) -> None:
        await bounded(api.local_network.save(CLIENT_ID, [LocalNetworkDevice(LUBA_NAME, enabled=False)]))

        [config] = await bounded(api.local_network.query(CLIENT_ID, device_name=LUBA_NAME))

        assert (config.device_name, config.enabled, config.dispatch_status) == (
            LUBA_NAME,
            False,
            DispatchStatus.FAILED,
        )


class TestQuery:
    async def test_lists_every_configured_device_when_unnamed(self, api: OpenMammotion) -> None:
        configs = await bounded(api.local_network.query(CLIENT_ID))

        assert [(c.device_name, c.enabled, c.dispatch_status) for c in configs] == [
            (YUKA_NAME, True, DispatchStatus.SUCCESS)
        ]

    async def test_an_unconfigured_device_has_no_configuration(self, api: OpenMammotion) -> None:
        assert await bounded(api.local_network.query(CLIENT_ID, device_name=LUBA_NAME)) == []


class TestWsTicket:
    async def test_the_signature_is_redacted_in_repr(self, api: OpenMammotion) -> None:
        ticket = await bounded(api.local_network.ws_ticket(YUKA_NAME))

        assert ticket.signature
        assert ticket.signature not in repr(ticket)
        assert "<redacted>" in repr(ticket)

    async def test_expires_with_the_access_token_it_was_minted_under(self, api: OpenMammotion) -> None:
        ticket = await bounded(api.local_network.ws_ticket(YUKA_NAME))

        assert api.token is not None
        assert ticket.expires_at_s == int(api.token.expires_at_s)
        assert (ticket.device_name, ticket.client_id) == (YUKA_NAME, CLIENT_ID)

    async def test_binds_to_the_given_source_ip(self, api: OpenMammotion) -> None:
        ticket = await bounded(api.local_network.ws_ticket(YUKA_NAME, ip="192.168.1.50"))

        assert ticket.allowed_ip == "192.168.1.50"

    async def test_is_unbound_without_an_ip(self, api: OpenMammotion) -> None:
        ticket = await bounded(api.local_network.ws_ticket(YUKA_NAME))

        assert ticket.allowed_ip == ""

    async def test_stamps_the_request_with_the_injected_clock_by_default(
        self, api: OpenMammotion, fake_cloud: FakeCloud, fake_clock: ManualClock
    ) -> None:
        ticket = await bounded(api.local_network.ws_ticket(YUKA_NAME))

        [sent] = [r for r in fake_cloud.state.requests if r.path == TICKET_PATH]
        assert sent.body["timestamp"] == int(fake_clock())
        assert ticket.issued_at_s == int(fake_clock())
