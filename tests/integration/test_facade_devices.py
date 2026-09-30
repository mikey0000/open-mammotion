"""``OpenMammotion.devices`` against the fake cloud's two seed mowers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from open_mammotion import ApiError, DeviceStatus
from open_mammotion.models.device import NetworkType
from tests.fakeserver.state import LUBA_ID, LUBA_NAME, YUKA_ID, YUKA_NAME
from tests.integration._fakeserver_client import bounded
from tests.integration._helpers import secrets_in_text

if TYPE_CHECKING:
    from open_mammotion import OpenMammotion
    from tests.fakeserver.server import FakeCloud


class TestList:
    async def test_returns_both_seed_devices_with_ids_names_and_online_flags(self, api: OpenMammotion) -> None:
        devices = await bounded(api.devices.list())

        assert [(d.device_id, d.name, d.online) for d in devices] == [
            (YUKA_ID, YUKA_NAME, True),
            (LUBA_ID, LUBA_NAME, False),
        ]


class TestGet:
    async def test_returns_the_live_state_of_the_online_yuka(self, api: OpenMammotion) -> None:
        detail = await bounded(api.devices.get(YUKA_ID))

        assert (detail.device_id, detail.name, detail.online) == (YUKA_ID, YUKA_NAME, True)
        assert detail.status is DeviceStatus.STANDBY
        assert detail.battery_level == 87
        assert detail.charging is True
        assert detail.version == "1.2.3.4"
        assert detail.network is not None
        assert detail.network.used_network is NetworkType.WIFI
        assert (detail.network.wifi_available, detail.network.wifi_rssi) == (True, -46)
        assert detail.network.wifi_ip == "192.168.1.100"
        assert detail.network.cellular_available is False

    async def test_reports_the_offline_luba_on_cellular(self, api: OpenMammotion) -> None:
        detail = await bounded(api.devices.get(LUBA_ID))

        assert (detail.online, detail.status, detail.charging) == (False, DeviceStatus.OFFLINE, False)
        assert detail.network is not None
        assert (detail.network.used_network, detail.network.cellular_rssi) == (NetworkType.CELLULAR, -71)

    async def test_a_one_element_list_decodes_to_the_same_detail(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        """Q14: the portal shows ``data`` as a one-element list, the spec as an object."""
        as_object = await bounded(api.devices.get(YUKA_ID))
        await bounded(fake_cloud.control(detail_as_list=True))

        as_list = await bounded(api.devices.get(YUKA_ID))

        assert as_list == as_object

    async def test_an_unknown_device_raises_api_error_404_with_the_request_id(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        with pytest.raises(ApiError) as caught:
            await bounded(api.devices.get("no-such-mower"))

        assert caught.value.code == 404
        assert caught.value.msg == "device not found"
        assert caught.value.request_id is not None
        assert caught.value.request_id.startswith("fake-req-")
        assert not secrets_in_text(str(caught.value), fake_cloud)
