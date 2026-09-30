"""``/control``: fault-injection knobs and counters. Unauthenticated, never recorded, never delayed.

``POST`` takes any subset of the knobs below and answers like ``GET``: every knob's current value plus
``requests_total``, ``actions_total`` and ``token_grants``. ``reset`` is applied before the other knobs in the
same body. A bad knob answers HTTP 400 ``{"error": ...}`` and changes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from tests.fakeserver._common import CONTROL_PATH, json_response
from tests.fakeserver.state import InjectedEnvelope, InjectedStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiohttp import web

    from tests.fakeserver.state import FakeState


class KnobError(Exception):
    pass


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise KnobError(f"{name} must be a boolean")
    return value


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise KnobError(f"{name} must be an integer >= {minimum}")
    return value


def _status(value: object, name: str) -> InjectedStatus | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise KnobError(f"{name} must be an object or null")
    status = _int(value.get("status"), f"{name}.status", minimum=100)
    count = _int(value.get("count", 1), f"{name}.count", minimum=1)
    return InjectedStatus(status=status, count=count, non_json=_bool(value.get("non_json", False), f"{name}.non_json"))


def _envelope(value: object, name: str) -> InjectedEnvelope | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise KnobError(f"{name} must be an object or null")
    code = value.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise KnobError(f"{name}.code must be an integer")
    msg = value.get("msg", "injected failure")
    if not isinstance(msg, str):
        raise KnobError(f"{name}.msg must be a string")
    return InjectedEnvelope(code=code, msg=msg, count=_int(value.get("count", 1), f"{name}.count", minimum=1))


def _envelope_code(value: object, name: str) -> int:
    if isinstance(value, bool) or value not in {0, 200}:
        raise KnobError(f"{name} must be 0 or 200")
    return 0 if value == 0 else 200


def _snapshot(state: FakeState) -> dict[str, Any]:
    return {
        **state.knobs(),
        "requests_total": state.requests_total,
        "actions_total": len(state.actions),
        "token_grants": dict(state.token_grants),
    }


def _plan(state: FakeState, body: dict[str, Any]) -> list[Callable[[], None]]:
    """Validate every knob first, so a bad one leaves the state untouched."""
    steps: list[Callable[[], None]] = []
    for name, value in body.items():
        match name:
            case "reset" | "expire_tokens" if _bool(value, name) is False:
                pass
            case "reset":
                steps.insert(0, state.reset)
            case "expire_tokens":
                steps.append(state.expire_tokens)
            case "reject_next_refresh" | "reject_client_credentials" | "detail_as_list":
                flag = _bool(value, name)
                steps.append(lambda n=name, f=flag: setattr(state, n, f))
            case "next_status" | "token_next_status":
                fault = _status(value, name)
                steps.append(lambda n=name, f=fault: setattr(state, n, f))
            case "next_envelope":
                forced = _envelope(value, name)
                steps.append(lambda f=forced: setattr(state, "next_envelope", f))
            case "envelope_code":
                code = _envelope_code(value, name)
                steps.append(lambda c=code: setattr(state, "success_code", c))
            case "delay_ms":
                delay = _int(value, name)
                steps.append(lambda d=delay: setattr(state, "delay_ms", d))
            case "token_ttl_s":
                ttl = _int(value, name, minimum=1)
                steps.append(lambda t=ttl: setattr(state, "token_ttl_s", t))
            case _:
                raise KnobError(f"unknown knob: {name}")
    return steps


def register(app: web.Application, state: FakeState) -> None:
    async def get_control(request: web.Request) -> web.Response:
        return json_response(_snapshot(state))

    async def post_control(request: web.Request) -> web.Response:
        raw = await request.read()
        try:
            body = orjson.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise KnobError("body must be a JSON object")
            steps = _plan(state, body)
        except (orjson.JSONDecodeError, KnobError) as exc:
            return json_response({"error": str(exc)}, status=400)
        for step in steps:
            step()
        return json_response(_snapshot(state))

    app.router.add_get(CONTROL_PATH, get_control)
    app.router.add_post(CONTROL_PATH, post_control)
