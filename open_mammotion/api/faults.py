"""``FaultsApi``: a mower's fault history from the "Mower information" tag (``docs/api/faults.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_mammotion.api._base import ApiGroup
from open_mammotion.models.fault import FaultPage

if TYPE_CHECKING:
    from open_mammotion.models.fault import FaultQuery


class FaultsApi(ApiGroup):
    """The faults a mower has raised; not a dictionary of error codes."""

    async def search(self, query: FaultQuery) -> FaultPage:
        """``POST /v1/mower/error-codes/search``: one page of the faults ``query`` matches.

        Raises:
            ValueError: ``query.device_id`` is empty; nothing is sent.

        """
        self._require(query.device_id, "device_id")
        return await self._post("/v1/mower/error-codes/search", query.to_dict(), FaultPage)
