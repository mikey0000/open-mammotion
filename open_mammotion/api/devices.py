"""``DevicesApi``: the "Mower information" device list and detail (``docs/api/devices.md``)."""

from __future__ import annotations

import builtins

from open_mammotion.api._base import ApiGroup
from open_mammotion.exceptions import ContractError
from open_mammotion.models.device import DeviceDetail, DeviceInfo


class DevicesApi(ApiGroup):
    """The devices bound to the developer account."""

    async def list(self) -> builtins.list[DeviceInfo]:
        """``GET /v1/mowers``: every device bound to the account."""
        return await self._get_list("/v1/mowers", DeviceInfo)

    async def get(self, device_id: str) -> DeviceDetail:
        """``GET /v1/mower/{deviceId}``: one device's detail and live state.

        The portal shows ``data`` as a one-element list and the spec as an object, so
        both are accepted.

        Raises:
            ValueError: ``device_id`` is empty; nothing is sent.
            ContractError: ``data`` is neither an object nor a one-element list.

        """
        path = self._mower_path(device_id)
        data = (await self._request("GET", path)).data
        if isinstance(data, builtins.list):
            if len(data) != 1:
                raise ContractError(DeviceDetail.__name__, f"{path}: expected one device, got {len(data)} elements")
            data = data[0]
        return self._decode(DeviceDetail, data, path=path)
