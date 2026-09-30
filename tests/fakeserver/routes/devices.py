"""Tag "Mower information": device list and detail, material fetch and property subscriptions.

Assumptions: ``material/fetch`` on an offline device answers ``commandResult: false, "device offline"``;
``subscriptions`` rejects more than 20 devices or an unlisted property key with envelope ``code: 400``, and
does not enforce the "LUBA 3 AWD only" model restriction (Q9). There is no SSE stream yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.fakeserver._common import MSG_TITLE_OK, BodyError, Field, fail, not_found, ok, read_json, validate
from tests.fakeserver.state import MAX_SUBSCRIPTION_DEVICES, SUBSCRIPTION_KEYS

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeState

_MATERIAL_REQ = (Field("deviceIds", list, required=True),)
_SUBSCRIPTION_ITEM = (Field("deviceId", str, required=True), Field("properties", list, required=True))


def register(app: web.Application, state: FakeState) -> None:
    async def list_mowers(request: web.Request) -> web.Response:
        return ok(state, [d.info() for d in state.devices.values()], msg_title=MSG_TITLE_OK)

    async def get_mower(request: web.Request) -> web.Response:
        if (device := state.devices.get(request.match_info["deviceId"])) is None:
            return not_found(state)
        detail = device.detail()
        return ok(state, [detail] if state.detail_as_list else detail, msg_title=MSG_TITLE_OK)

    async def fetch_material(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _MATERIAL_REQ)
            ids = body["deviceIds"]
            if not ids or not all(isinstance(i, str) and i for i in ids):
                raise BodyError("deviceIds is invalid")
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if any(i not in state.devices for i in ids):
            return not_found(state)
        offline = [i for i in ids if not state.devices[i].online]
        if offline:
            return ok(state, {"commandResult": False, "resultMessage": "device offline"})
        return ok(state, {"commandResult": True, "resultMessage": "ok"})

    async def subscribe(request: web.Request) -> web.Response:
        try:
            body = await read_json(request)
            if not isinstance(body, list) or not body:
                raise BodyError("body is invalid")
            if len(body) > MAX_SUBSCRIPTION_DEVICES:
                raise BodyError(f"at most {MAX_SUBSCRIPTION_DEVICES} devices per request")
            for index, item in enumerate(body):
                validate(item, _SUBSCRIPTION_ITEM, prefix=f"[{index}].")
                props = item["properties"]
                if not props or not all(isinstance(p, str) and p in SUBSCRIPTION_KEYS for p in props):
                    raise BodyError(f"[{index}].properties is invalid")
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if any(item["deviceId"] not in state.devices for item in body):
            return not_found(state)
        for item in body:
            state.subscriptions[item["deviceId"]] = list(item["properties"])
        return ok(state, {"commandResult": True, "resultMessage": "ok"}, msg_title=MSG_TITLE_OK)

    app.router.add_get("/v1/mowers", list_mowers)
    app.router.add_get("/v1/mower/{deviceId}", get_mower)
    app.router.add_post("/v1/mower/material/fetch", fetch_material)
    app.router.add_post("/v1/devices/subscriptions", subscribe)
