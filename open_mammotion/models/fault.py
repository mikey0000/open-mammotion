"""Device error-code history: query, record, attachment and page models (``docs/api/faults.md``).

The spec marks no response field required. ``code`` and both timestamps have no default,
because a record without them cannot be identified or placed in time; the rest default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import TolerantIntEnum, WireModel, utc_from_ms

if TYPE_CHECKING:
    from datetime import datetime


class FaultLevel(TolerantIntEnum):
    """``faultLevel``: how serious the fault is."""

    UNKNOWN = -1
    INFO = 1
    WARNING = 2
    CRITICAL = 3


class NotificationPriority(TolerantIntEnum):
    """``priority``: how prominently the fault is notified."""

    UNKNOWN = -1
    NONE = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3


@dataclass(frozen=True)
class FaultQuery(WireModel):
    """``DeviceErrorCodePageReq``. Dates are inclusive and sent as ``YYYY-MM-DD``; ``None`` is omitted."""

    device_id: Annotated[str, Alias("deviceId")]
    page_size: Annotated[int, Alias("pageSize")] = 10
    page_number: Annotated[int, Alias("pageNumber")] = 1
    start_date: Annotated[date | None, Alias("startDate")] = None
    end_date: Annotated[date | None, Alias("endDate")] = None
    error_code: Annotated[str | None, Alias("errorCode")] = None


@dataclass(frozen=True)
class Attachment(WireModel):
    """``WorkflowCodeFileInfo``: an image, video or action button attached to a fault."""

    url: str
    button_name: Annotated[str, Alias("buttonName")] = ""
    button_type: Annotated[str, Alias("buttonType")] = ""
    sort: int = 0


@dataclass(frozen=True)
class Fault(WireModel):
    """``DeviceErrorCode``: one raised fault. ``implication``/``solution`` follow ``Accept-Language`` (Q11)."""

    code: int
    raised_at_ms: Annotated[int, Alias("gmtCreate")]
    recorded_at_ms: Annotated[int, Alias("createTime")]
    implication: str = ""
    solution: str = ""
    level: Annotated[FaultLevel, Alias("faultLevel")] = FaultLevel.UNKNOWN
    priority: NotificationPriority = NotificationPriority.UNKNOWN
    images: Annotated[list[Attachment], Alias("imageList")] = field(default_factory=list)
    videos: Annotated[list[Attachment], Alias("videoList")] = field(default_factory=list)
    buttons: Annotated[list[Attachment], Alias("buttonList")] = field(default_factory=list)

    @property
    def raised_at(self) -> datetime:
        """When the alert fired, in UTC."""
        return utc_from_ms(self.raised_at_ms)

    @property
    def recorded_at(self) -> datetime:
        """When the record was written, in UTC."""
        return utc_from_ms(self.recorded_at_ms)


@dataclass(frozen=True)
class FaultPage(WireModel):
    """One page of fault records; ``page_number`` is 1-based."""

    records: list[Fault] = field(default_factory=list)
    total: int = 0
    page_number: Annotated[int, Alias("pageNumber")] = 0
    page_size: Annotated[int, Alias("pageSize")] = 0
    has_more: Annotated[bool, Alias("hasMore")] = False
