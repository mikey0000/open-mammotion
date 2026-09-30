"""Spec-example JSON for every wire model, one builder per schema.

Values are the examples in ``docs/openapi/mower.json``; where a schema has no example
the values are plausible stand-ins within the documented ranges.
"""

from __future__ import annotations

from typing import Any


def network_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "usedNetwork": "1",
        "wifiAvailable": True,
        "wifiRssi": -46,
        "wifiIp": "192.168.1.100",
        "cellularAvailable": True,
        "cellularRssi": -46,
    }
    return {**body, **overrides}


def device_info_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "123",
        "name": "Mower",
        "nickname": "My Mower",
        "model": "Luba2 AWD 5000",
        "icon": "https://XXXX/XX",
        "online": 1,
    }
    return {**body, **overrides}


def device_detail_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        **device_info_json(),
        "version": "1.0.0.1",
        "status": "StandBy",
        "batteryLevel": 100,
        "chargeStatus": 1,
        "network": network_json(),
    }
    return {**body, **overrides}


def action_result_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"commandResult": True, "resultMessage": "Command issued"}
    return {**body, **overrides}


def work_params_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "commandResult": True,
        "resultMessage": "Command issued",
        "edgeMode": 1,
        "rideBoundaryDistance": 0.5,
        "channelMode": 0,
        "jobContent": 8,
        "dumpPeriodSqm": 100,
        "knifeHeight": 60,
        "speed": 1,
        "channelWidth": 25,
        "toward": 90,
        "towardMode": 1,
        "towardIncludedAngle": 45,
        "ultraWave": 10,
        "boundaryZigzagOrder": 0,
        "forbiddenAreaCircleTimes": 1,
        "visualHashs": ["hash-a", "hash-b"],
    }
    return {**body, **overrides}


def work_task_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"taskId": "task-1", "taskName": "Front lawn"}
    return {**body, **overrides}


def work_report_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "workId": "work-1",
        "endWorkTime": 1_727_701_800_250,
        "workType": 2,
        "workResult": 5,
        "workProgress": 100.0,
        "workArea": 412.5,
        "workTimeUsed": 5400,
    }
    return {**body, **overrides}


def work_report_detail_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "workArea": 412.5,
        "workTimeUsed": 5400,
        "saveTime": 90.0,
        "carbonReduction": 1250.5,
        "energyConsume": 86.4,
        "startWorkTime": 1_727_696_400_000,
        "endWorkTime": 1_727_701_800_250,
        "workType": 2,
        "jobContent": 2,
        "workProcess": [
            {"timeStamp": 1_727_696_400_000, "eventCode": 1},
            {"timeStamp": 1_727_701_800_250, "eventCode": 12},
        ],
        "workParam": work_params_json(),
        "mapFilePath": "https://cdn.example.invalid/maps/work-1.json?sig=abc",
    }
    return {**body, **overrides}


def fault_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": 1005,
        "implication": "Blade motor overloaded",
        "solution": "Clear debris from the blade disc",
        "gmtCreate": 1_727_700_000_123,
        "createTime": 1_727_700_001_000,
        "faultLevel": 2,
        "priority": 3,
        "imageList": [{"buttonName": "", "buttonType": "image", "url": "https://cdn.example.invalid/a.png", "sort": 1}],
        "videoList": [],
        "buttonList": [{"buttonName": "Help", "buttonType": "link", "url": "https://help.example.invalid", "sort": 2}],
    }
    return {**body, **overrides}


def local_network_config_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "deviceName": "Luba-VS123456",
        "clientId": "cid-test",
        "redirectUri": "https://ha.example.invalid/auth/external/callback",
        "enabled": 1,
        "dispatchStatus": 1,
        "failReason": None,
    }
    return {**body, **overrides}


def ws_ticket_json(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticketId": "ticket-1",
        "productKey": "pk-test",
        "deviceName": "Luba-VS123456",
        "userId": "user-1",
        "clientId": "cid-test",
        "allowedIp": "",
        "iat": 1_727_700_000,
        "exp": 1_727_703_600,
        "sign": "0f" * 32,
    }
    return {**body, **overrides}
