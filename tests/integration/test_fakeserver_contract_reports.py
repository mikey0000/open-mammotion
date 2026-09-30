"""Work-report and fault-history routes on the fake cloud: pagination and filters.

These pin the fake itself (docs/testing.md §6) with a raw client, so the facade's integration tests can trust it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.fakeserver.state import YUKA_ID
from tests.integration._fakeserver_client import ENVELOPE_KEYS

if TYPE_CHECKING:
    from tests.integration._fakeserver_client import RawClient


class TestWorkReports:
    async def search(self, raw_client: RawClient, **query: Any) -> dict[str, Any]:
        return await raw_client.data("POST", "/v1/mower/work-reports/search", json={"deviceId": YUKA_ID, **query})

    async def test_paginates_newest_first_with_default_page_size(self, raw_client: RawClient) -> None:
        first = await self.search(raw_client)
        second = await self.search(raw_client, pageNumber=2)

        assert (first["total"], first["pages"], first["pageSize"], len(first["records"])) == (12, 2, 10, 10)
        assert len(second["records"]) == 2
        ends = [r["endWorkTime"] for r in first["records"] + second["records"]]
        assert ends == sorted(ends, reverse=True)
        assert set(first["records"][0]) == {
            "workId", "endWorkTime", "workType", "workResult", "workProgress", "workArea", "workTimeUsed",
        }  # fmt: skip

    async def test_filters_on_work_type_and_result(self, raw_client: RawClient) -> None:
        page = await self.search(raw_client, workType=2, workResult=5)

        assert page["total"] == 3
        assert {(r["workType"], r["workResult"]) for r in page["records"]} == {(2, 5)}

    async def test_filters_on_an_inclusive_end_time_range(self, raw_client: RawClient) -> None:
        everything = (await self.search(raw_client, pageSize=20))["records"]
        low, high = everything[4]["endWorkTime"], everything[2]["endWorkTime"]

        page = await self.search(raw_client, endWorkTimeStart=low, endWorkTimeEnd=high)

        assert [r["workId"] for r in page["records"]] == [r["workId"] for r in everything[2:5]]

    async def test_summary_aggregates_the_filtered_reports(self, raw_client: RawClient) -> None:
        body = await raw_client.call(
            "POST", "/v1/mower/work-reports/summary", json={"deviceId": YUKA_ID, "workType": 2, "workResult": 5}
        )
        summary = body["data"]

        assert set(body) == ENVELOPE_KEYS
        assert set(summary) == {"saveTime", "carbonReduction", "workCount", "totalWorkArea"}
        assert summary["workCount"] == 3

    async def test_returns_a_full_detail(self, raw_client: RawClient) -> None:
        detail = await raw_client.data("GET", f"/v1/mower/{YUKA_ID}/work-reports/work-yuka-0001")

        assert set(detail) == {
            "workArea", "workTimeUsed", "saveTime", "carbonReduction", "energyConsume", "startWorkTime",
            "endWorkTime", "workType", "jobContent", "workProcess", "workParam", "mapFilePath",
        }  # fmt: skip
        assert set(detail["workProcess"][0]) == {"timeStamp", "eventCode"}

    async def test_unknown_work_id_is_envelope_404(self, raw_client: RawClient) -> None:
        body = await raw_client.call("GET", f"/v1/mower/{YUKA_ID}/work-reports/nope")

        assert (body["code"], body["msg"]) == (404, "work report not found")

    @pytest.mark.parametrize(
        ("query", "msg"),
        [
            ({"pageSize": 5}, "deviceId is required"),
            ({"deviceId": YUKA_ID, "pageNumber": 0}, "pageNumber is invalid"),
            ({"deviceId": YUKA_ID, "pageSize": -1}, "pageSize is invalid"),
        ],
        ids=["no-device", "page-zero", "negative-size"],
    )
    async def test_bad_query_is_envelope_400(self, raw_client: RawClient, query: dict[str, Any], msg: str) -> None:
        body = await raw_client.call("POST", "/v1/mower/work-reports/search", json=query)

        assert (body["code"], body["msg"]) == (400, msg)


class TestFaults:
    async def search(self, raw_client: RawClient, **query: Any) -> dict[str, Any]:
        return await raw_client.data("POST", "/v1/mower/error-codes/search", json={"deviceId": YUKA_ID, **query})

    async def test_paginates_with_has_more(self, raw_client: RawClient) -> None:
        first = await self.search(raw_client, pageSize=2)
        last = await self.search(raw_client, pageSize=2, pageNumber=3)

        assert (first["total"], first["hasMore"], len(first["records"])) == (5, True, 2)
        assert (last["hasMore"], len(last["records"])) == (False, 1)
        assert set(first["records"][0]) == {
            "code", "implication", "solution", "gmtCreate", "createTime", "faultLevel", "priority", "imageList",
            "videoList", "buttonList",
        }  # fmt: skip

    async def test_filters_on_an_inclusive_date_range(self, raw_client: RawClient) -> None:
        page = await self.search(raw_client, startDate="2025-09-27", endDate="2025-09-29")

        assert [r["code"] for r in page["records"]] == [1301, 2711]

    async def test_filters_on_an_error_code_keyword(self, raw_client: RawClient) -> None:
        page = await self.search(raw_client, errorCode="130")

        assert sorted(r["code"] for r in page["records"]) == [1301, 1302]

    async def test_malformed_date_is_envelope_400(self, raw_client: RawClient) -> None:
        body = await raw_client.call(
            "POST", "/v1/mower/error-codes/search", json={"deviceId": YUKA_ID, "startDate": "x"}
        )

        assert (body["code"], body["msg"]) == (400, "startDate is invalid")
