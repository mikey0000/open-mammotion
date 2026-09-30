"""HA local-network configuration and the LAN WebSocket ticket on the fake cloud.

These pin the fake itself (docs/testing.md §6) with a raw client, so the facade's integration tests can trust it.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import TYPE_CHECKING, Any

import pytest

from tests.fakeserver.state import FAKE_CLIENT_ID, FAKE_TICKET_KEY, LUBA_NAME, YUKA_NAME
from tests.integration._fakeserver_client import START_S

if TYPE_CHECKING:
    from tests.fakeserver.clock import ManualClock
    from tests.integration._fakeserver_client import RawClient


# WsTicket properties from docs/openapi/mower.json, in schema order.
SPEC_TICKET_FIELDS = ("ticketId", "productKey", "deviceName", "userId", "clientId", "allowedIp", "iat", "exp", "sign")


def expected_signature(ticket: dict[str, Any]) -> str:
    # The key and the "|"-joined field order are the fake's own choice; the spec fixes only HMAC-SHA256 hex.
    message = "|".join(str(ticket[name]) for name in SPEC_TICKET_FIELDS[:-1])
    return hmac.new(FAKE_TICKET_KEY, message.encode(), hashlib.sha256).hexdigest()


class TestLocalNetwork:
    async def test_save_dispatches_to_online_and_fails_offline_devices(self, raw_client: RawClient) -> None:
        saved = await raw_client.data(
            "POST",
            "/v1/ha/local-network/save",
            json={
                "clientId": FAKE_CLIENT_ID,
                "redirectUri": "http://127.0.0.1/cb",
                "devices": [{"deviceName": YUKA_NAME, "enabled": 1}, {"deviceName": LUBA_NAME, "enabled": 1}],
            },
        )

        assert [(c["deviceName"], c["dispatchStatus"], c.get("failReason")) for c in saved] == [
            (YUKA_NAME, 1, None),
            (LUBA_NAME, 2, "device offline"),
        ]

    async def test_query_lists_configured_devices_for_the_client(self, raw_client: RawClient) -> None:
        everything = await raw_client.data("POST", "/v1/ha/local-network/query", json={"clientId": FAKE_CLIENT_ID})
        unconfigured = await raw_client.data(
            "POST", "/v1/ha/local-network/query", json={"clientId": FAKE_CLIENT_ID, "deviceName": LUBA_NAME}
        )

        assert everything == [{"deviceName": YUKA_NAME, "clientId": FAKE_CLIENT_ID, "enabled": 1, "dispatchStatus": 1}]
        assert unconfigured == []

    @pytest.mark.parametrize(
        ("body", "code", "msg"),
        [
            ({"devices": [{"deviceName": YUKA_NAME, "enabled": 1}]}, 400, "clientId is required"),
            (
                {"clientId": FAKE_CLIENT_ID, "devices": [{"deviceName": YUKA_NAME}]},
                400,
                "devices[0].enabled is required",
            ),
            (
                {"clientId": FAKE_CLIENT_ID, "devices": [{"deviceName": YUKA_NAME, "enabled": 2}]},
                400,
                "devices[0].enabled is invalid",
            ),
            ({"clientId": FAKE_CLIENT_ID, "devices": [{"deviceName": "nope", "enabled": 0}]}, 404, "device not found"),
        ],
        ids=["no-client", "no-enabled", "enabled-out-of-range", "unknown-device"],
    )
    async def test_save_rejects_a_bad_request(
        self, raw_client: RawClient, body: dict[str, Any], code: int, msg: str
    ) -> None:
        response = await raw_client.call("POST", "/v1/ha/local-network/save", json=body)

        assert (response["code"], response["msg"]) == (code, msg)


class TestWsTicket:
    async def test_issues_a_ticket_in_the_spec_shape(self, raw_client: RawClient, fake_clock: ManualClock) -> None:
        ticket = await raw_client.data(
            "POST",
            "/v1/mower/ws/ticket",
            json={"deviceName": YUKA_NAME, "timestamp": int(fake_clock.now), "ip": "10.0.0.5"},
        )

        assert set(ticket) == set(SPEC_TICKET_FIELDS)
        assert (ticket["deviceName"], ticket["clientId"], ticket["allowedIp"]) == (
            YUKA_NAME,
            FAKE_CLIENT_ID,
            "10.0.0.5",
        )
        assert (ticket["iat"], ticket["exp"]) == (int(START_S), int(START_S) + 3600)

    async def test_signs_with_lowercase_hex_hmac_sha256(self, raw_client: RawClient, fake_clock: ManualClock) -> None:
        ticket = await raw_client.data(
            "POST", "/v1/mower/ws/ticket", json={"deviceName": YUKA_NAME, "timestamp": int(fake_clock.now)}
        )

        assert re.fullmatch(r"[0-9a-f]{64}", ticket["sign"])
        assert ticket["sign"] == expected_signature(ticket)

    async def test_omitted_ip_leaves_the_ticket_unbound(self, raw_client: RawClient, fake_clock: ManualClock) -> None:
        ticket = await raw_client.data(
            "POST", "/v1/mower/ws/ticket", json={"deviceName": YUKA_NAME, "timestamp": int(fake_clock.now)}
        )

        assert ticket["allowedIp"] == ""

    async def test_rejects_a_skewed_timestamp(self, raw_client: RawClient, fake_clock: ManualClock) -> None:
        body = await raw_client.call(
            "POST", "/v1/mower/ws/ticket", json={"deviceName": YUKA_NAME, "timestamp": int(fake_clock.now) - 3600}
        )

        assert (body["code"], body["msg"]) == (400, "timestamp is invalid")
