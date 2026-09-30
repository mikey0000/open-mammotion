"""``POST /v1/mower/error-codes/search``: the per-device fault history, paginated, newest first.

Assumptions: ``startDate``/``endDate`` are compared with the UTC calendar date of ``gmtCreate``; ``errorCode``
is a substring match on the decimal code; a malformed date is envelope ``400 "<field> is invalid"``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from tests.fakeserver._common import BodyError, Field, fail, not_found, ok, page_params, read_json, validate

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeFault, FakeState

_QUERY = (
    Field("deviceId", str, required=True),
    Field("pageSize", int),
    Field("pageNumber", int),
    Field("startDate", str),
    Field("endDate", str),
    Field("errorCode", str),
)


def _date(body: dict[str, Any], name: str) -> date | None:
    if (raw := body.get(name)) is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise BodyError(f"{name} is invalid") from exc


def _raised_on(fault: FakeFault) -> date:
    return datetime.fromtimestamp(fault.gmt_create_ms / 1000, tz=UTC).date()


def register(app: web.Application, state: FakeState) -> None:
    async def search(request: web.Request) -> web.Response:
        try:
            body = validate(await read_json(request), _QUERY)
            number, size = page_params(body)
            start, end = _date(body, "startDate"), _date(body, "endDate")
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if body["deviceId"] not in state.devices:
            return not_found(state)
        keyword = body.get("errorCode") or ""
        found = [
            f
            for f in state.faults
            if f.device_id == body["deviceId"]
            and (start is None or _raised_on(f) >= start)
            and (end is None or _raised_on(f) <= end)
            and keyword in str(f.code)
        ]
        found.sort(key=lambda f: f.gmt_create_ms, reverse=True)
        page = found[(number - 1) * size : number * size]
        return ok(
            state,
            {
                "records": [f.wire() for f in page],
                "total": len(found),
                "pageNumber": number,
                "pageSize": size,
                "hasMore": number * size < len(found),
            },
        )

    app.router.add_post("/v1/mower/error-codes/search", search)
