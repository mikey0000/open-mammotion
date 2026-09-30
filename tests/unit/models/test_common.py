"""The envelope, the success rule, the tolerant enum bases, ``int_bool`` and the timestamp helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Annotated

from mashumaro.exceptions import InvalidFieldValue, MissingField
from mashumaro.types import Alias
import orjson
import pytest

from open_mammotion.models.common import (
    SUCCESS_CODES,
    Envelope,
    IntBool,
    TolerantIntEnum,
    TolerantStrEnum,
    WireModel,
    int_bool,
    utc_from_ms,
    utc_from_s,
)


class Level(TolerantIntEnum):
    UNKNOWN = -1
    INFO = 1
    CRITICAL = 3


class Status(TolerantStrEnum):
    UNKNOWN = "UNKNOWN"
    STANDBY = "Standby"
    WORKING = "Working"


@dataclass(frozen=True)
class Sample(WireModel):
    device_id: Annotated[str, Alias("id")]
    enabled: bool = int_bool(required=True)
    level: Level = Level.UNKNOWN
    status: Status = Status.UNKNOWN
    note: str | None = None
    online: bool = int_bool()


@pytest.fixture
def _fresh_unknown_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())


class TestSuccessCodes:
    @pytest.mark.parametrize("code", [0, 200])
    def test_both_documented_success_codes_are_ok(self, code: int) -> None:
        assert code in SUCCESS_CODES
        assert Envelope(code=code).ok

    @pytest.mark.parametrize("code", [400, 401, 404, 40101, -1])
    def test_anything_else_is_not_ok(self, code: int) -> None:
        assert not Envelope(code=code).ok


class TestEnvelope:
    def test_decodes_every_documented_field_by_alias(self) -> None:
        env = Envelope.from_dict(
            {"code": 0, "msg": "Request success", "msgTitle": "Operation Successful", "data": [1], "requestId": "r-1"}
        )

        assert env == Envelope(
            code=0, msg="Request success", msg_title="Operation Successful", data=[1], request_id="r-1"
        )

    def test_coerces_an_integer_request_id_to_a_string(self) -> None:
        env = Envelope.from_dict({"code": 200, "requestId": 176853488788872870010})

        assert env.request_id == "176853488788872870010"

    def test_optional_fields_default_when_absent(self) -> None:
        env = Envelope.from_dict({"code": 0})

        assert (env.msg, env.msg_title, env.data, env.request_id) == ("", None, None, None)

    def test_code_is_required(self) -> None:
        with pytest.raises(MissingField):
            Envelope.from_dict({"msg": "no code"})


class TestTolerantIntEnum:
    def test_known_values_decode_to_their_member(self) -> None:
        assert Level(3) is Level.CRITICAL

    @pytest.mark.usefixtures("_fresh_unknown_log")
    def test_unknown_value_decodes_to_unknown_and_warns_once(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            first, second = Level(99), Level(99)

        assert first is Level.UNKNOWN
        assert second is Level.UNKNOWN
        warnings = [r for r in caplog.records if "Unknown Level value 99" in r.getMessage()]
        assert len(warnings) == 1

    @pytest.mark.usefixtures("_fresh_unknown_log")
    def test_each_distinct_unknown_value_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            Level(98)
            Level(97)

        assert sum("Unknown Level value" in r.getMessage() for r in caplog.records) == 2


class TestTolerantStrEnum:
    def test_matches_case_insensitively(self) -> None:
        assert Status("StandBy") is Status.STANDBY
        assert Status("WORKING") is Status.WORKING

    @pytest.mark.usefixtures("_fresh_unknown_log")
    def test_unknown_value_decodes_to_unknown_and_warns_once(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            Status("Dancing")
            Status("Dancing")

        assert Status("Dancing") is Status.UNKNOWN
        assert sum("Unknown Status value 'Dancing'" in r.getMessage() for r in caplog.records) == 1

    def test_non_string_value_decodes_to_unknown(self) -> None:
        assert Status(7) is Status.UNKNOWN


class TestIntBool:
    @pytest.mark.parametrize(
        ("wire", "expected"),
        [
            (1, True),
            (0, False),
            ("1", True),
            ("0", False),
            (" 0 ", False),
            ("TRUE", True),
            ("false", False),
            (True, True),
        ],
    )
    def test_deserialize_accepts_every_documented_spelling(self, wire: object, expected: bool) -> None:
        assert IntBool().deserialize(wire) is expected

    @pytest.mark.parametrize("wire", [None, 2, -1, "", "yes", "no", 1.0, []])
    def test_deserialize_rejects_anything_else(self, wire: object) -> None:
        with pytest.raises(ValueError, match="not a 1/0 boolean"):
            IntBool().deserialize(wire)

    @pytest.mark.parametrize(("value", "wire"), [(True, 1), (False, 0)])
    def test_serialize_emits_the_integer(self, value: bool, wire: int) -> None:
        assert IntBool().serialize(value) == wire

    def test_field_defaults_to_false_when_absent(self) -> None:
        assert Sample.from_dict({"id": "x", "enabled": 1}).online is False

    def test_required_field_is_missing_when_absent(self) -> None:
        with pytest.raises(MissingField, match="enabled"):
            Sample.from_dict({"id": "x"})

    def test_round_trips_as_integers(self) -> None:
        body = Sample(device_id="x", online=True, enabled=False).to_dict()

        assert (body["online"], body["enabled"]) == (1, 0)


class TestWireModel:
    def test_decodes_by_alias_and_ignores_unknown_keys(self) -> None:
        sample = Sample.from_dict({"id": "x", "enabled": 1, "level": 1, "status": "Standby", "surprise": 42})

        assert sample == Sample(device_id="x", enabled=True, level=Level.INFO, status=Status.STANDBY)

    def test_serialises_by_alias_and_omits_none(self) -> None:
        body = Sample(device_id="x", enabled=True).to_dict()

        assert body == {"id": "x", "level": -1, "status": "UNKNOWN", "online": 0, "enabled": 1}

    def test_round_trips_through_json(self) -> None:
        sample = Sample(device_id="x", enabled=True, note="hi")

        assert Sample.from_json(sample.to_json()) == sample
        assert orjson.loads(sample.to_json())["note"] == "hi"

    def test_missing_required_field_raises_missing_field(self) -> None:
        with pytest.raises(MissingField, match="device_id"):
            Sample.from_dict({"enabled": 0})

    @pytest.mark.parametrize("value", [None, 7, ["x"], {"id": "x"}])
    def test_required_str_field_refuses_non_strings(self, value: object) -> None:
        with pytest.raises(InvalidFieldValue, match="device_id"):
            Sample.from_dict({"id": value, "enabled": 1})

    def test_optional_str_field_still_accepts_null(self) -> None:
        assert Sample.from_dict({"id": "x", "enabled": 1, "note": None}).note is None

    def test_required_str_check_applies_to_inherited_fields(self) -> None:
        @dataclass(frozen=True)
        class Child(Sample):
            extra: str = ""

        with pytest.raises(InvalidFieldValue, match="device_id"):
            Child.from_dict({"id": None, "enabled": 1})


class TestTimestamps:
    def test_utc_from_ms_is_exact_to_the_millisecond(self) -> None:
        assert utc_from_ms(1_700_000_000_123) == datetime(2023, 11, 14, 22, 13, 20, 123_000, tzinfo=UTC)

    def test_utc_from_s(self) -> None:
        assert utc_from_s(1_700_000_000) == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)

    def test_zero_is_the_epoch(self) -> None:
        assert utc_from_ms(0) == datetime(1970, 1, 1, tzinfo=UTC)
