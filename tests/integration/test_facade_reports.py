"""``OpenMammotion.work_reports`` and ``OpenMammotion.faults`` over the fake cloud's seeded history.

The Yuka has 12 reports, one a day, each ending at 18:00 UTC counting back from 2025-09-29, and 5 faults
raised at 09:00 UTC on 2025-09-30, -29, -27, -24 and -20.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from open_mammotion import FaultQuery, WorkReportQuery
from open_mammotion.models.fault import FaultLevel, NotificationPriority
from open_mammotion.models.work_params import JobContent
from open_mammotion.models.work_report import ReportJobContent, WorkEvent, WorkResult, WorkType
from tests.fakeserver.state import LUBA_ID, YUKA_ID
from tests.integration._fakeserver_client import bounded

if TYPE_CHECKING:
    from enum import IntEnum

    from open_mammotion import OpenMammotion

YUKA_REPORTS = 12
YUKA_FAULTS = 5
NEWEST_END = datetime(2025, 9, 29, 18, tzinfo=UTC)


def _is_named(member: IntEnum) -> bool:
    return member.name != "UNKNOWN"


class TestSummary:
    async def test_totals_every_report_of_the_device(self, api: OpenMammotion) -> None:
        summary = await bounded(api.work_reports.summary(WorkReportQuery(device_id=YUKA_ID)))

        assert summary.work_count == YUKA_REPORTS
        assert summary.total_work_area_m2 == pytest.approx(1935.0)
        assert summary.time_saved_min > 0
        assert summary.carbon_reduction_g == pytest.approx(1935.0 * 2.1, abs=0.5)

    async def test_totals_only_the_reports_the_filters_match(self, api: OpenMammotion) -> None:
        query = WorkReportQuery(device_id=YUKA_ID, work_type=WorkType.SCHEDULED, work_result=WorkResult.COMPLETED)

        summary = await bounded(api.work_reports.summary(query))

        assert summary.work_count == 3


class TestSearch:
    async def test_first_page_is_newest_first(self, api: OpenMammotion) -> None:
        page = await bounded(api.work_reports.search(WorkReportQuery(device_id=YUKA_ID)))

        assert [r.work_id for r in page.records[:2]] == ["work-yuka-0001", "work-yuka-0002"]
        assert page.records[0].end_time == NEWEST_END
        assert page.records[1].end_time == NEWEST_END - timedelta(days=1)

    async def test_second_page_holds_the_remainder_with_page_counts(self, api: OpenMammotion) -> None:
        page = await bounded(api.work_reports.search(WorkReportQuery(device_id=YUKA_ID, page_size=10, page_number=2)))

        assert [r.work_id for r in page.records] == ["work-yuka-0011", "work-yuka-0012"]
        assert (page.total, page.pages, page.page_number, page.page_size) == (YUKA_REPORTS, 2, 2, 10)

    async def test_filters_by_work_type(self, api: OpenMammotion) -> None:
        query = WorkReportQuery(device_id=YUKA_ID, work_type=WorkType.SCHEDULED, page_size=50)

        page = await bounded(api.work_reports.search(query))

        assert page.total == 6
        assert {r.work_type for r in page.records} == {WorkType.SCHEDULED}

    async def test_filters_by_work_result(self, api: OpenMammotion) -> None:
        query = WorkReportQuery(device_id=YUKA_ID, work_result=WorkResult.COMPLETED, page_size=50)

        page = await bounded(api.work_reports.search(query))

        assert page.total == 7
        assert {r.work_result for r in page.records} == {WorkResult.COMPLETED}
        assert {r.progress_pct for r in page.records} == {100.0}

    async def test_every_seed_record_decodes_to_named_enum_members(self, api: OpenMammotion) -> None:
        pages = [
            await bounded(api.work_reports.search(WorkReportQuery(device_id=device_id, page_size=50)))
            for device_id in (YUKA_ID, LUBA_ID)
        ]

        members = [m for page in pages for r in page.records for m in (r.work_type, r.work_result)]
        assert len(members) == 2 * (YUKA_REPORTS + 3)
        assert all(_is_named(m) for m in members)


class TestGet:
    async def test_returns_the_detail_with_timeline_params_and_map_url(self, api: OpenMammotion) -> None:
        detail = await bounded(api.work_reports.get(YUKA_ID, "work-yuka-0001"))

        assert detail.end_time == NEWEST_END
        assert detail.start_time == NEWEST_END - timedelta(hours=1)
        assert detail.start_time.tzinfo is UTC
        assert (detail.work_type, detail.job_content) == (WorkType.SCHEDULED, ReportJobContent.MOW)
        assert [(e.event, e.timestamp) for e in detail.events] == [
            (WorkEvent.AUTO_START, detail.start_time),
            (WorkEvent.COMPLETED, detail.end_time),
        ]
        assert detail.work_params is not None
        assert (detail.work_params.blade_height, detail.work_params.job_content) == (50, JobContent.MOW)
        assert detail.map_file_url == "https://cdn.fake.invalid/maps/work-yuka-0001.png?sig=fake"
        assert detail.duration_s == 3600

    async def test_an_interrupted_job_carries_its_recharge_event(self, api: OpenMammotion) -> None:
        detail = await bounded(api.work_reports.get(YUKA_ID, "work-yuka-0004"))

        assert [e.event for e in detail.events] == [
            WorkEvent.AUTO_START,
            WorkEvent.LOW_BATTERY_RECHARGE,
            WorkEvent.INTERRUPTED,
        ]
        assert detail.work_type is WorkType.DROP_MOW

    async def test_every_seed_detail_decodes_to_named_enum_members(self, api: OpenMammotion) -> None:
        page = await bounded(api.work_reports.search(WorkReportQuery(device_id=YUKA_ID, page_size=50)))
        details = [await bounded(api.work_reports.get(YUKA_ID, r.work_id)) for r in page.records]

        members = [m for d in details for m in (d.work_type, d.job_content, *(e.event for e in d.events))]
        assert all(_is_named(m) for m in members)
        assert {d.job_content for d in details} == set(ReportJobContent) - {ReportJobContent.UNKNOWN}


class TestFaultSearch:
    async def test_a_date_range_pages_newest_first_with_has_more(self, api: OpenMammotion) -> None:
        query = FaultQuery(device_id=YUKA_ID, start_date=date(2025, 9, 24), end_date=date(2025, 9, 30), page_size=2)

        page = await bounded(api.faults.search(query))

        assert [f.code for f in page.records] == [1005, 1301]
        assert (page.total, page.has_more) == (4, True)
        assert page.records[0].raised_at == datetime(2025, 9, 30, 9, tzinfo=UTC)
        assert page.records[0].recorded_at == datetime(2025, 9, 30, 9, 0, 1, 500_000, tzinfo=UTC)

    async def test_the_last_page_of_a_range_has_no_more(self, api: OpenMammotion) -> None:
        query = FaultQuery(
            device_id=YUKA_ID, start_date=date(2025, 9, 24), end_date=date(2025, 9, 30), page_size=2, page_number=2
        )

        page = await bounded(api.faults.search(query))

        assert [f.code for f in page.records] == [2711, 1005]
        assert (page.total, page.has_more) == (4, False)

    async def test_a_fault_carries_its_level_priority_and_attachments(self, api: OpenMammotion) -> None:
        page = await bounded(api.faults.search(FaultQuery(device_id=YUKA_ID, error_code="2711")))

        [fault] = page.records
        assert (fault.level, fault.priority) == (FaultLevel.CRITICAL, NotificationPriority.CRITICAL)
        assert fault.implication == "Mower lifted"
        assert [a.url for a in fault.images] == ["https://help.fake.invalid/2711.png"]
        assert [(b.button_name, b.button_type) for b in fault.buttons] == [("Contact support", "CONTACT")]
        assert fault.videos == []

    async def test_every_seed_fault_decodes_to_named_enum_members(self, api: OpenMammotion) -> None:
        page = await bounded(api.faults.search(FaultQuery(device_id=YUKA_ID, page_size=50)))

        assert page.total == YUKA_FAULTS
        assert all(_is_named(f.level) and _is_named(f.priority) for f in page.records)
