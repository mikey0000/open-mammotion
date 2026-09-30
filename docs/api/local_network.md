# HA local network and the LAN WebSocket ticket

Tags "HA local network" and (for the ticket) "Mower action command". Module
`open_mammotion/api/local_network.py` (`LocalNetworkApi`), models
`models/local_network.py`.

These endpoints configure a mower to accept a local WebSocket connection from
a named OAuth client and mint the short-lived ticket that connection
presents. The WebSocket protocol itself is undocumented (Q7); phase 4.

## `POST /v1/ha/local-network/save` → `LocalNetworkApi.save(client_id, devices, *, redirect_uri=None) -> list[LocalNetworkConfig]`

Request `DeviceHaLocalConfigSaveReq`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `clientId` | `client_id` | `str` | required; the OAuth client id |
| `redirectUri` | `redirect_uri` | `str | None` | "HA OAuth redirect URI" (Q8) |
| `devices[].deviceName` | `LocalNetworkDevice.device_name` | `str` | required; **device name**, not id |
| `devices[].enabled` | `LocalNetworkDevice.enabled` | `bool` | wire `1`/`0`; required, so a caller states it |

The cloud dispatches the configuration to each mower; the response reports
per-device dispatch state.

## `POST /v1/ha/local-network/query` → `LocalNetworkApi.query(client_id, *, device_name=None) -> list[LocalNetworkConfig]`

Omit `device_name` to list every configured device.

`LocalNetworkConfig` (`DeviceHaLocalConfigVo`):

| Wire | Python | Type | Notes |
|---|---|---|---|
| `deviceName` | `device_name` | `str` | |
| `clientId` | `client_id` | `str` | |
| `redirectUri` | `redirect_uri` | `str | None` | |
| `enabled` | `enabled` | `bool` | |
| `dispatchStatus` | `dispatch_status` | `DispatchStatus` | 0 pending, 1 success, 2 failed |
| `failReason` | `fail_reason` | `str | None` | |

## `POST /v1/mower/ws/ticket` → `LocalNetworkApi.ws_ticket(device_name, *, timestamp_s=None, ip=None) -> WsTicket`

Request `WsTicketReq`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `deviceName` | `device_name` | `str` | required |
| `timestamp` | `timestamp_s` | `int` | required; client Unix seconds, for skew checking; defaults to the injected clock |
| `ip` | `ip` | `str | None` | bind the ticket to a source IP; omit to skip |

`WsTicket`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `ticketId` | `ticket_id` | `str` | |
| `productKey` | `product_key` | `str` | |
| `deviceName` | `device_name` | `str` | |
| `userId` | `user_id` | `str` | |
| `clientId` | `client_id` | `str` | equals the JWT `aud` |
| `allowedIp` | `allowed_ip` | `str` | empty means unbound |
| `iat` | `issued_at_s` | `int` | |
| `exp` | `expires_at_s` | `int` | aligned with the access token |
| `sign` | `signature` | `str` | HMAC-SHA256, lowercase hex; opaque to the client |

`signature` is a credential for the mower and is redacted in `repr`.

Required vs default: `ticket_id`, `device_name`, `issued_at_s`, `expires_at_s`
and `signature` are required (the ticket cannot be presented without them);
`LocalNetworkConfig.device_name` and `client_id` are required (they identify
the row). Everything else defaults.

## Request models

The three request bodies are models too, so wire names stay inside
`models/`: `LocalNetworkSaveRequest(client_id, devices, redirect_uri=None)`,
`LocalNetworkQueryRequest(client_id, device_name=None)`,
`WsTicketRequest(device_name, timestamp_s, ip=None)`. The API methods build
them; callers normally never do.
