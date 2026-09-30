"""``ActionsApi``: the "Mower action command" tag — actions, work parameters, tasks (``docs/api/actions.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_mammotion.api._base import ApiGroup
from open_mammotion.exceptions import CommandRejectedError
from open_mammotion.models.action import ActionResult, WorkAction
from open_mammotion.models.task import WorkTask
from open_mammotion.models.work_params import WorkParams

if TYPE_CHECKING:
    from open_mammotion.models.common import Envelope, JsonObject

_ACTION_PATH = "/v1/mower/action"


def _raise_if_rejected(result: ActionResult | WorkParams, envelope: Envelope, path: str) -> None:
    if not result.accepted:
        raise CommandRejectedError(result.message, code=envelope.code, request_id=envelope.request_id, path=path)


class ActionsApi(ApiGroup):
    """Commands to a mower, its current work parameters and its task list."""

    async def perform(self, device_id: str, action: WorkAction, *, task_name: str | None = None) -> ActionResult:
        """``POST /v1/mower/action``: send one work action.

        Raises:
            ValueError: ``device_id`` is empty, or ``action`` is ``START`` without a
                ``task_name``; nothing is sent.
            CommandRejectedError: The mower refused the command (``commandResult: false``).

        """
        self._require(device_id, "device_id")
        action = WorkAction(action)
        if action is WorkAction.START and not task_name:
            raise ValueError("task_name is required for WorkAction.START")
        payload: JsonObject = {"deviceId": device_id, "action": action.value}
        if task_name:
            payload["params"] = {"taskName": task_name}
        envelope = await self._request("POST", _ACTION_PATH, json=payload)
        result = self._decode(ActionResult, envelope.data, path=_ACTION_PATH)
        _raise_if_rejected(result, envelope, _ACTION_PATH)
        return result

    async def start(self, device_id: str, task_name: str) -> ActionResult:
        """Start the named task (``START``); tasks are created in the Mammotion app."""
        return await self.perform(device_id, WorkAction.START, task_name=task_name)

    async def start_unplanned(self, device_id: str) -> ActionResult:
        """Start mowing immediately with no plan (``CMD_START``)."""
        return await self.perform(device_id, WorkAction.CMD_START)

    async def pause(self, device_id: str) -> ActionResult:
        """Pause the current operation (``PAUSE``)."""
        return await self.perform(device_id, WorkAction.PAUSE)

    async def resume(self, device_id: str) -> ActionResult:
        """Resume from paused (``RESUME``)."""
        return await self.perform(device_id, WorkAction.RESUME)

    async def stop(self, device_id: str) -> ActionResult:
        """Stop and terminate the current task (``STOP``)."""
        return await self.perform(device_id, WorkAction.STOP)

    async def return_to_dock(self, device_id: str) -> ActionResult:
        """Return to the charging dock (``RETURN``)."""
        return await self.perform(device_id, WorkAction.RETURN)

    async def cancel_return(self, device_id: str) -> ActionResult:
        """Cancel an in-progress return to the dock (``CANCEL_RETURN``)."""
        return await self.perform(device_id, WorkAction.CANCEL_RETURN)

    async def work_params(self, device_id: str) -> WorkParams:
        """``GET /v1/mower/{deviceId}/work-params``: the mower's current working parameters.

        Raises:
            ValueError: ``device_id`` is empty; nothing is sent.
            CommandRejectedError: The query was refused (``commandResult: false``).

        """
        path = self._mower_path(device_id, "work-params")
        envelope = await self._request("GET", path)
        params = self._decode(WorkParams, envelope.data, path=path)
        _raise_if_rejected(params, envelope, path)
        return params

    async def tasks(self, device_id: str) -> list[WorkTask]:
        """``GET /v1/mower/{deviceId}/plan``: the tasks ``start`` can run.

        Raises:
            ValueError: ``device_id`` is empty; nothing is sent.

        """
        return await self._get_list(self._mower_path(device_id, "plan"), WorkTask)
