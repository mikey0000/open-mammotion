from __future__ import annotations

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.action import ActionResult, WorkAction
from tests.unit.models._helpers import action_result_json


class TestWorkAction:
    def test_values_are_the_spec_names_verbatim(self) -> None:
        assert [a.value for a in WorkAction] == [
            "CMD_START",
            "START",
            "PAUSE",
            "RESUME",
            "STOP",
            "RETURN",
            "CANCEL_RETURN",
        ]

    def test_formats_as_its_wire_value(self) -> None:
        assert f"{WorkAction.CANCEL_RETURN}" == "CANCEL_RETURN"

    def test_has_no_unknown_member(self) -> None:
        with pytest.raises(ValueError, match="MOONWALK"):
            WorkAction("MOONWALK")


class TestActionResultDecode:
    def test_decodes_the_spec_example(self) -> None:
        assert ActionResult.from_dict(action_result_json()) == ActionResult(accepted=True, message="Command issued")

    def test_decodes_a_rejection(self) -> None:
        result = ActionResult.from_dict(action_result_json(commandResult=False, resultMessage="Mower is offline"))

        assert result == ActionResult(accepted=False, message="Mower is offline")

    def test_defaults_message_to_empty(self) -> None:
        assert ActionResult.from_dict({"commandResult": True}).message == ""

    def test_ignores_unknown_keys(self) -> None:
        assert ActionResult.from_dict(action_result_json(traceId="t-1")) == ActionResult.from_dict(action_result_json())

    def test_raises_missing_field_without_command_result(self) -> None:
        with pytest.raises(MissingField, match="accepted"):
            ActionResult.from_dict({"resultMessage": "?"})

    def test_to_dict_round_trips_by_alias(self) -> None:
        assert ActionResult.from_dict(action_result_json()).to_dict() == action_result_json()
