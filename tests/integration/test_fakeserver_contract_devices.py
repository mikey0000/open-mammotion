"""Device, action, plan, material and subscription routes on the fake cloud.

These pin the fake itself (docs/testing.md §6) with a raw client, so the facade's integration tests can trust it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.fakeserver.state import LUBA_ID, LUBA_NAME, YUKA_ID, YUKA_NAME, YUKA_TASKS
from tests.integration._fakeserver_client import TITLED_ENVELOPE_KEYS

if TYPE_CHECKING:
    from tests.integration._fakeserver_client import RawClient


class TestDevices:
    async def test_lists_both_seed_devices(self, raw_client: RawClient) -> None:
        body = await raw_client.call("GET", "/v1/mowers")

        assert set(body) == TITLED_ENVELOPE_KEYS
        assert body["msgTitle"] == "Operation Successful"
        assert [(d["id"], d["name"], d["online"]) for d in body["data"]] == [
            (YUKA_ID, YUKA_NAME, 1),
            (LUBA_ID, LUBA_NAME, 0),
        ]
        assert set(body["data"][0]) == {"id", "name", "nickname", "model", "icon", "online"}

    async def test_returns_device_detail_as_an_object(self, raw_client: RawClient) -> None:
        detail = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}")

        assert set(detail) == {
            "id", "name", "nickname", "model", "icon", "version", "online", "status", "batteryLevel", "chargeStatus",
            "network",
        }  # fmt: skip
        assert (detail["status"], detail["chargeStatus"], detail["network"]["usedNetwork"]) == ("Standby", 1, "1")

    async def test_detail_as_list_knob_wraps_the_detail(self, raw_client: RawClient) -> None:
        await raw_client.control(detail_as_list=True)

        detail = await raw_client.data("GET", f"/v1/mower/{LUBA_ID}")

        assert [d["status"] for d in detail] == ["Offline"]

    async def test_unknown_device_is_envelope_404(self, raw_client: RawClient) -> None:
        body = await raw_client.call("GET", "/v1/mower/no-such-device")

        assert (body["code"], body["msg"]) == (404, "device not found")


class TestActions:
    async def action(self, raw_client: RawClient, **body: Any) -> dict[str, Any]:
        return await raw_client.data("POST", "/v1/mower/action", json=body)

    @pytest.mark.parametrize(
        ("action", "params", "status", "charging"),
        [
            ("CMD_START", None, "Working", 0),
            ("START", {"taskName": YUKA_TASKS[0]}, "Working", 0),
            ("PAUSE", None, "Paused", 1),
            ("RESUME", None, "Working", 0),
            ("STOP", None, "Standby", 1),
            ("RETURN", None, "Returning", 1),
            ("CANCEL_RETURN", None, "Paused", 1),
        ],
    )
    async def test_accepted_action_moves_the_device_status(
        self, raw_client: RawClient, action: str, params: dict[str, str] | None, status: str, charging: int
    ) -> None:
        body: dict[str, Any] = {"deviceId": YUKA_ID, "action": action}
        if params is not None:
            body["params"] = params

        result = await self.action(raw_client, **body)
        detail = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}")

        assert result == {"commandResult": True, "resultMessage": "Success"}
        assert (detail["status"], detail["chargeStatus"]) == (status, charging)

    async def test_records_the_action_and_its_task(self, raw_client: RawClient) -> None:
        await self.action(raw_client, deviceId=YUKA_ID, action="START", params={"taskName": YUKA_TASKS[0]})

        recorded = raw_client.state.actions[-1]
        assert (recorded.device_id, recorded.action, recorded.task_name, recorded.accepted) == (
            YUKA_ID,
            "START",
            YUKA_TASKS[0],
            True,
        )

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ({"deviceId": YUKA_ID, "action": "START"}, "taskName is required"),
            ({"deviceId": YUKA_ID, "action": "START", "params": {"taskName": "Nope"}}, "task not found"),
            ({"deviceId": LUBA_ID, "action": "RETURN"}, "device offline"),
        ],
        ids=["start-without-task", "unknown-task", "offline"],
    )
    async def test_rejects_with_command_result_false(
        self, raw_client: RawClient, body: dict[str, Any], message: str
    ) -> None:
        before = (await raw_client.data("GET", f"/v1/mower/{body['deviceId']}"))["status"]

        result = await self.action(raw_client, **body)
        after = (await raw_client.data("GET", f"/v1/mower/{body['deviceId']}"))["status"]

        assert result == {"commandResult": False, "resultMessage": message}
        assert after == before
        assert raw_client.state.actions[-1].accepted is False

    @pytest.mark.parametrize(
        ("body", "code", "msg"),
        [
            ({"deviceId": YUKA_ID}, 400, "action is required"),
            ({"action": "STOP"}, 400, "deviceId is required"),
            ({"deviceId": YUKA_ID, "action": "DANCE"}, 400, "action is invalid"),
            ({"deviceId": "no-such-device", "action": "STOP"}, 404, "device not found"),
        ],
        ids=["no-action", "no-device", "bad-action", "unknown-device"],
    )
    async def test_rejects_a_bad_request_with_an_error_envelope(
        self, raw_client: RawClient, body: dict[str, Any], code: int, msg: str
    ) -> None:
        response = await raw_client.call("POST", "/v1/mower/action", json=body)

        assert (response["code"], response["msg"]) == (code, msg)


class TestWorkParamsAndPlan:
    async def test_returns_every_work_parameter_for_an_online_device(self, raw_client: RawClient) -> None:
        params = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}/work-params")

        assert set(params) == {
            "commandResult", "resultMessage", "edgeMode", "rideBoundaryDistance", "channelMode", "jobContent",
            "dumpPeriodSqm", "knifeHeight", "speed", "channelWidth", "toward", "towardMode", "towardIncludedAngle",
            "ultraWave", "boundaryZigzagOrder", "forbiddenAreaCircleTimes", "visualHashs",
        }  # fmt: skip
        assert params["commandResult"] is True
        assert params["visualHashs"] == ["3f2a9c01", "7b1e44d2"]

    async def test_reports_an_offline_device_through_command_result(self, raw_client: RawClient) -> None:
        params = await raw_client.data("GET", f"/v1/mower/{LUBA_ID}/work-params")

        assert params == {"commandResult": False, "resultMessage": "device offline"}

    async def test_lists_the_task_plan(self, raw_client: RawClient) -> None:
        tasks = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}/plan")

        assert tasks == [
            {"taskId": "task-yuka-1", "taskName": YUKA_TASKS[0]},
            {"taskId": "task-yuka-2", "taskName": YUKA_TASKS[1]},
        ]


class TestMaterialAndSubscriptions:
    async def test_material_fetch_accepts_online_and_refuses_offline(self, raw_client: RawClient) -> None:
        online = await raw_client.data("POST", "/v1/mower/material/fetch", json={"deviceIds": [YUKA_ID]})
        offline = await raw_client.data("POST", "/v1/mower/material/fetch", json={"deviceIds": [LUBA_ID]})

        assert online == {"commandResult": True, "resultMessage": "ok"}
        assert offline == {"commandResult": False, "resultMessage": "device offline"}

    @pytest.mark.parametrize(
        ("device_ids", "code", "msg"),
        [([], 400, "deviceIds is invalid"), (["no-such-device"], 404, "device not found")],
        ids=["empty", "unknown-device"],
    )
    async def test_material_fetch_rejects_a_bad_request(
        self, raw_client: RawClient, device_ids: list[str], code: int, msg: str
    ) -> None:
        response = await raw_client.call("POST", "/v1/mower/material/fetch", json={"deviceIds": device_ids})

        assert (response["code"], response["msg"]) == (code, msg)

    async def test_subscription_is_accepted_and_stored(self, raw_client: RawClient) -> None:
        result = await raw_client.data(
            "POST", "/v1/devices/subscriptions", json=[{"deviceId": YUKA_ID, "properties": ["DEV_ST", "BAT_PCT"]}]
        )

        assert result == {"commandResult": True, "resultMessage": "ok"}
        assert raw_client.state.subscriptions == {YUKA_ID: ["DEV_ST", "BAT_PCT"]}

    @pytest.mark.parametrize(
        ("body", "msg"),
        [
            ([{"deviceId": YUKA_ID, "properties": ["NOPE"]}], "[0].properties is invalid"),
            ([{"deviceId": YUKA_ID, "properties": ["DEV_ST"]}] * 21, "at most 20 devices per request"),
        ],
        ids=["unknown-key", "too-many"],
    )
    async def test_subscription_rejects_a_bad_request(self, raw_client: RawClient, body: list[Any], msg: str) -> None:
        response = await raw_client.call("POST", "/v1/devices/subscriptions", json=body)

        assert (response["code"], response["msg"]) == (400, msg)
