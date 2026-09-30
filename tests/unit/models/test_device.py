from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mashumaro.exceptions import MissingField
import pytest

from open_mammotion.models.device import DeviceDetail, DeviceInfo, DeviceStatus, Network, NetworkType
from tests.unit.models._helpers import device_detail_json, device_info_json, network_json

if TYPE_CHECKING:
    from typing import Any


def _unknown_warnings(caplog: pytest.LogCaptureFixture, enum_name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.WARNING and f"Unknown {enum_name}" in r.getMessage()]


class TestDeviceInfoDecode:
    def test_decodes_the_spec_example(self) -> None:
        info = DeviceInfo.from_dict(device_info_json())

        assert info == DeviceInfo(
            device_id="123",
            name="Mower",
            nickname="My Mower",
            model="Luba2 AWD 5000",
            icon_url="https://XXXX/XX",
            online=True,
        )

    @pytest.mark.parametrize(("wire", "expected"), [(1, True), (0, False), ("1", True), ("0", False), (True, True)])
    def test_coerces_online_from_integer_or_string(self, wire: Any, *, expected: bool) -> None:
        assert DeviceInfo.from_dict(device_info_json(online=wire)).online is expected

    def test_defaults_optional_fields_when_absent(self) -> None:
        info = DeviceInfo.from_dict({"id": "123"})

        assert info == DeviceInfo(device_id="123")
        assert info.name is None
        assert info.online is False

    def test_ignores_unknown_keys(self) -> None:
        assert DeviceInfo.from_dict(device_info_json(firmwareChannel="beta")) == DeviceInfo.from_dict(
            device_info_json()
        )

    def test_raises_missing_field_without_an_id(self) -> None:
        body = device_info_json()
        del body["id"]

        with pytest.raises(MissingField, match="device_id"):
            DeviceInfo.from_dict(body)


class TestDeviceInfoEncode:
    def test_to_dict_uses_wire_aliases_and_integer_booleans(self) -> None:
        assert DeviceInfo.from_dict(device_info_json()).to_dict() == device_info_json()

    def test_to_dict_omits_absent_optional_fields(self) -> None:
        assert DeviceInfo(device_id="123").to_dict() == {"id": "123", "online": 0}


class TestDeviceDetailDecode:
    def test_decodes_the_spec_example(self) -> None:
        detail = DeviceDetail.from_dict(device_detail_json())

        assert detail.device_id == "123"
        assert detail.icon_url == "https://XXXX/XX"
        assert detail.online is True
        assert detail.version == "1.0.0.1"
        assert detail.status is DeviceStatus.STANDBY
        assert detail.battery_level == 100
        assert detail.charging is True
        assert detail.network == Network(
            used_network=NetworkType.WIFI,
            wifi_available=True,
            wifi_rssi=-46,
            wifi_ip="192.168.1.100",
            cellular_available=True,
            cellular_rssi=-46,
        )

    def test_is_a_device_info(self) -> None:
        assert isinstance(DeviceDetail.from_dict(device_detail_json()), DeviceInfo)

    @pytest.mark.parametrize(("wire", "expected"), [(1, True), (0, False), ("1", True), ("0", False)])
    def test_coerces_charge_status_to_charging(self, wire: Any, *, expected: bool) -> None:
        assert DeviceDetail.from_dict(device_detail_json(chargeStatus=wire)).charging is expected

    @pytest.mark.parametrize(
        ("wire", "expected"),
        [
            ("Standby", DeviceStatus.STANDBY),
            ("StandBy", DeviceStatus.STANDBY),
            ("WORKING", DeviceStatus.WORKING),
            ("Paused", DeviceStatus.PAUSED),
            ("Mapping", DeviceStatus.MAPPING),
            ("Updating", DeviceStatus.UPDATING),
            ("Offline", DeviceStatus.OFFLINE),
            ("Returning", DeviceStatus.RETURNING),
            ("Abnormal", DeviceStatus.ABNORMAL),
        ],
    )
    def test_decodes_every_status_case_insensitively(self, wire: str, expected: DeviceStatus) -> None:
        assert DeviceDetail.from_dict(device_detail_json(status=wire)).status is expected

    def test_decodes_an_unknown_status_as_unknown(self) -> None:
        assert DeviceDetail.from_dict(device_detail_json(status="Hovering-detail")).status is DeviceStatus.UNKNOWN

    def test_logs_an_unknown_status_once_for_repeated_values(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())
        DeviceDetail.from_dict(device_detail_json(status="Levitating-once"))
        DeviceDetail.from_dict(device_detail_json(status="Levitating-once"))

        warnings = _unknown_warnings(caplog, "DeviceStatus")
        assert len(warnings) == 1
        assert "Levitating-once" in warnings[0].getMessage()

    def test_defaults_optional_fields_when_absent(self) -> None:
        detail = DeviceDetail.from_dict({"id": "123"})

        assert detail.status is None
        assert detail.battery_level is None
        assert detail.charging is False
        assert detail.network is None

    def test_ignores_unknown_keys(self) -> None:
        assert DeviceDetail.from_dict(device_detail_json(bladeWear=3)) == DeviceDetail.from_dict(device_detail_json())

    def test_raises_missing_field_without_an_id(self) -> None:
        body = device_detail_json()
        del body["id"]

        with pytest.raises(MissingField, match="device_id"):
            DeviceDetail.from_dict(body)

    def test_to_dict_round_trips_by_alias(self) -> None:
        body = device_detail_json(status="Standby")

        assert DeviceDetail.from_dict(body).to_dict() == body


