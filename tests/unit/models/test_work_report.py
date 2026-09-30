from __future__ import annotations

from datetime import UTC, datetime
import logging

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.work_params import WorkParams
from open_mammotion.models.work_report import (
    ReportJobContent,
    WorkEvent,
    WorkProcessEvent,
    WorkReport,
    WorkReportDetail,
    WorkReportPage,
    WorkReportQuery,
    WorkReportSummary,
    WorkResult,
    WorkType,
)
from tests.unit.models._helpers import work_report_detail_json, work_report_json


class TestWorkReportQuery:
    def test_serialises_only_device_and_paging_by_default(self) -> None:
        query = WorkReportQuery(device_id="dev-1")

        assert query.to_dict() == {"deviceId": "dev-1", "pageSize": 10, "pageNumber": 1}

    def test_serialises_every_filter_under_its_wire_name(self) -> None:
        query = WorkReportQuery(
            device_id="dev-1",
            page_size=50,
            page_number=3,
            end_time_from_ms=1_727_696_400_000,
            end_time_to_ms=1_727_701_800_250,
            work_type=WorkType.DROP_MOW,
            work_result=WorkResult.INTERRUPTED,
        )

        assert query.to_dict() == {
            "deviceId": "dev-1",
            "pageSize": 50,
            "pageNumber": 3,
            "endWorkTimeStart": 1_727_696_400_000,
            "endWorkTimeEnd": 1_727_701_800_250,
            "workType": 3,
            "workResult": 4,
        }

    def test_serialises_enums_as_plain_integers(self) -> None:
        body = WorkReportQuery(device_id="dev-1", work_type=WorkType.SINGLE).to_dict()

        assert type(body["workType"]) is int

    def test_exposes_filter_bounds_as_utc_datetimes(self) -> None:
        query = WorkReportQuery(device_id="dev-1", end_time_from_ms=1_727_696_400_000, end_time_to_ms=1_727_701_800_250)

        assert query.end_time_from == datetime(2024, 9, 30, 11, 40, tzinfo=UTC)
        assert query.end_time_to == datetime(2024, 9, 30, 13, 10, 0, 250_000, tzinfo=UTC)

    def test_unset_filter_bounds_yield_none(self) -> None:
        query = WorkReportQuery(device_id="dev-1")

        assert query.end_time_from is None
        assert query.end_time_to is None


class TestWorkReportSummary:
    def test_decodes_every_alias(self) -> None:
        summary = WorkReportSummary.from_dict(
            {"saveTime": 90.5, "carbonReduction": 1250.5, "workCount": 7, "totalWorkArea": 2887.5}
        )

        assert summary == WorkReportSummary(
            time_saved_min=90.5, carbon_reduction_g=1250.5, work_count=7, total_work_area_m2=2887.5
        )

    def test_defaults_missing_totals_to_zero(self) -> None:
        assert WorkReportSummary.from_dict({}) == WorkReportSummary(
            time_saved_min=0.0, carbon_reduction_g=0.0, work_count=0, total_work_area_m2=0.0
        )


class TestWorkReport:
    def test_decodes_every_alias(self) -> None:
        report = WorkReport.from_dict(work_report_json())

        assert report == WorkReport(
            work_id="work-1",
            end_time_ms=1_727_701_800_250,
            work_type=WorkType.SCHEDULED,
            work_result=WorkResult.COMPLETED,
            progress_pct=100.0,
            work_area_m2=412.5,
            duration_s=5400,
        )

    def test_exposes_end_time_as_utc_datetime(self) -> None:
        report = WorkReport.from_dict(work_report_json())

        assert report.end_time == datetime(2024, 9, 30, 13, 10, 0, 250_000, tzinfo=UTC)

    def test_keeps_the_specs_own_unknown_result_distinct_from_the_sentinel(self) -> None:
        report = WorkReport.from_dict(work_report_json(workResult=0))

        assert report.work_result is WorkResult.UNKNOWN_RESULT

    def test_decodes_an_unlisted_result_as_unknown(self) -> None:
        report = WorkReport.from_dict(work_report_json(workResult=9_101))

        assert report.work_result is WorkResult.UNKNOWN

    def test_decodes_an_unlisted_type_as_unknown(self) -> None:
        report = WorkReport.from_dict(work_report_json(workType=9_102))

        assert report.work_type is WorkType.UNKNOWN

    def test_logs_an_unlisted_value_once(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())

        WorkReport.from_dict(work_report_json(workType=9_103))
        WorkReport.from_dict(work_report_json(workType=9_103))

        assert [r.levelno for r in caplog.records if "9103" in r.getMessage()] == [logging.WARNING]

    def test_optional_parts_default_when_absent(self) -> None:
        report = WorkReport.from_dict({"workId": "work-1", "endWorkTime": 1_727_701_800_250})

        assert report.work_type is WorkType.UNKNOWN
        assert report.work_result is WorkResult.UNKNOWN
        assert (report.progress_pct, report.work_area_m2, report.duration_s) == (0.0, 0.0, 0)

    def test_rejects_a_record_without_a_work_id(self) -> None:
        body = work_report_json()
        del body["workId"]

        with pytest.raises(MissingField, match="work_id"):
            WorkReport.from_dict(body)

    def test_rejects_a_record_without_an_end_time(self) -> None:
        body = work_report_json()
        del body["endWorkTime"]

        with pytest.raises(MissingField, match="end_time_ms"):
            WorkReport.from_dict(body)


