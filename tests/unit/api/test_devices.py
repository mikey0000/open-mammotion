from __future__ import annotations

import pytest

from open_mammotion.api.devices import DevicesApi
from open_mammotion.exceptions import ContractError
from open_mammotion.models.device import DeviceDetail, DeviceInfo, DeviceStatus
from tests.unit._fakes import FakeRequester, RecordedCall
from tests.unit.models._helpers import device_detail_json, device_info_json


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def devices(requester: FakeRequester) -> DevicesApi:
    return DevicesApi(requester)


class TestList:
    async def test_gets_the_mower_list(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mowers", [device_info_json()])

        await devices.list()

        assert requester.calls == [RecordedCall("GET", "/v1/mowers", None)]

    async def test_returns_every_device(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mowers", [device_info_json(), device_info_json(id="456", online=0)])

        result = await devices.list()

        assert [d.device_id for d in result] == ["123", "456"]
        assert all(type(d) is DeviceInfo for d in result)
        assert [d.online for d in result] == [True, False]

    async def test_returns_empty_for_null_data(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mowers", None)

        assert await devices.list() == []

    async def test_raises_contract_error_for_an_object(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mowers", device_info_json())

        with pytest.raises(ContractError, match="expected a list") as caught:
            await devices.list()

        assert caught.value.model == "DeviceInfo"

    async def test_raises_contract_error_naming_a_missing_id(
        self, requester: FakeRequester, devices: DevicesApi
    ) -> None:
        body = device_info_json()
        del body["id"]
        requester.on("GET", "/v1/mowers", [body])

        with pytest.raises(ContractError, match="device_id") as caught:
            await devices.list()

        assert caught.value.model == "DeviceInfo"


class TestGet:
    async def test_gets_the_mower_by_id(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mower/123", device_detail_json())

        await devices.get("123")

        assert requester.calls == [RecordedCall("GET", "/v1/mower/123", None)]

    async def test_url_encodes_the_device_id(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mower/a%2Fb%20c", device_detail_json())

        await devices.get("a/b c")

        assert requester.calls[0].path == "/v1/mower/a%2Fb%20c"

    async def test_decodes_an_object(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mower/123", device_detail_json())

        detail = await devices.get("123")

        assert detail == DeviceDetail.from_dict(device_detail_json())
        assert detail.status is DeviceStatus.STANDBY

    async def test_decodes_a_one_element_list(self, requester: FakeRequester, devices: DevicesApi) -> None:
        requester.on("GET", "/v1/mower/123", [device_detail_json()])

        assert await devices.get("123") == DeviceDetail.from_dict(device_detail_json())

    @pytest.mark.parametrize("data", [[], [device_detail_json(), device_detail_json(id="456")]])
    async def test_raises_contract_error_unless_the_list_has_one_element(
        self, requester: FakeRequester, devices: DevicesApi, data: list[object]
    ) -> None:
        requester.on("GET", "/v1/mower/123", data)

        with pytest.raises(ContractError, match=f"{len(data)} elements") as caught:
            await devices.get("123")

        assert caught.value.model == "DeviceDetail"

    @pytest.mark.parametrize("data", [None, "123", 7])
    async def test_raises_contract_error_for_a_non_object(
        self, requester: FakeRequester, devices: DevicesApi, data: object
    ) -> None:
        requester.on("GET", "/v1/mower/123", data)

        with pytest.raises(ContractError, match="expected an object"):
            await devices.get("123")

    async def test_raises_contract_error_naming_a_missing_id(
        self, requester: FakeRequester, devices: DevicesApi
    ) -> None:
        body = device_detail_json()
        del body["id"]
        requester.on("GET", "/v1/mower/123", body)

        with pytest.raises(ContractError, match="device_id"):
            await devices.get("123")

    async def test_rejects_an_empty_device_id_before_any_request(
        self, requester: FakeRequester, devices: DevicesApi
    ) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await devices.get("")

        assert requester.calls == []
