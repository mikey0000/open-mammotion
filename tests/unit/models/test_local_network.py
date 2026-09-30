from __future__ import annotations

from datetime import UTC, datetime
import logging

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.local_network import (
    DispatchStatus,
    LocalNetworkConfig,
    LocalNetworkDevice,
    LocalNetworkQueryRequest,
    LocalNetworkSaveRequest,
    WsTicket,
    WsTicketRequest,
)
from tests.unit.models._helpers import local_network_config_json, ws_ticket_json


class TestLocalNetworkDevice:
    @pytest.mark.parametrize(("enabled", "wire"), [(True, 1), (False, 0)])
    def test_serialises_enabled_as_an_integer(self, enabled: bool, wire: int) -> None:
        body = LocalNetworkDevice(device_name="Luba-VS123456", enabled=enabled).to_dict()

        assert body == {"deviceName": "Luba-VS123456", "enabled": wire}
        assert type(body["enabled"]) is int

    def test_decodes_an_integer_enabled_flag(self) -> None:
        device = LocalNetworkDevice.from_dict({"deviceName": "Luba-VS123456", "enabled": 1})

        assert device == LocalNetworkDevice(device_name="Luba-VS123456", enabled=True)


class TestLocalNetworkSaveRequest:
    def test_serialises_devices_and_client(self) -> None:
        request = LocalNetworkSaveRequest(
            client_id="cid-test",
            devices=[
                LocalNetworkDevice(device_name="Luba-A", enabled=True),
                LocalNetworkDevice(device_name="Luba-B", enabled=False),
            ],
            redirect_uri="https://ha.example.invalid/cb",
        )

        assert request.to_dict() == {
            "clientId": "cid-test",
            "redirectUri": "https://ha.example.invalid/cb",
            "devices": [{"deviceName": "Luba-A", "enabled": 1}, {"deviceName": "Luba-B", "enabled": 0}],
        }

    def test_omits_an_unset_redirect_uri(self) -> None:
        request = LocalNetworkSaveRequest(client_id="cid-test", devices=[LocalNetworkDevice("Luba-A", enabled=True)])

        assert "redirectUri" not in request.to_dict()


class TestLocalNetworkQueryRequest:
    def test_omits_an_unset_device_name(self) -> None:
        assert LocalNetworkQueryRequest(client_id="cid-test").to_dict() == {"clientId": "cid-test"}

    def test_serialises_a_device_name(self) -> None:
        assert LocalNetworkQueryRequest(client_id="cid-test", device_name="Luba-A").to_dict() == {
            "clientId": "cid-test",
            "deviceName": "Luba-A",
        }


class TestLocalNetworkConfig:
    def test_decodes_every_alias(self) -> None:
        config = LocalNetworkConfig.from_dict(local_network_config_json(failReason="unreachable", dispatchStatus=2))

        assert config == LocalNetworkConfig(
            device_name="Luba-VS123456",
            client_id="cid-test",
            redirect_uri="https://ha.example.invalid/auth/external/callback",
            enabled=True,
            dispatch_status=DispatchStatus.FAILED,
            fail_reason="unreachable",
        )

    def test_decodes_enabled_zero_as_false(self) -> None:
        assert LocalNetworkConfig.from_dict(local_network_config_json(enabled=0)).enabled is False

    def test_decodes_an_unlisted_dispatch_status_as_unknown(self) -> None:
        config = LocalNetworkConfig.from_dict(local_network_config_json(dispatchStatus=9_301))

        assert config.dispatch_status is DispatchStatus.UNKNOWN

    def test_logs_an_unlisted_dispatch_status_once(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())

        LocalNetworkConfig.from_dict(local_network_config_json(dispatchStatus=9_302))
        LocalNetworkConfig.from_dict(local_network_config_json(dispatchStatus=9_302))

        assert [r.levelno for r in caplog.records if "9302" in r.getMessage()] == [logging.WARNING]

    def test_optional_parts_default_when_absent(self) -> None:
        config = LocalNetworkConfig.from_dict({"deviceName": "Luba-VS123456", "clientId": "cid-test"})

        assert config.redirect_uri is None
        assert config.enabled is False
        assert config.dispatch_status is DispatchStatus.UNKNOWN
        assert config.fail_reason is None

    def test_rejects_a_config_without_a_device_name(self) -> None:
        body = local_network_config_json()
        del body["deviceName"]

        with pytest.raises(MissingField, match="device_name"):
            LocalNetworkConfig.from_dict(body)


class TestWsTicketRequest:
    def test_serialises_device_and_timestamp(self) -> None:
        assert WsTicketRequest(device_name="Luba-A", timestamp_s=1_727_700_000).to_dict() == {
            "deviceName": "Luba-A",
            "timestamp": 1_727_700_000,
        }

    def test_serialises_an_ip_binding(self) -> None:
        body = WsTicketRequest(device_name="Luba-A", timestamp_s=1_727_700_000, ip="192.0.2.10").to_dict()

        assert body["ip"] == "192.0.2.10"


class TestWsTicket:
    def test_decodes_every_alias(self) -> None:
        ticket = WsTicket.from_dict(ws_ticket_json())

        assert ticket == WsTicket(
            ticket_id="ticket-1",
            product_key="pk-test",
            device_name="Luba-VS123456",
            user_id="user-1",
            client_id="cid-test",
            allowed_ip="",
            issued_at_s=1_727_700_000,
            expires_at_s=1_727_703_600,
            signature="0f" * 32,
        )

    def test_exposes_issue_and_expiry_as_utc_datetimes(self) -> None:
        ticket = WsTicket.from_dict(ws_ticket_json())

        assert ticket.issued_at == datetime(2024, 9, 30, 12, 40, tzinfo=UTC)
        assert ticket.expires_at == datetime(2024, 9, 30, 13, 40, tzinfo=UTC)

    def test_repr_never_contains_the_signature(self) -> None:
        ticket = WsTicket.from_dict(ws_ticket_json(sign="deadbeefcafef00d"))

        assert "deadbeefcafef00d" not in repr(ticket)
        assert "deadbeefcafef00d" not in str(ticket)
        assert "ticket-1" in repr(ticket)

    def test_unbound_parts_default_to_empty_strings(self) -> None:
        ticket = WsTicket.from_dict(
            {"ticketId": "ticket-1", "deviceName": "Luba-A", "iat": 1_727_700_000, "exp": 1_727_703_600, "sign": "ab"}
        )

        assert (ticket.product_key, ticket.user_id, ticket.client_id, ticket.allowed_ip) == ("", "", "", "")

    def test_rejects_a_ticket_without_a_signature(self) -> None:
        body = ws_ticket_json()
        del body["sign"]

        with pytest.raises(MissingField, match="signature"):
            WsTicket.from_dict(body)
