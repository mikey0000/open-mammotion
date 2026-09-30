"""Device list and detail models: ``DeviceInfo``, ``DeviceDetail``, ``Network`` (``docs/api/devices.md``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from mashumaro.types import Alias

from open_mammotion.models.common import TolerantIntEnum, TolerantStrEnum, WireModel, int_bool

_USED_NETWORK = "usedNetwork"


class DeviceStatus(TolerantStrEnum):
    """``status`` of a device detail; the spec's names verbatim, matched case-insensitively."""

    STANDBY = "Standby"
    WORKING = "Working"
    PAUSED = "Paused"
    MAPPING = "Mapping"
    UPDATING = "Updating"
    OFFLINE = "Offline"
    RETURNING = "Returning"
    ABNORMAL = "Abnormal"
    UNKNOWN = "UNKNOWN"


class NetworkType(TolerantIntEnum):
    """``usedNetwork``: which link the mower is on."""

    UNKNOWN = -1
    WIFI = 1
    CELLULAR = 2


@dataclass(frozen=True)
class Network(WireModel):
    """The connectivity block of a device detail. RSSI values are dBm."""

    used_network: Annotated[NetworkType | None, Alias(_USED_NETWORK)] = None
    wifi_available: Annotated[bool, Alias("wifiAvailable")] = False
    wifi_rssi: Annotated[int | None, Alias("wifiRssi")] = None
    wifi_ip: Annotated[str | None, Alias("wifiIp")] = None
    cellular_available: Annotated[bool, Alias("cellularAvailable")] = False
    cellular_rssi: Annotated[int | None, Alias("cellularRssi")] = None

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        # The wire sends ``usedNetwork`` as the string "1"/"2".
        if isinstance(value := d.get(_USED_NETWORK), str) and value.strip().lstrip("-").isdigit():
            d = {**d, _USED_NETWORK: int(value)}
        return d

    def __post_serialize__(self, d: dict[Any, Any]) -> dict[Any, Any]:
        if (value := d.get(_USED_NETWORK)) is not None:
            d[_USED_NETWORK] = str(value)
        return d


@dataclass(frozen=True)
class DeviceInfo(WireModel):
    """One entry of ``GET /v1/mowers``. ``device_id`` is opaque (Q5)."""

    device_id: Annotated[str, Alias("id")]
    name: str | None = None
    nickname: str | None = None
    model: str | None = None
    icon_url: Annotated[str | None, Alias("icon")] = None
    online: bool = int_bool()


@dataclass(frozen=True)
class DeviceDetail(DeviceInfo):
    """``GET /v1/mower/{deviceId}``: every ``DeviceInfo`` field plus live state."""

    version: str | None = None
    status: DeviceStatus | None = None
    battery_level: Annotated[int | None, Alias("batteryLevel")] = None
    charging: Annotated[bool, Alias("chargeStatus")] = int_bool()
    network: Network | None = None
