from __future__ import annotations

from datetime import date

import pytest

from open_mammotion.api.faults import FaultsApi
from open_mammotion.exceptions import ContractError
from open_mammotion.models.fault import FaultQuery
from tests.unit._fakes import FakeRequester, RecordedCall
from tests.unit.models._helpers import fault_json

SEARCH_PATH = "/v1/mower/error-codes/search"


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def api(requester: FakeRequester) -> FaultsApi:
    return FaultsApi(requester)


class TestSearch:
    async def test_posts_the_query_and_returns_the_page(self, api: FaultsApi, requester: FakeRequester) -> None:
        requester.on(
            "POST",
            SEARCH_PATH,
            {"records": [fault_json()], "total": 1, "pageNumber": 1, "pageSize": 10, "hasMore": False},
        )

        page = await api.search(FaultQuery(device_id="dev-1", start_date=date(2024, 9, 1)))

        assert [f.code for f in page.records] == [1005]
        assert requester.calls == [
            RecordedCall(
                "POST", SEARCH_PATH, {"deviceId": "dev-1", "pageSize": 10, "pageNumber": 1, "startDate": "2024-09-01"}
            )
        ]

    async def test_rejects_an_empty_device_id_before_io(self, api: FaultsApi, requester: FakeRequester) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await api.search(FaultQuery(device_id=""))

        assert requester.calls == []

    async def test_raises_contract_error_on_a_record_without_a_code(
        self, api: FaultsApi, requester: FakeRequester
    ) -> None:
        record = fault_json()
        del record["code"]
        requester.on("POST", SEARCH_PATH, {"records": [record]})

        with pytest.raises(ContractError, match=r'FaultPage: .*field "records"'):
            await api.search(FaultQuery(device_id="dev-1"))

    async def test_raises_contract_error_when_data_is_not_an_object(
        self, api: FaultsApi, requester: FakeRequester
    ) -> None:
        requester.on("POST", SEARCH_PATH, "none")

        with pytest.raises(ContractError):
            await api.search(FaultQuery(device_id="dev-1"))
