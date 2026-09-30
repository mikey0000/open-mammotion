"""Tag "HA local network" plus ``POST /v1/mower/ws/ticket``.

Assumptions: ``save`` upserts per ``(clientId, deviceName)`` and dispatches at once — ``dispatchStatus`` 1 for an
online device, 2 with ``failReason: "device offline"`` otherwise; ``clientId`` is not checked against the
token's client. ``query`` for a known but unconfigured device is an empty list. The ticket rejects a
``timestamp`` more than ``TICKET_MAX_SKEW_S`` from the server clock with envelope ``400 "timestamp is invalid"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.fakeserver._common import BodyError, Field, current_token, fail, not_found, ok, read_json, validate
from tests.fakeserver.state import FakeLocalConfig, sign_ticket

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeDevice, FakeState

TICKET_MAX_SKEW_S = 300

_SAVE_REQ = (Field("clientId", str, required=True), Field("redirectUri", str), Field("devices", list, required=True))
_SAVE_ITEM = (Field("deviceName", str, required=True), Field("enabled", int, required=True))
_QUERY_REQ = (Field("clientId", str, required=True), Field("deviceName", str))
_TICKET_REQ = (Field("deviceName", str, required=True), Field("timestamp", int, required=True), Field("ip", str))


def register(app: web.Application, state: FakeState) -> None:
    def upsert(client_id: str, redirect_uri: str | None, device: FakeDevice, enabled: int) -> FakeLocalConfig:
        config = next(
            (c for c in state.local_configs if c.client_id == client_id and c.device_name == device.name), None
        )
        if config is None:
            config = FakeLocalConfig(device.name, client_id, None, 0, 0, None)
            state.local_configs.append(config)
        config.redirect_uri = redirect_uri
        config.enabled = enabled
        config.dispatch_status = 1 if device.online else 2
        config.fail_reason = None if device.online else "device offline"
        return config

    async def save(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _SAVE_REQ)
            if not body["devices"]:
                raise BodyError("devices is required")
            for index, item in enumerate(body["devices"]):
                validate(item, _SAVE_ITEM, prefix=f"devices[{index}].")
                if item["enabled"] not in {0, 1}:
                    raise BodyError(f"devices[{index}].enabled is invalid")
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        targets = [(state.device_by_name(item["deviceName"]), item["enabled"]) for item in body["devices"]]
        resolved = [(device, enabled) for device, enabled in targets if device is not None]
        if len(resolved) != len(targets):
            return not_found(state)
        saved = [upsert(body["clientId"], body.get("redirectUri"), device, enabled) for device, enabled in resolved]
        return ok(state, [c.wire() for c in saved])

    async def query(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _QUERY_REQ)
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        name = body.get("deviceName")
        if name is not None and state.device_by_name(name) is None:
            return not_found(state)
        found = [
            c.wire()
            for c in state.local_configs
            if c.client_id == body["clientId"] and (name is None or c.device_name == name)
        ]
        return ok(state, found)

    async def ws_ticket(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _TICKET_REQ)
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if (device := state.device_by_name(body["deviceName"])) is None:
            return not_found(state)
        now = state.clock()
        if abs(body["timestamp"] - now) > TICKET_MAX_SKEW_S:
            return fail(state, 400, "timestamp is invalid")
        token = current_token(request)
        ticket: dict[str, Any] = {
            "ticketId": f"tkt-{state.next_serial():06d}",
            "productKey": device.product_key,
            "deviceName": device.name,
            "userId": state.user_id,
            "clientId": token.client_id,
            "allowedIp": body.get("ip") or "",
            "iat": int(now),
            "exp": int(token.expires_at),
        }
        ticket["sign"] = sign_ticket(ticket)
        return ok(state, ticket)

    app.router.add_post("/v1/ha/local-network/save", save)
    app.router.add_post("/v1/ha/local-network/query", query)
    app.router.add_post("/v1/mower/ws/ticket", ws_ticket)
