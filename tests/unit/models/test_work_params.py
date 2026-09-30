from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from open_mammotion.models.work_params import (
    ChannelMode,
    JobContent,
    ObstacleMode,
    PathOrder,
    TowardMode,
    WorkParams,
)
from tests.unit.models._helpers import work_params_json

if TYPE_CHECKING:
    from open_mammotion.models.common import TolerantIntEnum


class TestWorkParamsDecode:
    def test_decodes_every_field_by_alias(self) -> None:
        params = WorkParams.from_dict(work_params_json())

        assert params == WorkParams(
            accepted=True,
            message="Command issued",
            edge_laps=1,
            ride_boundary_distance=0.5,
            channel_mode=ChannelMode.SINGLE_BOW,
            job_content=JobContent.MOW,
            dump_period_sqm=100,
            blade_height=60,
            speed=1,
            channel_width=25,
            toward=90,
            toward_mode=TowardMode.ABSOLUTE,
            toward_included_angle=45,
            obstacle_mode=ObstacleMode.NO_TOUCH,
            path_order=PathOrder.BORDER_FIRST,
            obstacle_laps=1,
            visual_hashes=["hash-a", "hash-b"],
        )

    def test_defaults_every_field_when_absent(self) -> None:
        params = WorkParams.from_dict({})

        assert params.accepted is True
        assert params.message == ""
        assert params.visual_hashes == []
        assert params.channel_mode is None
        assert params.blade_height is None

    def test_decodes_a_rejection(self) -> None:
        params = WorkParams.from_dict(work_params_json(commandResult=False, resultMessage="Mower is offline"))

        assert params.accepted is False
        assert params.message == "Mower is offline"

    def test_ignores_unknown_keys(self) -> None:
        assert WorkParams.from_dict(work_params_json(mowingPattern="spiral")) == WorkParams.from_dict(
            work_params_json()
        )

    def test_to_dict_round_trips_by_alias(self) -> None:
        assert WorkParams.from_dict(work_params_json()).to_dict() == work_params_json()

    def test_to_dict_omits_absent_parameters(self) -> None:
        assert WorkParams().to_dict() == {"commandResult": True, "resultMessage": "", "visualHashs": []}


class TestWorkParamEnums:
    @pytest.mark.parametrize(
        ("alias", "wire", "attr", "expected"),
        [
            ("channelMode", 0, "channel_mode", ChannelMode.SINGLE_BOW),
            ("channelMode", 1, "channel_mode", ChannelMode.CROSS),
            ("channelMode", 2, "channel_mode", ChannelMode.ZONED_BOW),
            ("channelMode", 3, "channel_mode", ChannelMode.NO_BOW),
            ("jobContent", 8, "job_content", JobContent.MOW),
            ("jobContent", 10, "job_content", JobContent.COLLECT),
            ("jobContent", 12, "job_content", JobContent.MOW_AND_COLLECT),
            ("towardMode", 0, "toward_mode", TowardMode.RELATIVE),
            ("towardMode", 1, "toward_mode", TowardMode.ABSOLUTE),
            ("towardMode", 2, "toward_mode", TowardMode.RANDOM),
            ("ultraWave", 0, "obstacle_mode", ObstacleMode.SLOW_TOUCH),
            ("ultraWave", 1, "obstacle_mode", ObstacleMode.SLOW_TOUCH_ALT),
            ("ultraWave", 10, "obstacle_mode", ObstacleMode.NO_TOUCH),
            ("ultraWave", 11, "obstacle_mode", ObstacleMode.NO_OUT_LAWN),
            ("boundaryZigzagOrder", 0, "path_order", PathOrder.BORDER_FIRST),
            ("boundaryZigzagOrder", 1, "path_order", PathOrder.BOW_FIRST),
        ],
    )
    def test_decodes_every_spec_value(self, alias: str, wire: int, attr: str, expected: TolerantIntEnum) -> None:
        assert getattr(WorkParams.from_dict(work_params_json(**{alias: wire})), attr) is expected

    @pytest.mark.parametrize(
        ("alias", "attr", "enum"),
        [
            ("channelMode", "channel_mode", ChannelMode),
            ("jobContent", "job_content", JobContent),
            ("towardMode", "toward_mode", TowardMode),
            ("ultraWave", "obstacle_mode", ObstacleMode),
            ("boundaryZigzagOrder", "path_order", PathOrder),
        ],
    )
    def test_decodes_an_unknown_value_as_unknown(self, alias: str, attr: str, enum: type[TolerantIntEnum]) -> None:
        assert getattr(WorkParams.from_dict(work_params_json(**{alias: 97})), attr) is enum["UNKNOWN"]

    def test_logs_an_unknown_value_once_for_repeated_values(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())
        WorkParams.from_dict(work_params_json(jobContent=98))
        WorkParams.from_dict(work_params_json(jobContent=98))

        warnings = [
            r for r in caplog.records if r.levelno == logging.WARNING and "Unknown JobContent" in r.getMessage()
        ]
        assert len(warnings) == 1

    @pytest.mark.parametrize("mode", [ObstacleMode.SLOW_TOUCH, ObstacleMode.SLOW_TOUCH_ALT])
    def test_both_spec_slow_touch_values_read_as_slow_touch(self, mode: ObstacleMode) -> None:
        assert mode.is_slow_touch

    @pytest.mark.parametrize("mode", [ObstacleMode.NO_TOUCH, ObstacleMode.NO_OUT_LAWN, ObstacleMode.UNKNOWN])
    def test_other_obstacle_modes_are_not_slow_touch(self, mode: ObstacleMode) -> None:
        assert not mode.is_slow_touch
