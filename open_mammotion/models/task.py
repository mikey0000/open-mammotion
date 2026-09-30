"""``WorkTask``: one task of a mower's plan list (``docs/api/actions.md``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import WireModel


@dataclass(frozen=True)
class WorkTask(WireModel):
    """A task created in the Mammotion app; ``task_name`` is what ``START`` takes.

    Both fields are required: a task without an id or a name cannot be started.
    """

    task_id: Annotated[str, Alias("taskId")]
    task_name: Annotated[str, Alias("taskName")]
