"""``OpenMammotion.actions``: commands move the fake mower's state; refusals become ``CommandRejectedError``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from open_mammotion import CommandRejectedError, DeviceStatus
from open_mammotion.models.work_params import ChannelMode, JobContent, ObstacleMode, PathOrder, TowardMode
from tests.fakeserver.state import LUBA_ID, LUBA_TASKS, YUKA_ID, YUKA_TASKS
from tests.integration._fakeserver_client import bounded
from tests.integration._helpers import secrets_in_text

if TYPE_CHECKING:
    from open_mammotion import OpenMammotion
    from tests.fakeserver.server import FakeCloud


async def _status(api: OpenMammotion, device_id: str) -> DeviceStatus | None:
    return (await bounded(api.devices.get(device_id))).status


class TestTasks:
    async def test_lists_the_tasks_start_can_run(self, api: OpenMammotion) -> None:
        tasks = await bounded(api.actions.tasks(YUKA_ID))

        assert [t.task_name for t in tasks] == list(YUKA_TASKS)
        assert all(t.task_id for t in tasks)


class TestStart:
    async def test_an_accepted_start_sets_the_mower_working(self, api: OpenMammotion) -> None:
        result = await bounded(api.actions.start(YUKA_ID, YUKA_TASKS[0]))

        assert result.accepted is True
        assert await _status(api, YUKA_ID) is DeviceStatus.WORKING

    async def test_starting_the_offline_luba_is_rejected_as_device_offline(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        with pytest.raises(CommandRejectedError) as caught:
            await bounded(api.actions.start(LUBA_ID, LUBA_TASKS[0]))

        assert caught.value.message == "device offline"
        assert not secrets_in_text(str(caught.value), fake_cloud)

    async def test_an_unknown_task_name_is_rejected(self, api: OpenMammotion) -> None:
        with pytest.raises(CommandRejectedError) as caught:
            await bounded(api.actions.start(YUKA_ID, "No such task"))

        assert caught.value.message == "task not found"
        assert await _status(api, YUKA_ID) is DeviceStatus.STANDBY

    async def test_an_empty_task_name_raises_value_error_without_a_request(
        self, api: OpenMammotion, fake_cloud: FakeCloud
    ) -> None:
        with pytest.raises(ValueError, match="task_name"):
            await bounded(api.actions.start(YUKA_ID, ""))

        assert fake_cloud.state.requests_total == 0


class TestStatusTransitions:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("pause", DeviceStatus.PAUSED),
            ("resume", DeviceStatus.WORKING),
            ("stop", DeviceStatus.STANDBY),
            ("return_to_dock", DeviceStatus.RETURNING),
            ("cancel_return", DeviceStatus.PAUSED),
            ("start_unplanned", DeviceStatus.WORKING),
        ],
    )
    async def test_an_accepted_command_moves_the_working_mower_to_its_status(
        self, api: OpenMammotion, command: str, expected: DeviceStatus
    ) -> None:
        await bounded(api.actions.start(YUKA_ID, YUKA_TASKS[0]))

        result = await bounded(getattr(api.actions, command)(YUKA_ID))

        assert result.accepted is True
        assert await _status(api, YUKA_ID) is expected


class TestWorkParams:
    async def test_returns_the_online_mowers_parameters(self, api: OpenMammotion) -> None:
        params = await bounded(api.actions.work_params(YUKA_ID))

        assert params.accepted is True
        assert params.blade_height == 50
        assert params.job_content is JobContent.MOW
        assert params.edge_laps == 1
        assert params.ride_boundary_distance == 0.25
        assert params.channel_mode is ChannelMode.SINGLE_BOW
        assert params.toward_mode is TowardMode.RELATIVE
        assert params.obstacle_mode is ObstacleMode.NO_TOUCH
        assert params.path_order is PathOrder.BORDER_FIRST
        assert (params.speed, params.channel_width, params.toward) == (3, 25, 90)
        assert params.visual_hashes == ["3f2a9c01", "7b1e44d2"]

    async def test_the_offline_luba_is_rejected(self, api: OpenMammotion) -> None:
        with pytest.raises(CommandRejectedError) as caught:
            await bounded(api.actions.work_params(LUBA_ID))

        assert caught.value.message == "device offline"
