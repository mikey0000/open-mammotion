from __future__ import annotations

import pytest

from open_mammotion.api.local_network import LocalNetworkApi
from open_mammotion.exceptions import ContractError
from open_mammotion.models.local_network import DispatchStatus, LocalNetworkDevice
from tests.unit._fakes import FakeRequester, RecordedCall
from tests.unit.models._helpers import local_network_config_json, ws_ticket_json

SAVE_PATH = "/v1/ha/local-network/save"
QUERY_PATH = "/v1/ha/local-network/query"
TICKET_PATH = "/v1/mower/ws/ticket"
NOW_S = 1_727_700_000.75


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def api(requester: FakeRequester) -> LocalNetworkApi:
    return LocalNetworkApi(requester, clock=lambda: NOW_S)


class TestSave:
    async def test_posts_devices_with_enabled_as_integers(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        requester.on("POST", SAVE_PATH, [local_network_config_json(dispatchStatus=0)])

        configs = await api.save(
            "cid-test",
            [LocalNetworkDevice("Luba-A", enabled=True), LocalNetworkDevice("Luba-B", enabled=False)],
            redirect_uri="https://ha.example.invalid/cb",
        )

        assert [c.dispatch_status for c in configs] == [DispatchStatus.PENDING]
        assert requester.calls == [
            RecordedCall(
                "POST",
                SAVE_PATH,
                {
                    "clientId": "cid-test",
                    "redirectUri": "https://ha.example.invalid/cb",
                    "devices": [{"deviceName": "Luba-A", "enabled": 1}, {"deviceName": "Luba-B", "enabled": 0}],
                },
            )
        ]

    async def test_omits_an_unset_redirect_uri(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        requester.on("POST", SAVE_PATH, [])

        await api.save("cid-test", [LocalNetworkDevice("Luba-A", enabled=True)])

        assert requester.calls[0].json == {"clientId": "cid-test", "devices": [{"deviceName": "Luba-A", "enabled": 1}]}

    async def test_rejects_an_empty_device_list_before_io(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="devices"):
            await api.save("cid-test", [])

        assert requester.calls == []

    async def test_rejects_an_empty_client_id_before_io(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="client_id"):
            await api.save("", [LocalNetworkDevice("Luba-A", enabled=True)])

        assert requester.calls == []

    async def test_raises_contract_error_when_data_is_not_a_list(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", SAVE_PATH, local_network_config_json())

        with pytest.raises(ContractError):
            await api.save("cid-test", [LocalNetworkDevice("Luba-A", enabled=True)])


class TestQuery:
    async def test_posts_the_client_and_returns_every_config(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", QUERY_PATH, [local_network_config_json(), local_network_config_json(deviceName="Luba-B")])

        configs = await api.query("cid-test")

        assert [c.device_name for c in configs] == ["Luba-VS123456", "Luba-B"]
        assert requester.calls == [RecordedCall("POST", QUERY_PATH, {"clientId": "cid-test"})]

    async def test_filters_by_device_name(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        requester.on("POST", QUERY_PATH, [local_network_config_json()])

        await api.query("cid-test", device_name="Luba-VS123456")

        assert requester.calls[0].json == {"clientId": "cid-test", "deviceName": "Luba-VS123456"}

    async def test_returns_an_empty_list_for_null_data(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        requester.on("POST", QUERY_PATH, None)

        assert await api.query("cid-test") == []

    async def test_rejects_an_empty_client_id_before_io(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="client_id"):
            await api.query("")

        assert requester.calls == []

    async def test_raises_contract_error_on_a_config_without_a_device_name(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        config = local_network_config_json()
        del config["deviceName"]
        requester.on("POST", QUERY_PATH, [config])

        with pytest.raises(ContractError, match="device_name"):
            await api.query("cid-test")


class TestWsTicket:
    async def test_defaults_the_timestamp_to_the_injected_clock_in_whole_seconds(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", TICKET_PATH, ws_ticket_json())

        ticket = await api.ws_ticket("Luba-VS123456")

        assert ticket.ticket_id == "ticket-1"
        assert requester.calls == [
            RecordedCall("POST", TICKET_PATH, {"deviceName": "Luba-VS123456", "timestamp": 1_727_700_000})
        ]

    async def test_sends_an_explicit_timestamp_and_ip(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        requester.on("POST", TICKET_PATH, ws_ticket_json(allowedIp="192.0.2.10"))

        await api.ws_ticket("Luba-VS123456", timestamp_s=1_600_000_000, ip="192.0.2.10")

        assert requester.calls[0].json == {
            "deviceName": "Luba-VS123456",
            "timestamp": 1_600_000_000,
            "ip": "192.0.2.10",
        }

    async def test_sends_an_explicit_zero_timestamp_rather_than_the_clock(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", TICKET_PATH, ws_ticket_json())

        await api.ws_ticket("Luba-VS123456", timestamp_s=0)

        assert requester.calls[0].json == {"deviceName": "Luba-VS123456", "timestamp": 0}

    async def test_rejects_an_empty_device_name_before_io(self, api: LocalNetworkApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="device_name"):
            await api.ws_ticket("")

        assert requester.calls == []

    async def test_raises_contract_error_on_a_ticket_without_a_signature(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        ticket = ws_ticket_json()
        del ticket["sign"]
        requester.on("POST", TICKET_PATH, ticket)

        with pytest.raises(ContractError, match="signature"):
            await api.ws_ticket("Luba-VS123456")

    async def test_contract_error_never_carries_the_signature(
        self, api: LocalNetworkApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", TICKET_PATH, ws_ticket_json(sign="deadbeefcafef00d", iat="not-a-number"))

        with pytest.raises(ContractError) as excinfo:
            await api.ws_ticket("Luba-VS123456")

        assert "issued_at_s" in str(excinfo.value)
        assert "deadbeefcafef00d" not in str(excinfo.value)
