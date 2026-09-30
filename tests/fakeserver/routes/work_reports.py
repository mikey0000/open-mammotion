"""Tag "Mower work report": summary, paginated search and detail.

Search and summary share the filters (``workType``, ``workResult``, inclusive ``endWorkTimeStart``/``End``).
Search orders newest ``endWorkTime`` first. Assumption: an unknown ``workId`` is envelope ``404 "work report not
found"``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from tests.fakeserver._common import BodyError, Field, fail, not_found, ok, page_params, read_json, validate

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeState, FakeWorkReport

_QUERY = (
    Field("deviceId", str, required=True),
    Field("pageSize", int),
    Field("pageNumber", int),
    Field("endWorkTimeStart", int),
    Field("endWorkTimeEnd", int),
    Field("workType", int),
    Field("workResult", int),
)


def _matches(report: FakeWorkReport, query: dict[str, Any]) -> bool:
    if report.device_id != query["deviceId"]:
        return False
    if (work_type := query.get("workType")) is not None and report.work_type != work_type:
        return False
    if (result := query.get("workResult")) is not None and report.work_result != result:
        return False
    if (start := query.get("endWorkTimeStart")) is not None and report.end_ms < start:
        return False
    return (end := query.get("endWorkTimeEnd")) is None or report.end_ms <= end


def register(app: web.Application, state: FakeState) -> None:
    async def parse(request: web.Request) -> dict[str, Any] | web.Response:
        try:
            body = validate(await read_json(request), _QUERY)
            page_params(body)
        except BodyError as exc:
            return fail(state, 400, exc.msg)
        if body["deviceId"] not in state.devices:
            return not_found(state)
        return body

    def matching(query: dict[str, Any]) -> list[FakeWorkReport]:
        found = [r for r in state.work_reports if _matches(r, query)]
        return sorted(found, key=lambda r: r.end_ms, reverse=True)

    async def summary(request: web.Request) -> web.Response:
        if not isinstance(query := await parse(request), dict):
            return query
        reports = matching(query)
        return ok(
            state,
            {
                "saveTime": round(sum(r.save_time_min for r in reports), 1),
                "carbonReduction": round(sum(r.carbon_g for r in reports), 1),
                "workCount": len(reports),
                "totalWorkArea": round(sum(r.area_m2 for r in reports), 1),
            },
        )

    async def search(request: web.Request) -> web.Response:
        if not isinstance(query := await parse(request), dict):
            return query
        number, size = page_params(query)
        reports = matching(query)
        page = reports[(number - 1) * size : number * size]
        return ok(
            state,
            {
                "records": [r.record() for r in page],
                "total": len(reports),
                "pageNumber": number,
                "pageSize": size,
                "pages": math.ceil(len(reports) / size),
            },
        )

    async def detail(request: web.Request) -> web.Response:
        device_id, work_id = request.match_info["deviceId"], request.match_info["workId"]
        if device_id not in state.devices:
            return not_found(state)
        report = next((r for r in state.work_reports if r.device_id == device_id and r.work_id == work_id), None)
        if report is None:
            return not_found(state, "work report")
        return ok(state, report.detail())

    app.router.add_post("/v1/mower/work-reports/summary", summary)
    app.router.add_post("/v1/mower/work-reports/search", search)
    app.router.add_get("/v1/mower/{deviceId}/work-reports/{workId}", detail)
