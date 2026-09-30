from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from open_mammotion.api.actions import ActionsApi
from open_mammotion.exceptions import CommandRejectedError, ContractError
from open_mammotion.models.action import ActionResult, WorkAction
from open_mammotion.models.common import Envelope
from open_mammotion.models.task import WorkTask
from open_mammotion.models.work_params import JobContent, WorkParams
from tests.unit._fakes import FakeRequester, RecordedCall
from tests.unit.models._helpers import action_result_json, work_params_json, work_task_json

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

ACTION_PATH = "/v1/mower/action"


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def actions(requester: FakeRequester) -> ActionsApi:
    return ActionsApi(requester)


class TestPerform:
    async def test_posts_the_action_without_params(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.perform("123", WorkAction.PAUSE)

        assert requester.calls == [RecordedCall("POST", ACTION_PATH, {"deviceId": "123", "action": "PAUSE"})]

    async def test_posts_the_task_name_in_params(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.perform("123", WorkAction.START, task_name="Front lawn")

        assert requester.calls[0].json == {"deviceId": "123", "action": "START", "params": {"taskName": "Front lawn"}}

    async def test_sends_the_action_as_a_plain_string(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.perform("123", WorkAction.CANCEL_RETURN)

        assert requester.calls[0].json is not None
        sent = requester.calls[0].json["action"]
        assert type(sent) is str
        assert sent == "CANCEL_RETURN"

    async def test_sends_params_for_a_non_start_action_given_a_task_name(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.perform("123", WorkAction.PAUSE, task_name="Front lawn")

        assert requester.calls[0].json == {"deviceId": "123", "action": "PAUSE", "params": {"taskName": "Front lawn"}}

    async def test_accepts_the_action_as_its_string_value(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.perform("123", "PAUSE")  # type: ignore[arg-type]

        assert requester.calls[0].json == {"deviceId": "123", "action": "PAUSE"}

    async def test_rejects_an_unknown_action_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="MOONWALK"):
            await actions.perform("123", "MOONWALK")  # type: ignore[arg-type]

        assert requester.calls == []

    async def test_returns_the_accepted_result(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        assert await actions.perform("123", WorkAction.STOP) == ActionResult(accepted=True, message="Command issued")

    async def test_rejects_start_without_a_task_name_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="task_name"):
            await actions.perform("123", WorkAction.START)

        assert requester.calls == []

    async def test_rejects_an_empty_device_id_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await actions.perform("", WorkAction.PAUSE)

        assert requester.calls == []

    async def test_raises_command_rejected_with_the_envelope_details(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        rejection = action_result_json(commandResult=False, resultMessage="Mower is offline")
        requester.on("POST", ACTION_PATH, Envelope(code=200, msg="Success", data=rejection, request_id="req-42"))

        with pytest.raises(CommandRejectedError) as caught:
            await actions.perform("123", WorkAction.RESUME)

        assert caught.value.message == "Mower is offline"
        assert caught.value.code == 200
        assert caught.value.request_id == "req-42"
        assert caught.value.path == ACTION_PATH

    async def test_raises_contract_error_without_command_result(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        requester.on("POST", ACTION_PATH, {"resultMessage": "?"})

        with pytest.raises(ContractError, match="accepted"):
            await actions.perform("123", WorkAction.PAUSE)

    async def test_raises_contract_error_for_a_non_object(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, [action_result_json()])

        with pytest.raises(ContractError, match="expected an object"):
            await actions.perform("123", WorkAction.PAUSE)


class TestConvenienceMethods:
    @pytest.mark.parametrize(
        ("call", "action"),
        [
            (lambda api: api.start_unplanned("123"), "CMD_START"),
            (lambda api: api.pause("123"), "PAUSE"),
            (lambda api: api.resume("123"), "RESUME"),
            (lambda api: api.stop("123"), "STOP"),
            (lambda api: api.return_to_dock("123"), "RETURN"),
            (lambda api: api.cancel_return("123"), "CANCEL_RETURN"),
        ],
        ids=["start_unplanned", "pause", "resume", "stop", "return_to_dock", "cancel_return"],
    )
    async def test_sends_its_action_without_params(
        self,
        requester: FakeRequester,
        actions: ActionsApi,
        call: Callable[[ActionsApi], Awaitable[ActionResult]],
        action: str,
    ) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        result = await call(actions)

        assert requester.calls == [RecordedCall("POST", ACTION_PATH, {"deviceId": "123", "action": action})]
        assert result.accepted is True

    async def test_start_sends_start_with_the_task_name(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("POST", ACTION_PATH, action_result_json())

        await actions.start("123", "Front lawn")

        assert requester.calls[0].json == {"deviceId": "123", "action": "START", "params": {"taskName": "Front lawn"}}

    async def test_start_rejects_an_empty_task_name_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="task_name"):
            await actions.start("123", "")

        assert requester.calls == []


class TestWorkParams:
    async def test_gets_the_work_params_path(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/123/work-params", work_params_json())

        await actions.work_params("123")

        assert requester.calls == [RecordedCall("GET", "/v1/mower/123/work-params", None)]

    async def test_url_encodes_the_device_id(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/a%2Fb/work-params", work_params_json())

        await actions.work_params("a/b")

        assert requester.calls[0].path == "/v1/mower/a%2Fb/work-params"

    async def test_returns_the_decoded_params(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/123/work-params", work_params_json())

        params = await actions.work_params("123")

        assert params == WorkParams.from_dict(work_params_json())
        assert params.job_content is JobContent.MOW

    async def test_raises_command_rejected_with_the_envelope_details(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        rejection = work_params_json(commandResult=False, resultMessage="Mower is asleep")
        requester.on("GET", "/v1/mower/123/work-params", Envelope(code=0, data=rejection, request_id="req-7"))

        with pytest.raises(CommandRejectedError) as caught:
            await actions.work_params("123")

        assert caught.value.message == "Mower is asleep"
        assert caught.value.code == 0
        assert caught.value.request_id == "req-7"
        assert caught.value.path == "/v1/mower/123/work-params"

    async def test_raises_contract_error_for_a_wrongly_typed_field(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        requester.on("GET", "/v1/mower/123/work-params", work_params_json(visualHashs=5))

        with pytest.raises(ContractError, match="WorkParams"):
            await actions.work_params("123")

    async def test_rejects_an_empty_device_id_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await actions.work_params("")

        assert requester.calls == []


class TestTasks:
    async def test_gets_the_plan_path(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/123/plan", [work_task_json()])

        await actions.tasks("123")

        assert requester.calls == [RecordedCall("GET", "/v1/mower/123/plan", None)]

    async def test_returns_every_task(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/123/plan", [work_task_json(), work_task_json(taskId="task-2", taskName="Back")])

        assert await actions.tasks("123") == [
            WorkTask(task_id="task-1", task_name="Front lawn"),
            WorkTask(task_id="task-2", task_name="Back"),
        ]

    async def test_returns_empty_for_null_data(self, requester: FakeRequester, actions: ActionsApi) -> None:
        requester.on("GET", "/v1/mower/123/plan", None)

        assert await actions.tasks("123") == []

    async def test_raises_contract_error_naming_a_missing_field(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        requester.on("GET", "/v1/mower/123/plan", [{"taskId": "task-1"}])

        with pytest.raises(ContractError, match="task_name"):
            await actions.tasks("123")

    async def test_rejects_an_empty_device_id_before_any_request(
        self, requester: FakeRequester, actions: ActionsApi
    ) -> None:
        with pytest.raises(ValueError, match="device_id"):
            await actions.tasks("")

        assert requester.calls == []
