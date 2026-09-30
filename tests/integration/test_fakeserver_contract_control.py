"""The fake cloud's /control fault-injection knobs.

These pin the fake itself (docs/testing.md §6) with a raw client, so the facade's integration tests can trust it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.fakeserver.state import YUKA_ID

if TYPE_CHECKING:
    from tests.fakeserver.clock import RecordingSleep
    from tests.integration._fakeserver_client import RawClient


class TestControl:
    async def test_next_status_fails_exactly_count_requests_with_json(self, raw_client: RawClient) -> None:
        await raw_client.control(next_status={"status": 503, "count": 2})

        statuses = [(await raw_client.raw("GET", "/v1/mowers"))[:2] for _ in range(3)]

        assert statuses == [(503, "application/json"), (503, "application/json"), (200, "application/json")]

    async def test_next_status_can_answer_html(self, raw_client: RawClient) -> None:
        await raw_client.control(next_status={"status": 502, "non_json": True})

        status, content_type, text = await raw_client.raw("GET", "/v1/mowers")

        assert (status, content_type) == (502, "text/html")
        assert text.startswith("<html>")

    async def test_token_next_status_fails_the_token_endpoint_only(self, raw_client: RawClient) -> None:
        await raw_client.control(token_next_status={"status": 500})

        status, _, _ = await raw_client.raw("POST", "/oauth2/token", token="")
        api_status, _, _ = await raw_client.raw("GET", "/v1/mowers")

        assert (status, api_status) == (500, 200)

    async def test_next_envelope_forces_an_error_code(self, raw_client: RawClient) -> None:
        await raw_client.control(next_envelope={"code": 50001, "msg": "system busy"})

        forced = await raw_client.call("GET", "/v1/mowers")
        normal = await raw_client.call("GET", "/v1/mowers")

        assert (forced["code"], forced["msg"], normal["code"]) == (50001, "system busy", 200)

    async def test_envelope_code_switches_the_success_code(self, raw_client: RawClient) -> None:
        await raw_client.control(envelope_code=0)

        body = await raw_client.call("GET", "/v1/mowers")
        grant = await raw_client.grant()

        assert (body["code"], body["msg"], grant["code"]) == (0, "Request success", 0)

    async def test_delay_ms_is_handed_to_the_injected_sleep(
        self, raw_client: RawClient, fake_sleep: RecordingSleep
    ) -> None:
        await raw_client.control(delay_ms=25)

        await raw_client.call("GET", "/v1/mowers")

        assert fake_sleep.calls == [0.025]

    async def test_next_status_fires_before_auth(self, raw_client: RawClient) -> None:
        await raw_client.control(next_status={"status": 429})

        status, _, _ = await raw_client.raw("GET", "/v1/mowers", token="")

        assert status == 429

    async def test_next_envelope_is_not_spent_on_an_unauthenticated_request(self, raw_client: RawClient) -> None:
        await raw_client.control(next_envelope={"code": 50001})

        unauthenticated, _, _ = await raw_client.raw("GET", "/v1/mowers", token="")
        forced = await raw_client.call("GET", "/v1/mowers")

        assert (unauthenticated, forced["code"]) == (401, 50001)

    async def test_reset_restores_seed_data_knobs_and_counters(self, raw_client: RawClient) -> None:
        await raw_client.data("POST", "/v1/mower/action", json={"deviceId": YUKA_ID, "action": "PAUSE"})
        await raw_client.data(
            "POST", "/v1/devices/subscriptions", json=[{"deviceId": YUKA_ID, "properties": ["DEV_ST"]}]
        )
        await raw_client.control(envelope_code=0, delay_ms=5)

        snapshot = await raw_client.control(reset=True)
        detail = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}")

        assert (snapshot["envelope_code"], snapshot["delay_ms"], snapshot["actions_total"]) == (200, 0, 0)
        assert snapshot["token_grants"] == {"client_credentials": 0, "refresh_token": 0}
        assert raw_client.state.subscriptions == {}
        assert detail["status"] == "Standby"

    async def test_reset_is_applied_before_the_other_knobs_in_the_same_call(self, raw_client: RawClient) -> None:
        snapshot = await raw_client.control(envelope_code=0, reset=True)

        assert snapshot["envelope_code"] == 0

    async def test_rejects_an_unknown_knob_without_changing_anything(self, raw_client: RawClient) -> None:
        with pytest.raises(ValueError, match="unknown knob: explode"):
            await raw_client.control(delay_ms=5, explode=True)

        assert (await raw_client.control())["delay_ms"] == 0

    @pytest.mark.parametrize(
        ("knobs", "error"),
        [
            ({"token_ttl_s": 0}, "token_ttl_s must be an integer >= 1"),
            ({"delay_ms": -1}, "delay_ms must be an integer >= 0"),
            ({"envelope_code": 1}, "envelope_code must be 0 or 200"),
            ({"next_status": {"count": 1}}, "next_status.status must be an integer >= 100"),
            ({"reject_next_refresh": "yes"}, "reject_next_refresh must be a boolean"),
        ],
        ids=["ttl-zero", "negative-delay", "bad-envelope-code", "status-missing", "non-bool"],
    )
    async def test_rejects_an_ill_typed_knob(self, raw_client: RawClient, knobs: dict[str, Any], error: str) -> None:
        with pytest.raises(ValueError, match=f"^{error}$"):
            await raw_client.control(**knobs)

    async def test_counts_recorded_requests_but_not_control_calls(self, raw_client: RawClient) -> None:
        before = (await raw_client.control())["requests_total"]

        await raw_client.call("GET", "/v1/mowers")
        after = (await raw_client.control())["requests_total"]

        assert after - before == 1
