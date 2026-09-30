"""``WorkReportsApi``: the "Mower work report" tag (``docs/api/work_reports.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_mammotion.api._base import ApiGroup
from open_mammotion.models.work_report import WorkReportDetail, WorkReportPage, WorkReportSummary

if TYPE_CHECKING:
    from open_mammotion.models.work_report import WorkReportQuery


class WorkReportsApi(ApiGroup):
    """Historical work reports of one mower: aggregate, page through, and open one."""

    async def summary(self, query: WorkReportQuery) -> WorkReportSummary:
        """``POST /v1/mower/work-reports/summary``: totals over the reports ``query`` matches.

        Raises:
            ValueError: ``query.device_id`` is empty; nothing is sent.

        """
        self._require(query.device_id, "device_id")
        return await self._post("/v1/mower/work-reports/summary", query.to_dict(), WorkReportSummary)

    async def search(self, query: WorkReportQuery) -> WorkReportPage:
        """``POST /v1/mower/work-reports/search``: one page of the reports ``query`` matches.

        Raises:
            ValueError: ``query.device_id`` is empty; nothing is sent.

        """
        self._require(query.device_id, "device_id")
        return await self._post("/v1/mower/work-reports/search", query.to_dict(), WorkReportPage)

    async def get(self, device_id: str, work_id: str) -> WorkReportDetail:
        """``GET /v1/mower/{deviceId}/work-reports/{workId}``: one report in full.

        Raises:
            ValueError: ``device_id`` or ``work_id`` is empty; nothing is sent.

        """
        path = self._mower_path(device_id, "work-reports", self._require(work_id, "work_id"))
        return await self._get(path, WorkReportDetail)