class TestDeviceStatus:
    def test_matches_spec_values_case_insensitively(self) -> None:
        assert DeviceStatus("StandBy") is DeviceStatus.STANDBY

    def test_values_are_the_spec_names_verbatim(self) -> None:
        assert [s.value for s in DeviceStatus if s is not DeviceStatus.UNKNOWN] == [
            "Standby",
            "Working",
            "Paused",
            "Mapping",
            "Updating",
            "Offline",
            "Returning",
            "Abnormal",
        ]


class TestNetworkDecode:
    @pytest.mark.parametrize(
        ("wire", "expected"), [("1", NetworkType.WIFI), ("2", NetworkType.CELLULAR), (2, NetworkType.CELLULAR)]
    )
    def test_decodes_used_network_string_to_enum(self, wire: Any, expected: NetworkType) -> None:
        assert Network.from_dict(network_json(usedNetwork=wire)).used_network is expected

    @pytest.mark.parametrize("wire", ["7", "-1", "satellite", 9])
    def test_decodes_an_unknown_used_network_as_unknown(self, wire: Any) -> None:
        assert Network.from_dict(network_json(usedNetwork=wire)).used_network is NetworkType.UNKNOWN

    def test_logs_an_unknown_used_network_once_for_repeated_values(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("open_mammotion.models.common._UNKNOWN_SEEN", set())
        Network.from_dict(network_json(usedNetwork="42"))
        Network.from_dict(network_json(usedNetwork="42"))

        assert len(_unknown_warnings(caplog, "NetworkType")) == 1

    def test_defaults_optional_fields_when_absent(self) -> None:
        assert Network.from_dict({}) == Network()

    def test_ignores_unknown_keys(self) -> None:
        assert Network.from_dict(network_json(ethernet=False)) == Network.from_dict(network_json())

    def test_to_dict_sends_used_network_back_as_the_wire_string(self) -> None:
        assert Network.from_dict(network_json()).to_dict() == network_json()

    def test_to_dict_omits_used_network_when_absent(self) -> None:
        assert Network().to_dict() == {"wifiAvailable": False, "cellularAvailable": False}


class TestDeviceDetailEncode:
    def test_to_dict_omits_an_absent_network(self) -> None:
        assert "network" not in DeviceDetail(device_id="123").to_dict()
