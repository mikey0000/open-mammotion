from __future__ import annotations

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.task import WorkTask
from tests.unit.models._helpers import work_task_json


class TestWorkTaskDecode:
    def test_decodes_task_id_and_name(self) -> None:
        assert WorkTask.from_dict(work_task_json()) == WorkTask(task_id="task-1", task_name="Front lawn")

    def test_ignores_unknown_keys(self) -> None:
        assert WorkTask.from_dict(work_task_json(color="green")) == WorkTask(task_id="task-1", task_name="Front lawn")

    @pytest.mark.parametrize(("wire", "field"), [("taskId", "task_id"), ("taskName", "task_name")])
    def test_raises_missing_field_without_a_required_key(self, wire: str, field: str) -> None:
        body = work_task_json()
        del body[wire]

        with pytest.raises(MissingField, match=field):
            WorkTask.from_dict(body)

    def test_to_dict_round_trips_by_alias(self) -> None:
        assert WorkTask.from_dict(work_task_json()).to_dict() == work_task_json()
