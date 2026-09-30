# Actions, work parameters and tasks

Tag "Mower action command". Module `open_mammotion/api/actions.py`
(`ActionsApi`), models `models/action.py`, `models/work_params.py`,
`models/task.py`.

## `POST /v1/mower/action` → `ActionsApi.perform(device_id, action, *, task_name=None) -> ActionResult`

Request `WorkActionRequest`:

| Wire | Python | Type | Notes |
|---|---|---|---|
| `deviceId` | `device_id` | `str` | required |
| `action` | `action` | `WorkAction` | required |
| `params.taskName` | `task_name` | `str | None` | required when `action == START` |

`WorkAction` (`StrEnum`, spec values verbatim):

| Value | Meaning |
|---|---|
| `CMD_START` | start mowing immediately with no plan |
| `START` | start the named task (`task_name` required) |
| `PAUSE` | pause the current operation |
| `RESUME` | resume from paused |
| `STOP` | stop and terminate the current task |
| `RETURN` | return to the charging dock |
| `CANCEL_RETURN` | cancel an in-progress return |

`perform` sends `params` whenever `task_name` is given, whatever the action.
Every method raises `ValueError` before any I/O for an empty `device_id`.

Convenience methods on `ActionsApi`, one per value: `start(device_id,
task_name)`, `start_unplanned(device_id)`, `pause`, `resume`, `stop`,
`return_to_dock`, `cancel_return`. Each calls `perform`. `start` without a
task name raises `ValueError` before any I/O.

Response `data` (`WorkAction` schema → `ActionResult`):

| Wire | Python | Type |
|---|---|---|
| `commandResult` | `accepted` | `bool` (required) |
| `resultMessage` | `message` | `str` |

`accepted == False` raises `CommandRejectedError(message)`; the method never
returns a rejected result.

## `GET /v1/mower/{deviceId}/work-params` → `ActionsApi.work_params(device_id) -> WorkParams`

Schema `workParam`. The two `commandResult`/`resultMessage` fields are treated
exactly as for actions (rejected → `CommandRejectedError`).

| Wire | Python | Type | Notes |
|---|---|---|---|
| `edgeMode` | `edge_laps` | `int` | edge-tracing rounds |
| `rideBoundaryDistance` | `ride_boundary_distance` | `float` | edge overlap |
| `channelMode` | `channel_mode` | `ChannelMode` | 0 single bow, 1 cross, 2 zoned, 3 none |
| `jobContent` | `job_content` | `JobContent` | 8 mow, 10 collect, 12 mow and collect |
| `dumpPeriodSqm` | `dump_period_sqm` | `int` | grass-collection frequency |
| `knifeHeight` | `blade_height` | `int` | |
| `speed` | `speed` | `int` | |
| `channelWidth` | `channel_width` | `int` | bow spacing |
| `toward` | `toward` | `int` | working direction |
| `towardMode` | `toward_mode` | `TowardMode` | 0 relative, 1 absolute, 2 random |
| `towardIncludedAngle` | `toward_included_angle` | `int` | double-bow angle |
| `ultraWave` | `obstacle_mode` | `ObstacleMode` | 0/1 slow-touch, 10 no-touch, 11 no-out-lawn |
| `boundaryZigzagOrder` | `path_order` | `PathOrder` | 0 border first, 1 bow first |
| `forbiddenAreaCircleTimes` | `obstacle_laps` | `int` | |
| `visualHashs` | `visual_hashes` | `list[str]` | map file hashes |

All enums are `TolerantIntEnum`. `ObstacleMode` has `SLOW_TOUCH = 0` and
`SLOW_TOUCH_ALT = 1` (the spec says "0/1" mean the same thing); test with
`ObstacleMode.is_slow_touch`. Every field except `accepted`/`message` is
optional (`None` when absent); `accepted` defaults to `True` when
`commandResult` is absent.

## `GET /v1/mower/{deviceId}/plan` → `ActionsApi.tasks(device_id) -> list[WorkTask]`

| Wire | Python | Type |
|---|---|---|
| `taskId` | `task_id` | `str` |
| `taskName` | `task_name` | `str` |

`task_name` is what `START` takes; tasks are created in the app.
