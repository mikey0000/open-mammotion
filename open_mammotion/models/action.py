"""The work-action request enum and its response model (``docs/api/actions.md``)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import WireModel


class WorkAction(StrEnum):
    """``action`` of ``POST /v1/mower/action``; the spec's values verbatim."""

    CMD_START = "CMD_START"
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    RETURN = "RETURN"
    CANCEL_RETURN = "CANCEL_RETURN"


@dataclass(frozen=True)
class ActionResult(WireModel):
    """Whether the mower accepted a command (schema ``WorkAction``).

    ``accepted`` has no default: it is the whole answer, so an envelope without it is a
    contract violation. (``WorkParams.accepted`` defaults to ``True`` because there the
    parameters are the answer and the flag is auxiliary.)
    """

    accepted: Annotated[bool, Alias("commandResult")]
    message: Annotated[str, Alias("resultMessage")] = ""
