"""``WorkParams`` and its enums: a mower's current working parameters (``docs/api/actions.md``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import TolerantIntEnum, WireModel


class ChannelMode(TolerantIntEnum):
    """``channelMode``: the bow (stripe) pattern."""

    UNKNOWN = -1
    SINGLE_BOW = 0
    CROSS = 1
    ZONED_BOW = 2
    NO_BOW = 3


class JobContent(TolerantIntEnum):
    """``jobContent``: what the mower does while it drives."""

    UNKNOWN = -1
    MOW = 8
    COLLECT = 10
    MOW_AND_COLLECT = 12


class TowardMode(TolerantIntEnum):
    """``towardMode``: the reference system of ``toward``."""

    UNKNOWN = -1
    RELATIVE = 0
    ABSOLUTE = 1
    RANDOM = 2


class ObstacleMode(TolerantIntEnum):
    """``ultraWave``: obstacle avoidance.

    The spec gives slow-touch (ultrasonic deceleration) as "0/1", so both values are
    members; test with :attr:`is_slow_touch` rather than comparing to one of them.
    """

    UNKNOWN = -1
    SLOW_TOUCH = 0
    SLOW_TOUCH_ALT = 1
    NO_TOUCH = 10
    NO_OUT_LAWN = 11

    @property
    def is_slow_touch(self) -> bool:
        """Whether this is either of the spec's slow-touch values."""
        return self in {ObstacleMode.SLOW_TOUCH, ObstacleMode.SLOW_TOUCH_ALT}


class PathOrder(TolerantIntEnum):
    """``boundaryZigzagOrder``: whether the border or the bows are mown first."""

    UNKNOWN = -1
    BORDER_FIRST = 0
    BOW_FIRST = 1


@dataclass(frozen=True)
class WorkParams(WireModel):
    """``GET /v1/mower/{deviceId}/work-params`` (schema ``workParam``).

    The spec marks no field required, so every parameter is optional. ``accepted``
    defaults to ``True`` when ``commandResult`` is absent.
    """

    accepted: Annotated[bool, Alias("commandResult")] = True
    message: Annotated[str, Alias("resultMessage")] = ""
    edge_laps: Annotated[int | None, Alias("edgeMode")] = None
    ride_boundary_distance: Annotated[float | None, Alias("rideBoundaryDistance")] = None
    channel_mode: Annotated[ChannelMode | None, Alias("channelMode")] = None
    job_content: Annotated[JobContent | None, Alias("jobContent")] = None
    dump_period_sqm: Annotated[int | None, Alias("dumpPeriodSqm")] = None
    blade_height: Annotated[int | None, Alias("knifeHeight")] = None
    speed: int | None = None
    channel_width: Annotated[int | None, Alias("channelWidth")] = None
    toward: int | None = None
    toward_mode: Annotated[TowardMode | None, Alias("towardMode")] = None
    toward_included_angle: Annotated[int | None, Alias("towardIncludedAngle")] = None
    obstacle_mode: Annotated[ObstacleMode | None, Alias("ultraWave")] = None
    path_order: Annotated[PathOrder | None, Alias("boundaryZigzagOrder")] = None
    obstacle_laps: Annotated[int | None, Alias("forbiddenAreaCircleTimes")] = None
    visual_hashes: Annotated[list[str], Alias("visualHashs")] = field(default_factory=list)
