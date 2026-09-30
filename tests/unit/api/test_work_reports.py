from __future__ import annotations

import pytest

from open_mammotion.api.work_reports import WorkReportsApi
from open_mammotion.exceptions import ContractError
from open_mammotion.models.work_report import WorkReportQuery, WorkResult, WorkType
from tests.unit._fakes import FakeRequester, RecordedCall
from tests.unit.models._helpers import work_report_detail_json, work_report_json

SUMMARY_PATH = "/v1/mower/work-reports/summary"
SEARCH_PATH = "/v1/mower/work-reports/search"


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def api(requester: FakeRequester) -> WorkReportsApi:
    return WorkReportsApi(requester)


class TestSummary:
    async def test_posts_the_query_and_returns_the_summary(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        requester.on(
            "POST", SUMMARY_PATH, {"saveTime": 90.0, "carbonReduction": 10.5, "workCount": 3, "totalWorkArea": 900.0}
        )

        summary = await api.summary(WorkReportQuery(device_id="dev-1", work_type=WorkType.SINGLE))

        assert summary.work_count == 3
        assert requester.calls == [
            RecordedCall("POST", SUMMARY_PATH, {"deviceId": "dev-1", "pageSize": 10, "pageNumber": 1, "workType": 1})
        ]

    async def test_rejects_an_empty_device_id_before_io(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await api.summary(WorkReportQuery(device_id=""))

        assert requester.calls == []

    async def test_raises_contract_error_when_data_is_not_an_object(
        self, api: WorkReportsApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", SUMMARY_PATH, [1, 2])

        with pytest.raises(ContractError):
            await api.summary(WorkReportQuery(device_id="dev-1"))


class TestSearch:
    async def test_posts_the_query_and_returns_the_page(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        requester.on(
            "POST",
            SEARCH_PATH,
            {"records": [work_report_json()], "total": 1, "pageNumber": 2, "pageSize": 5, "pages": 1},
        )

        page = await api.search(
            WorkReportQuery(device_id="dev-1", page_size=5, page_number=2, work_result=WorkResult.COMPLETED)
        )

        assert [r.work_id for r in page.records] == ["work-1"]
        assert requester.calls == [
            RecordedCall("POST", SEARCH_PATH, {"deviceId": "dev-1", "pageSize": 5, "pageNumber": 2, "workResult": 5})
        ]

    async def test_rejects_an_empty_device_id_before_io(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await api.search(WorkReportQuery(device_id=""))

        assert requester.calls == []

    async def test_raises_contract_error_on_a_record_without_a_work_id(
        self, api: WorkReportsApi, requester: FakeRequester
    ) -> None:
        record = work_report_json()
        del record["workId"]
        requester.on("POST", SEARCH_PATH, {"records": [record]})

        with pytest.raises(ContractError, match=r'WorkReportPage: .*field "records"'):
            await api.search(WorkReportQuery(device_id="dev-1"))


class TestGet:
    async def test_gets_the_detail_by_device_and_work_id(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/mower/dev-1/work-reports/work-1", work_report_detail_json())

        detail = await api.get("dev-1", "work-1")

        assert detail.duration_s == 5400
        assert requester.calls == [RecordedCall("GET", "/v1/mower/dev-1/work-reports/work-1", None)]

    async def test_url_encodes_both_path_segments(self, api: WorkReportsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/mower/dev%2F1/work-reports/work%3F1", work_report_detail_json())

        await api.get("dev/1", "work?1")

        assert [c.path for c in requester.calls] == ["/v1/mower/dev%2F1/work-reports/work%3F1"]

    @pytest.mark.parametrize(("device_id", "work_id", "named"), [("", "work-1", "device_id"), ("dev-1", "", "work_id")])
    async def test_rejects_an_empty_id_before_io(
        self, api: WorkReportsApi, requester: FakeRequester, device_id: str, work_id: str, named: str
    ) -> None:
        with pytest.raises(ValueError, match=named):
            await api.get(device_id, work_id)

        assert requester.calls == []

    async def test_raises_contract_error_on_a_wrongly_typed_field(
        self, api: WorkReportsApi, requester: FakeRequester
    ) -> None:
        requester.on("GET", "/v1/mower/dev-1/work-reports/work-1", work_report_detail_json(workProcess="soon"))

        with pytest.raises(ContractError, match='field "events"'):
            await api.get("dev-1", "work-1")
