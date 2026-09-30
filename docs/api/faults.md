# Faults (device error-code history)

Tag "Mower information", endpoint `POST /v1/mower/error-codes/search`.
Module `open_mammotion/api/faults.py` (`FaultsApi`), models
`models/fault.py`. This is the per-device history of raised faults, not a
dictionary of error codes.

## `FaultsApi.search(query) -> FaultPage`

Query `FaultQuery` (`DeviceErrorCodePageReq`):

| Wire | Python | Type | Notes |
|---|---|---|---|
| `deviceId` | `device_id` | `str` | required |
| `pageSize` | `page_size` | `int` | default 10 |
| `pageNumber` | `page_number` | `int` | 1-based |
| `startDate` | `start_date` | `date | None` | inclusive, ISO `YYYY-MM-DD` |
| `endDate` | `end_date` | `date | None` | inclusive |
| `errorCode` | `error_code` | `str | None` | keyword filter |

`FaultPage`: `records: list[Fault]`, `total: int`, `page_number: int`,
`page_size: int`, `has_more: bool`.

`Fault` (`DeviceErrorCode`):

| Wire | Python | Type | Notes |
|---|---|---|---|
| `code` | `code` | `int` | |
| `implication` | `implication` | `str` | localised by `Accept-Language` (Q11) |
| `solution` | `solution` | `str` | |
| `gmtCreate` | `raised_at_ms` | `int` | when the alert fired |
| `createTime` | `recorded_at_ms` | `int` | when the record was written |
| `faultLevel` | `level` | `FaultLevel` | 1 info, 2 warning, 3 critical |
| `priority` | `priority` | `NotificationPriority` | 0 none, 1 info, 2 warning, 3 critical |
| `imageList` | `images` | `list[Attachment]` | |
| `videoList` | `videos` | `list[Attachment]` | |
| `buttonList` | `buttons` | `list[Attachment]` | |

`Attachment` (`WorkflowCodeFileInfo`): `url: str` (required), `button_name: str`,
`button_type: str`, `sort: int`.
