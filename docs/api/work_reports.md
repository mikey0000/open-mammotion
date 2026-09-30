# Work reports

Tag "Mower work report". Module `open_mammotion/api/work_reports.py`
(`WorkReportsApi`), models `models/work_report.py`.

## Shared query: `WorkReportQuery` (`WorkReportPageReq`)

| Wire | Python | Type | Notes |
|---|---|---|---|
| `deviceId` | `device_id` | `str` | required |
| `pageSize` | `page_size` | `int` | default 10 |
| `pageNumber` | `page_number` | `int` | 1-based, default 1 |
| `endWorkTimeStart` | `end_time_from_ms` | `int | None` | filter on end time |
| `endWorkTimeEnd` | `end_time_to_ms` | `int | None` | |
| `workType` | `work_type` | `WorkType | None` | |
| `workResult` | `work_result` | `WorkResult | None` | |

`None` fields are omitted from the body.

Enums (`TolerantIntEnum`):

- `WorkType`: 1 `SINGLE`, 2 `SCHEDULED`, 3 `DROP_MOW`, 4 `RESUME`
- `WorkResult`: 0 `UNKNOWN_RESULT`, 1 `WORKING`, 2 `PAUSED`, 3 `USER_STOPPED`,
  4 `INTERRUPTED`, 5 `COMPLETED` (the tolerant `UNKNOWN` sentinel is separate
  from the spec's own 0 value)
- `ReportJobContent` (detail only): 0 `MOW`, 1 `COLLECT`, 2 `MOW_AND_COLLECT` —
  a **different** numbering from `work_params.JobContent` (8/10/12), hence
  the separate enum
- `WorkEvent` (process timeline): 0 `NONE`, 1 `AUTO_START`, 2 `MANUAL_START`,
  3 `AUTO_RESUME`, 4 `MANUAL_RESUME`, 5 `AUTO_PAUSE`, 6 `MANUAL_PAUSE`,
  7 `NIGHT_ANIMAL_PROTECTION`, 8 `BAD_WEATHER_PROTECTION`, 9 `DO_NOT_DISTURB`,
  10 `LOW_BATTERY_RECHARGE`, 11 `NO_NIGHT_WORK`, 12 `COMPLETED`,
  13 `INTERRUPTED`, 14 `USER_STOPPED`

## `POST /v1/mower/work-reports/summary` → `WorkReportsApi.summary(query) -> WorkReportSummary`

| Wire | Python | Type | Notes |
|---|---|---|---|
| `saveTime` | `time_saved_min` | `float` | minutes |
| `carbonReduction` | `carbon_reduction_g` | `float` | grams |
| `workCount` | `work_count` | `int` | |
| `totalWorkArea` | `total_work_area_m2` | `float` | |

## `POST /v1/mower/work-reports/search` → `WorkReportsApi.search(query) -> WorkReportPage`

`WorkReportPage`: `records: list[WorkReport]`, `total: int`,
`page_number: int`, `page_size: int`, `pages: int`.

`WorkReport`:

| Wire | Python | Type |
|---|---|---|
| `workId` | `work_id` | `str` |
| `endWorkTime` | `end_time_ms` | `int` |
| `workType` | `work_type` | `WorkType` |
| `workResult` | `work_result` | `WorkResult` |
| `workProgress` | `progress_pct` | `float` |
| `workArea` | `work_area_m2` | `float` |
| `workTimeUsed` | `duration_s` | `int` |

## `GET /v1/mower/{deviceId}/work-reports/{workId}` → `WorkReportsApi.get(device_id, work_id) -> WorkReportDetail`

| Wire | Python | Type | Notes |
|---|---|---|---|
| `workArea` | `work_area_m2` | `float` | |
| `workTimeUsed` | `duration_s` | `int` | |
| `saveTime` | `time_saved_min` | `float` | |
| `carbonReduction` | `carbon_reduction_g` | `float` | |
| `energyConsume` | `energy_wh` | `float` | |
| `startWorkTime` | `start_time_ms` | `int` | |
| `endWorkTime` | `end_time_ms` | `int` | |
| `workType` | `work_type` | `WorkType` | |
| `jobContent` | `job_content` | `ReportJobContent` | 0/1/2 numbering |
| `workProcess` | `events` | `list[WorkProcessEvent]` | |
| `workParam` | `work_params` | `WorkParams | None` | same model as actions |
| `mapFilePath` | `map_file_url` | `str | None` | signed CDN URL, short-lived |

`WorkProcessEvent`: `timestamp_ms: int` (wire `timeStamp`), `event: WorkEvent`
(wire `eventCode`).

Every model with a `*_ms` field exposes a matching `datetime` property
(`end_time`, `start_time`, `timestamp`) in UTC.

Required vs default: the spec marks no response field required. Ids and
timestamps have no default (a record without them cannot be identified or
placed in time, so a missing one is a `ContractError`); measurements default
to 0, strings to `""`, enums to `UNKNOWN`, lists to empty.
