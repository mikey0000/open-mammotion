"""Tag "Mower action command": the action endpoint, current work parameters and the task list.

Rule order for ``POST /v1/mower/action``: body validation (envelope ``400``), unknown device (``404``), then
``commandResult: false`` for ``START`` without ``params.taskName``, an offline device, or an unknown task.
Assumptions: an ``action`` outside the spec's enumeration is envelope ``400 "action is invalid"``; ``work-params``
on an offline device answers ``commandResult: false, "device offline"`` with no parameter fields. An accepted
action moves the device's ``status`` (e.g. ``PAUSE`` → ``Paused``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.fakeserver._common import MSG_TITLE_OK, BodyError, Field, fail, not_found, ok, read_json, validate
from tests.fakeserver.state import ACTIONS, ActionRecord

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeDevice, FakeState

_ACTION_REQ = (Field("deviceId", str, required=True), Field("action", str, required=True), Field("params", dict))
_PARAMS = (Field("taskName", str),)


def _verdict(device: FakeDevice, action: str, task_name: str | None) -> tuple[bool, str]:
    if action == "START" and not task_name:
        return False, "taskName is required"
    if not device.online:
        return False, "device offline"
    if action == "START" and task_name not in {t.task_name for t in device.tasks}:
        return False, "task not found"
    return True, "Success"


def register(app: web.Application, state: FakeState) -> None:
    async def action(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _ACTION_REQ)
            params = validate(body.get("params") or {}, _PARAMS, prefix="params.")
            if body["action"] not in ACTIONS:
                raise BodyError("action is invalid")
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if (device := state.devices.get(body["deviceId"])) is None:
            return not_found(state)
        task_name = params.get("taskName")
        accepted, message = _verdict(device, body["action"], task_name)
        state.actions.append(ActionRecord(device.device_id, body["action"], task_name, accepted, message))
        if accepted:
            state.apply_action(device, body["action"])
        return ok(state, {"commandResult": accepted, "resultMessage": message}, msg_title=MSG_TITLE_OK)

    async def work_params(request: web.Request) -> web.Response:
        if (device := state.devices.get(request.match_info["deviceId"])) is None:
            return not_found(state)
        if not device.online:
            return ok(state, {"commandResult": False, "resultMessage": "device offline"}, msg_title=MSG_TITLE_OK)
        return ok(state, dict(device.work_params), msg_title=MSG_TITLE_OK)

    async def plan(request: web.Request) -> web.Response:
        if (device := state.devices.get(request.match_info["deviceId"])) is None:
            return not_found(state)
        return ok(state, [t.wire() for t in device.tasks], msg_title=MSG_TITLE_OK)

    app.router.add_post("/v1/mower/action", action)
    app.router.add_get("/v1/mower/{deviceId}/work-params", work_params)
    app.router.add_get("/v1/mower/{deviceId}/plan", plan)
