"""``ApiGroup``: the path helper, the identifier guard and the typed decode helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from mashumaro.types import Alias
import pytest

from open_mammotion.api._base import ApiGroup
from open_mammotion.exceptions import ContractError
from open_mammotion.models.common import WireModel
from tests.unit._fakes import FakeRequester


@dataclass(frozen=True)
class Thing(WireModel):
    thing_id: Annotated[str, Alias("id")]
    size: int = 0


class ThingsApi(ApiGroup):
    async def one(self, thing_id: str) -> Thing:
        return await self._get(self._mower_path(thing_id, "thing"), Thing)

    async def many(self) -> list[Thing]:
        return await self._get_list("/v1/things", Thing)

    async def make(self, size: int) -> Thing:
        return await self._post("/v1/things", {"size": size}, Thing)


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def api(requester: FakeRequester) -> ThingsApi:
    return ThingsApi(requester)


class TestMowerPath:
    def test_joins_encoded_segments_under_the_mower_prefix(self) -> None:
        assert ApiGroup._mower_path("dev 1", "work-reports", "w/2") == "/v1/mower/dev%201/work-reports/w%2F2"

    @pytest.mark.parametrize("device_id", ["", ".", ".."])
    def test_refuses_an_id_that_cannot_address_a_device(self, device_id: str) -> None:
        with pytest.raises(ValueError, match="device_id"):
            ApiGroup._mower_path(device_id)

    def test_require_names_the_argument(self) -> None:
        with pytest.raises(ValueError, match="work_id"):
            ApiGroup._require("", "work_id")


class TestDecode:
    async def test_decodes_an_object(self, api: ThingsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/mower/t1/thing", {"id": "t1", "size": 3, "extra": True})

        assert await api.one("t1") == Thing(thing_id="t1", size=3)

    async def test_decodes_a_list_and_treats_null_as_empty(self, api: ThingsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/things", [{"id": "a"}, {"id": "b"}], None)

        assert [t.thing_id for t in await api.many()] == ["a", "b"]
        assert await api.many() == []

    async def test_post_sends_the_payload(self, api: ThingsApi, requester: FakeRequester) -> None:
        requester.on("POST", "/v1/things", {"id": "n", "size": 9})

        assert (await api.make(9)).size == 9
        assert requester.calls[0].json == {"size": 9}

    async def test_wrong_shape_is_a_contract_error_naming_the_path(
        self, api: ThingsApi, requester: FakeRequester
    ) -> None:
        requester.on("GET", "/v1/mower/t1/thing", [1, 2])
        requester.on("GET", "/v1/things", {"id": "not-a-list"})

        with pytest.raises(ContractError, match=r"Thing: /v1/mower/t1/thing: expected an object"):
            await api.one("t1")
        with pytest.raises(ContractError, match=r"Thing: /v1/things: expected a list"):
            await api.many()

    async def test_missing_field_is_named_without_the_body(self, api: ThingsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/mower/t1/thing", {"size": 1, "secretish": "do-not-echo"})

        with pytest.raises(ContractError, match='field "thing_id" is missing') as info:
            await api.one("t1")

        assert "do-not-echo" not in str(info.value)
        assert info.value.__cause__ is None

    async def test_invalid_value_is_named_without_the_value(self, api: ThingsApi, requester: FakeRequester) -> None:
        requester.on("GET", "/v1/mower/t1/thing", {"id": "t1", "size": "do-not-echo"})

        with pytest.raises(ContractError, match='field "size" has an invalid value') as info:
            await api.one("t1")

        assert "do-not-echo" not in str(info.value)
