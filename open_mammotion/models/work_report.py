"""Work-report query, summary, page and detail models (``docs/api/work_reports.md``).

The spec marks no response field required. Ids and timestamps have no default, because a
record without them cannot be identified or placed in time; measurements default to zero,
enums to ``UNKNOWN`` and lists to empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import TolerantIntEnum, WireModel, utc_from_ms
from open_mammotion.models.work_params import WorkParams

if TYPE_CHECKING:
    from datetime import datetime


class WorkType(TolerantIntEnum):
    """``workType``: how the job was started."""

    UNKNOWN = -1
    SINGLE = 1
    SCHEDULED = 2
    DROP_MOW = 3
    RESUME = 4


class WorkResult(TolerantIntEnum):
    """``workResult``. ``UNKNOWN_RESULT`` is the spec's own 0; ``UNKNOWN`` is an unlisted value."""

    UNKNOWN = -1
    UNKNOWN_RESULT = 0
    WORKING = 1
    PAUSED = 2
    USER_STOPPED = 3
    INTERRUPTED = 4
    COMPLETED = 5


class ReportJobContent(TolerantIntEnum):
    """``jobContent`` of a report detail; numbered 0/1/2, unlike ``work_params.JobContent`` (8/10/12)."""

    UNKNOWN = -1
    MOW = 0
    COLLECT = 1
    MOW_AND_COLLECT = 2


class WorkEvent(TolerantIntEnum):
    """``eventCode`` of one node on a report's process timeline."""

    UNKNOWN = -1
    NONE = 0
    AUTO_START = 1
    MANUAL_START = 2
    AUTO_RESUME = 3
    MANUAL_RESUME = 4
    AUTO_PAUSE = 5
    MANUAL_PAUSE = 6
    NIGHT_ANIMAL_PROTECTION = 7
    BAD_WEATHER_PROTECTION = 8
    DO_NOT_DISTURB = 9
    LOW_BATTERY_RECHARGE = 10
    NO_NIGHT_WORK = 11
    COMPLETED = 12
    INTERRUPTED = 13
    USER_STOPPED = 14


@dataclass(frozen=True)
class WorkReportQuery(WireModel):
    """``WorkReportPageReq``: the body of both summary and search. ``None`` filters are omitted."""

    device_id: Annotated[str, Alias("deviceId")]
    page_size: Annotated[int, Alias("pageSize")] = 10
    page_number: Annotated[int, Alias("pageNumber")] = 1
    end_time_from_ms: Annotated[int | None, Alias("endWorkTimeStart")] = None
    end_time_to_ms: Annotated[int | None, Alias("endWorkTimeEnd")] = None
    work_type: Annotated[WorkType | None, Alias("workType")] = None
    work_result: Annotated[WorkResult | None, Alias("workResult")] = None

    @property
    def end_time_from(self) -> datetime | None:
        """Lower bound on a report's end time, in UTC."""
        return None if self.end_time_from_ms is None else utc_from_ms(self.end_time_from_ms)

    @property
    def end_time_to(self) -> datetime | None:
        """Upper bound on a report's end time, in UTC."""
        return None if self.end_time_to_ms is None else utc_from_ms(self.end_time_to_ms)


@dataclass(frozen=True)
class WorkReportSummary(WireModel):
    """Aggregate statistics over the reports a query matches."""

    time_saved_min: Annotated[float, Alias("saveTime")] = 0.0
    carbon_reduction_g: Annotated[float, Alias("carbonReduction")] = 0.0
    work_count: Annotated[int, Alias("workCount")] = 0
    total_work_area_m2: Annotated[float, Alias("totalWorkArea")] = 0.0


@dataclass(frozen=True)
class WorkReport(WireModel):
    """One row of a work-report search."""

    work_id: Annotated[str, Alias("workId")]
    end_time_ms: Annotated[int, Alias("endWorkTime")]
    work_type: Annotated[WorkType, Alias("workType")] = WorkType.UNKNOWN
    work_result: Annotated[WorkResult, Alias("workResult")] = WorkResult.UNKNOWN
    progress_pct: Annotated[float, Alias("workProgress")] = 0.0
    work_area_m2: Annotated[float, Alias("workArea")] = 0.0
    duration_s: Annotated[int, Alias("workTimeUsed")] = 0

    @property
    def end_time(self) -> datetime:
        """When the job ended, in UTC."""
        return utc_from_ms(self.end_time_ms)


@dataclass(frozen=True)
class WorkReportPage(WireModel):
    """One page of work reports; ``page_number`` is 1-based."""

    records: list[WorkReport] = field(default_factory=list)
    total: int = 0
    page_number: Annotated[int, Alias("pageNumber")] = 0
    page_size: Annotated[int, Alias("pageSize")] = 0
    pages: int = 0


@dataclass(frozen=True)
class WorkProcessEvent(WireModel):
    """``WorkReportDetail.WorkProcess``: one event on a job's timeline."""

    timestamp_ms: Annotated[int, Alias("timeStamp")]
    event: Annotated[WorkEvent, Alias("eventCode")]

    @property
    def timestamp(self) -> datetime:
        """When the event happened, in UTC."""
        return utc_from_ms(self.timestamp_ms)


@dataclass(frozen=True)
class WorkReportDetail(WireModel):
    """One job in full. ``map_file_url`` is a short-lived signed URL; fetch it promptly."""

    start_time_ms: Annotated[int, Alias("startWorkTime")]
    end_time_ms: Annotated[int, Alias("endWorkTime")]
    work_area_m2: Annotated[float, Alias("workArea")] = 0.0
    duration_s: Annotated[int, Alias("workTimeUsed")] = 0
    time_saved_min: Annotated[float, Alias("saveTime")] = 0.0
    carbon_reduction_g: Annotated[float, Alias("carbonReduction")] = 0.0
    energy_wh: Annotated[float, Alias("energyConsume")] = 0.0
    work_type: Annotated[WorkType, Alias("workType")] = WorkType.UNKNOWN
    job_content: Annotated[ReportJobContent, Alias("jobContent")] = ReportJobContent.UNKNOWN
    events: Annotated[list[WorkProcessEvent], Alias("workProcess")] = field(default_factory=list)
    work_params: Annotated[WorkParams | None, Alias("workParam")] = None
    map_file_url: Annotated[str | None, Alias("mapFilePath")] = None

    @property
    def start_time(self) -> datetime:
        """When the job started, in UTC."""
        return utc_from_ms(self.start_time_ms)

    @property
    def end_time(self) -> datetime:
        """When the job ended, in UTC."""
        return utc_from_ms(self.end_time_ms)