class TestWorkReportPage:
    def test_decodes_records_and_paging(self) -> None:
        page = WorkReportPage.from_dict(
            {"records": [work_report_json()], "total": 21, "pageNumber": 2, "pageSize": 10, "pages": 3}
        )

        assert [r.work_id for r in page.records] == ["work-1"]
        assert (page.total, page.page_number, page.page_size, page.pages) == (21, 2, 10, 3)

    def test_an_empty_page_has_no_records(self) -> None:
        page = WorkReportPage.from_dict({})

        assert page.records == []
        assert page.total == 0


class TestWorkProcessEvent:
    def test_decodes_the_spec_wire_names(self) -> None:
        event = WorkProcessEvent.from_dict({"timeStamp": 1_727_696_400_000, "eventCode": 10})

        assert event == WorkProcessEvent(timestamp_ms=1_727_696_400_000, event=WorkEvent.LOW_BATTERY_RECHARGE)

    def test_exposes_timestamp_as_utc_datetime(self) -> None:
        event = WorkProcessEvent.from_dict({"timeStamp": 1_727_696_400_000, "eventCode": 1})

        assert event.timestamp == datetime(2024, 9, 30, 11, 40, tzinfo=UTC)

    def test_decodes_an_unlisted_event_as_unknown(self) -> None:
        event = WorkProcessEvent.from_dict({"timeStamp": 1_727_696_400_000, "eventCode": 9_104})

        assert event.event is WorkEvent.UNKNOWN

    def test_keeps_the_specs_none_event_distinct_from_the_sentinel(self) -> None:
        event = WorkProcessEvent.from_dict({"timeStamp": 1_727_696_400_000, "eventCode": 0})

        assert event.event is WorkEvent.NONE


class TestWorkReportDetail:
    def test_decodes_every_alias(self) -> None:
        detail = WorkReportDetail.from_dict(work_report_detail_json())

        assert detail.work_area_m2 == 412.5
        assert detail.duration_s == 5400
        assert detail.time_saved_min == 90.0
        assert detail.carbon_reduction_g == 1250.5
        assert detail.energy_wh == 86.4
        assert detail.start_time_ms == 1_727_696_400_000
        assert detail.end_time_ms == 1_727_701_800_250
        assert detail.work_type is WorkType.SCHEDULED
        assert detail.job_content is ReportJobContent.MOW_AND_COLLECT
        assert detail.events == [
            WorkProcessEvent(timestamp_ms=1_727_696_400_000, event=WorkEvent.AUTO_START),
            WorkProcessEvent(timestamp_ms=1_727_701_800_250, event=WorkEvent.COMPLETED),
        ]
        assert detail.map_file_url == "https://cdn.example.invalid/maps/work-1.json?sig=abc"

    def test_decodes_work_params_with_the_actions_model(self) -> None:
        detail = WorkReportDetail.from_dict(work_report_detail_json())

        assert isinstance(detail.work_params, WorkParams)
        assert detail.work_params.blade_height == 60

    def test_exposes_start_and_end_as_utc_datetimes(self) -> None:
        detail = WorkReportDetail.from_dict(work_report_detail_json())

        assert detail.start_time == datetime(2024, 9, 30, 11, 40, tzinfo=UTC)
        assert detail.end_time == datetime(2024, 9, 30, 13, 10, 0, 250_000, tzinfo=UTC)

    def test_uses_the_report_numbering_for_job_content(self) -> None:
        detail = WorkReportDetail.from_dict(work_report_detail_json(jobContent=1))

        assert detail.job_content is ReportJobContent.COLLECT

    def test_decodes_a_work_params_job_content_value_as_unknown(self) -> None:
        detail = WorkReportDetail.from_dict(work_report_detail_json(jobContent=8))

        assert detail.job_content is ReportJobContent.UNKNOWN

    def test_optional_parts_default_when_absent(self) -> None:
        body = work_report_detail_json()
        for key in ("workProcess", "workParam", "mapFilePath", "energyConsume"):
            del body[key]

        detail = WorkReportDetail.from_dict(body)

        assert detail.events == []
        assert detail.work_params is None
        assert detail.map_file_url is None
        assert detail.energy_wh == 0.0

    def test_rejects_a_detail_without_a_start_time(self) -> None:
        body = work_report_detail_json()
        del body["startWorkTime"]

        with pytest.raises(MissingField, match="start_time_ms"):
            WorkReportDetail.from_dict(body)
