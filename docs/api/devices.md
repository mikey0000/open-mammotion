# Devices

Tag "Mower information". Module `open_mammotion/api/devices.py`
(`DevicesApi`), models `open_mammotion/models/device.py`.

## `GET /v1/mowers` → `DevicesApi.list() -> list[DeviceInfo]`

`data` is a list of `DeviceInfo`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `id` | `device_id` | `str` | required; the `deviceId` used everywhere else (Q5) |
| `name` | `name` | `str | None` | device name, e.g. `Yuka-MV27…` |
| `nickname` | `nickname` | `str | None` | user-set |
| `model` | `model` | `str | None` | e.g. `YUKA mini Vision 800` |
| `icon` | `icon_url` | `str | None` | |
| `online` | `online` | `bool` | wire `1`/`0` → `bool` |

## `GET /v1/mower/{deviceId}` → `DevicesApi.get(device_id) -> DeviceDetail`

`DeviceDetail` has every `DeviceInfo` field plus:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `version` | `version` | `str | None` | firmware, e.g. `1.2.3.4` |
| `status` | `status` | `DeviceStatus | None` | tolerant `StrEnum`; `None` when absent, `UNKNOWN` when unrecognised |
| `batteryLevel` | `battery_level` | `int | None` | percent |
| `chargeStatus` | `charging` | `bool` | wire `1`/`0` |
| `network` | `network` | `Network | None` | |

`DeviceStatus` values (spec names, verbatim): `Standby`, `Working`, `Paused`,
`Mapping`, `Updating`, `Offline`, `Returning`, `Abnormal`, plus `UNKNOWN` for
anything else. Note the spec example is `StandBy` with a capital B; decode is
case-insensitive.

`Network`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `usedNetwork` | `used_network` | `NetworkType | None` | wire is the **string** `"1"` (Wi-Fi) or `"2"` (cellular); tolerant; `to_dict()` re-emits the string |
| `wifiAvailable` | `wifi_available` | `bool` | |
| `wifiRssi` | `wifi_rssi` | `int | None` | dBm |
| `wifiIp` | `wifi_ip` | `str | None` | |
| `cellularAvailable` | `cellular_available` | `bool` | |
| `cellularRssi` | `cellular_rssi` | `int | None` | dBm |

Note: the portal page shows `GET /v1/mower/{deviceId}` returning `data` as a
**list** with one element while `mower.json` says an object. `DevicesApi.get`
accepts both and returns the single object; an empty or longer list is a
`ContractError` (Q14). The fake server's `detail_as_list` knob produces the list
variant.
