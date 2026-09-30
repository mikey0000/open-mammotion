from __future__ import annotations

from datetime import UTC, date, datetime
import logging

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.fault import Attachment, Fault, FaultLevel, FaultPage, FaultQuery, NotificationPriority
from tests.unit.models._helpers import fault_json


class TestFaultQuery:
    def test_serialises_only_device_and_paging_by_default(self) -> None:
        query = FaultQuery(device_id="dev-1")

        assert query.to_dict() == {"deviceId": "dev-1", "pageSize": 10, "pageNumber": 1}

    def test_serialises_every_filter_under_its_wire_name(self) -> None:
        query = FaultQuery(
            device_id="dev-1",
            page_size=20,
            page_number=2,
            start_date=date(2024, 9, 1),
            end_date=date(2024, 9, 30),
            error_code="1005",
        )

        assert query.to_dict() == {
            "deviceId": "dev-1",
            "pageSize": 20,
            "pageNumber": 2,
            "startDate": "2024-09-01",
            "endDate": "2024-09-30",
            "errorCode": "1005",
        }


class TestAttachment:
    def test_decodes_every_alias(self) -> None:
        attachment = Attachment.from_dict(
            {"buttonName": "Help", "buttonType": "link", "url": "https://help.example.invalid", "sort": 2}
        )

        assert attachment == Attachment(
            button_name="Help", button_type="link", url="https://help.example.invalid", sort=2
        )

    def test_defaults_everything_but_the_url(self) -> None:
        assert Attachment.from_dict({"url": "https://help.example.invalid"}) == Attachment(
            url="https://help.example.invalid", button_name="", button_type="", sort=0
        )


class TestFault:
    def test_decodes_every_alias(self) -> None:
        fault = Fault.from_dict(fault_json())

        assert fault.code == 1005
        assert fault.implication == "Blade motor overloaded"
        assert fault.solution == "Clear debris from the blade disc"
        assert fault.raised_at_ms == 1_727_700_000_123
        assert fault.recorded_at_ms == 1_727_700_001_000
        assert fault.level is FaultLevel.WARNING
        assert fault.priority is NotificationPriority.CRITICAL
        assert fault.images == [
            Attachment(button_name="", button_type="image", url="https://cdn.example.invalid/a.png", sort=1)
        ]
        assert fault.videos == []
        assert fault.buttons == [
            Attachment(button_name="Help", button_type="link", url="https://help.example.invalid", sort=2)
        ]

    def test_exposes_both_timestamps_as_utc_datetimes(self) -> None:
        fault = Fault.from_dict(fault_json())

        assert fault.raised_at == datetime(2024, 9, 30, 12, 40, 0, 123_000, tzinfo=UTC)
        assert fault.recorded_at == datetime(2024, 9, 30, 12, 40, 1, tzinfo=UTC)

    def test_decodes_an_unlisted_level_as_unknown(self) -> None:
        assert Fault.from_dict(fault_json(faultLevel=9_201)).level is FaultLevel.UNKNOWN

    def test_decodes_an_unlisted_priority_as_unknown(self) -> None:
        assert Fault.from_dict(fault_json(priority=9_202)).priority is NotificationPriority.UNKNOWN

    def test_keeps_the_specs_none_priority_distinct_from_the_sentinel(self) -> None:
        assert Fault.from_dict(fault_json(priority=0)).priority is NotificationPriority.NONE

    def test_logs_an_unlisted_value_once(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())

        Fault.from_dict(fault_json(faultLevel=9_203))
        Fault.from_dict(fault_json(faultLevel=9_203))

        assert [r.levelno for r in caplog.records if "9203" in r.getMessage()] == [logging.WARNING]

    def test_optional_parts_default_when_absent(self) -> None:
        fault = Fault.from_dict({"code": 1005, "gmtCreate": 1_727_700_000_123, "createTime": 1_727_700_001_000})

        assert (fault.implication, fault.solution) == ("", "")
        assert fault.level is FaultLevel.UNKNOWN
        assert fault.priority is NotificationPriority.UNKNOWN
        assert (fault.images, fault.videos, fault.buttons) == ([], [], [])

    def test_rejects_a_record_without_a_code(self) -> None:
        body = fault_json()
        del body["code"]

        with pytest.raises(MissingField, match="code"):
            Fault.from_dict(body)

    def test_rejects_a_record_without_an_alert_time(self) -> None:
        body = fault_json()
        del body["gmtCreate"]

        with pytest.raises(MissingField, match="raised_at_ms"):
            Fault.from_dict(body)


class TestFaultPage:
    def test_decodes_records_and_paging(self) -> None:
        page = FaultPage.from_dict(
            {"records": [fault_json()], "total": 11, "pageNumber": 1, "pageSize": 10, "hasMore": True}
        )

        assert [f.code for f in page.records] == [1005]
        assert (page.total, page.page_number, page.page_size) == (11, 1, 10)
        assert page.has_more is True

    def test_an_empty_page_has_no_more(self) -> None:
        page = FaultPage.from_dict({})

        assert page.records == []
        assert page.has_more is False
