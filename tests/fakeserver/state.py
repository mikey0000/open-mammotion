"""The fake cloud's mutable world: seed data, issued tokens, fault-injection knobs and request logs.

Everything a route reads or writes lives on one :class:`FakeState`; there is no module-level state.
Wire rendering (camelCase dicts in the specification's shapes) lives beside each seed record.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import itertools
import time
from typing import TYPE_CHECKING, Any

import orjson

from open_mammotion.const import DEFAULT_TOKEN_TTL_S

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

FAKE_CLIENT_ID = "cid-test"
FAKE_CLIENT_SECRET = "not-a-real-secret"
FAKE_USER_ID = "fake-user-0001"
FAKE_JWT_KEY = b"fake-jwt-signing-key"
FAKE_TICKET_KEY = b"fake-ws-ticket-signing-key"

#: 2025-09-30T00:00:00Z in milliseconds; every seed timestamp is relative to it.
SEED_BASE_MS = 1_759_190_400_000
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

YUKA_ID = "4DMCToYk7Qx2hLpe90u5oV"
YUKA_NAME = "Yuka-MV27A3F9K2"
LUBA_ID = "7KpQrLb2Xw9Zt3mN8sBdQe"
LUBA_NAME = "Luba-VS5K8D2M1"

YUKA_TASKS = ("Front lawn weekly", "Edges only")
LUBA_TASKS = ("Back garden full",)

SUBSCRIPTION_KEYS = frozenset({
    "DEV_ST", "CHG_ST", "SELF_CHK", "SENS_ST", "LOC_SRC", "BAT_PCT", "BMS_INFO", "COORD", "NET_ST", "WK_PRG", "KNF_HGT",
    "KNF_ST", "WK_TRK", "DEV_VER", "BASE_STN", "OTA_PRG", "MAP_UPLD", "LOG_SYNC", "DEV_INF", "TSK_CHG", "ENR_BIND",
    "ENR_UNBIND",
})  # fmt: skip
MAX_SUBSCRIPTION_DEVICES = 20

ACTIONS = frozenset({"CMD_START", "START", "PAUSE", "RESUME", "STOP", "RETURN", "CANCEL_RETURN"})
_STATUS_AFTER_ACTION = {
    "CMD_START": "Working",
    "START": "Working",
    "PAUSE": "Paused",
    "RESUME": "Working",
    "STOP": "Standby",
    "RETURN": "Returning",
    "CANCEL_RETURN": "Paused",
}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_jwt(claims: dict[str, Any]) -> str:
    """An HS256 JWT over ``claims`` with the fake signing key; the client treats it as opaque."""
    header = _b64url(orjson.dumps({"alg": "HS256", "typ": "JWT"}))
    payload = _b64url(orjson.dumps(claims))
    signature = hmac.new(FAKE_JWT_KEY, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


TICKET_SIGNED_FIELDS = ("ticketId", "productKey", "deviceName", "userId", "clientId", "allowedIp", "iat", "exp")


def sign_ticket(ticket: dict[str, Any]) -> str:
    """HMAC-SHA256 lowercase hex over ``TICKET_SIGNED_FIELDS`` joined by ``|``, with the fake key."""
    message = "|".join(str(ticket[name]) for name in TICKET_SIGNED_FIELDS)
    return hmac.new(FAKE_TICKET_KEY, message.encode(), hashlib.sha256).hexdigest()


@dataclass
class TokenRecord:
    """One issued access token; ``expires_at`` is absolute seconds on :attr:`FakeState.clock`."""

    client_id: str
    expires_at: float
    refresh_token: str


@dataclass(frozen=True)
class RecordedRequest:
    """One request as the fake saw it; Authorization and form secrets are replaced by fingerprints."""

    method: str
    path: str
    headers: dict[str, str]
    body: Any

    @property
    def accept_language(self) -> str | None:
        return next((v for k, v in self.headers.items() if k.lower() == "accept-language"), None)


@dataclass(frozen=True)
class ActionRecord:
    """One ``POST /v1/mower/action`` the fake received, with the verdict it answered."""

    device_id: str
    action: str
    task_name: str | None
    accepted: bool
    message: str


@dataclass
class InjectedStatus:
    """``next_status`` / ``token_next_status``: answer the next ``count`` requests with ``status``."""

    status: int
    count: int
    non_json: bool = False


@dataclass
class InjectedEnvelope:
    """``next_envelope``: answer the next ``count`` authenticated requests with HTTP 200 and this ``code``."""

    code: int
    msg: str
    count: int


@dataclass
class FakeTask:
    task_id: str
    task_name: str

    def wire(self) -> dict[str, Any]:
        return {"taskId": self.task_id, "taskName": self.task_name}


@dataclass
class FakeDevice:
    """A mower bound to the account, with everything the device, action and plan routes answer."""

    device_id: str
    name: str
    nickname: str
    model: str
    icon: str
    online: bool
    version: str
    status: str
    battery_level: int
    charging: bool
    network: dict[str, Any] | None
    product_key: str
    work_params: dict[str, Any]
    tasks: list[FakeTask]

    def info(self) -> dict[str, Any]:
        return {
            "id": self.device_id,
            "name": self.name,
            "nickname": self.nickname,
            "model": self.model,
            "icon": self.icon,
            "online": int(self.online),
        }

    def detail(self) -> dict[str, Any]:
        body = {
            "id": self.device_id,
            "name": self.name,
            "nickname": self.nickname,
            "model": self.model,
            "icon": self.icon,
            "version": self.version,
            "online": int(self.online),
            "status": self.status,
            "batteryLevel": self.battery_level,
            "chargeStatus": int(self.charging),
        }
        if self.network is not None:
            body["network"] = dict(self.network)
        return body


@dataclass
class FakeWorkReport:
    """One finished (or in-progress) job; renders as both a search record and a detail."""

    device_id: str
    work_id: str
    start_ms: int
    end_ms: int
    work_type: int
    work_result: int
    progress: float
    area_m2: float
    duration_s: int
    save_time_min: float
    carbon_g: float
    energy_wh: float
    job_content: int
    process: list[dict[str, int]]
    work_params: dict[str, Any]
    map_file_path: str

    def record(self) -> dict[str, Any]:
        return {
            "workId": self.work_id,
            "endWorkTime": self.end_ms,
            "workType": self.work_type,
            "workResult": self.work_result,
            "workProgress": self.progress,
            "workArea": self.area_m2,
            "workTimeUsed": self.duration_s,
        }

    def detail(self) -> dict[str, Any]:
        return {
            "workArea": self.area_m2,
            "workTimeUsed": self.duration_s,
            "saveTime": self.save_time_min,
            "carbonReduction": self.carbon_g,
            "energyConsume": self.energy_wh,
            "startWorkTime": self.start_ms,
            "endWorkTime": self.end_ms,
            "workType": self.work_type,
            "jobContent": self.job_content,
            "workProcess": [dict(p) for p in self.process],
            "workParam": dict(self.work_params),
            "mapFilePath": self.map_file_path,
        }


@dataclass
class FakeFault:
    device_id: str
    code: int
    implication: str
    solution: str
    gmt_create_ms: int
    create_time_ms: int
    fault_level: int
    priority: int
    images: list[dict[str, Any]] = field(default_factory=list)
    videos: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)

    def wire(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "implication": self.implication,
            "solution": self.solution,
            "gmtCreate": self.gmt_create_ms,
            "createTime": self.create_time_ms,
            "faultLevel": self.fault_level,
            "priority": self.priority,
            "imageList": [dict(a) for a in self.images],
            "videoList": [dict(a) for a in self.videos],
            "buttonList": [dict(a) for a in self.buttons],
        }


@dataclass
class FakeLocalConfig:
    device_name: str
    client_id: str
    redirect_uri: str | None
    enabled: int
    dispatch_status: int
    fail_reason: str | None

    def wire(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "deviceName": self.device_name,
            "clientId": self.client_id,
            "enabled": self.enabled,
            "dispatchStatus": self.dispatch_status,
        }
        if self.redirect_uri is not None:
            body["redirectUri"] = self.redirect_uri
        if self.fail_reason is not None:
            body["failReason"] = self.fail_reason
        return body


def _work_params(*, knife_height: int, job_content: int, hashes: list[str]) -> dict[str, Any]:
    return {
        "commandResult": True,
        "resultMessage": "Success",
        "edgeMode": 1,
        "rideBoundaryDistance": 0.25,
        "channelMode": 0,
        "jobContent": job_content,
        "dumpPeriodSqm": 150,
        "knifeHeight": knife_height,
        "speed": 3,
        "channelWidth": 25,
        "toward": 90,
        "towardMode": 0,
        "towardIncludedAngle": 90,
        "ultraWave": 10,
        "boundaryZigzagOrder": 0,
        "forbiddenAreaCircleTimes": 1,
        "visualHashs": hashes,
    }


def seed_devices() -> dict[str, FakeDevice]:
    yuka = FakeDevice(
        device_id=YUKA_ID,
        name=YUKA_NAME,
        nickname="Front Lawn",
        model="YUKA mini Vision 800",
        icon="https://icons.fake.invalid/yuka-mini-vision-800.png",
        online=True,
        version="1.2.3.4",
        status="Standby",
        battery_level=87,
        charging=True,
        network={
            "usedNetwork": "1",
            "wifiAvailable": True,
            "wifiRssi": -46,
            "wifiIp": "192.168.1.100",
            "cellularAvailable": False,
        },
        product_key="a1FakeYukaPK",
        work_params=_work_params(knife_height=50, job_content=8, hashes=["3f2a9c01", "7b1e44d2"]),
        tasks=[FakeTask(f"task-yuka-{i + 1}", name) for i, name in enumerate(YUKA_TASKS)],
    )
    luba = FakeDevice(
        device_id=LUBA_ID,
        name=LUBA_NAME,
        nickname="Back Garden",
        model="Luba2 AWD 5000",
        icon="https://icons.fake.invalid/luba2-awd-5000.png",
        online=False,
        version="1.0.0.1",
        status="Offline",
        battery_level=42,
        charging=False,
        network={
            "usedNetwork": "2",
            "wifiAvailable": False,
            "cellularAvailable": True,
            "cellularRssi": -71,
        },
        product_key="a1FakeLubaPK",
        work_params=_work_params(knife_height=60, job_content=12, hashes=["c0ffee01"]),
        tasks=[FakeTask(f"task-luba-{i + 1}", name) for i, name in enumerate(LUBA_TASKS)],
    )
    return {yuka.device_id: yuka, luba.device_id: luba}


# (workType, workResult, jobContent) per report, newest first; deliberately mixed so filters have work to do.
_YUKA_RUNS = [(2, 5, 0), (1, 5, 0), (2, 3, 2), (3, 4, 0), (2, 5, 1), (4, 5, 0),
              (2, 2, 0), (1, 5, 2), (2, 5, 0), (3, 3, 0), (2, 4, 1), (1, 5, 0)]  # fmt: skip
_LUBA_RUNS = [(2, 5, 2), (1, 4, 0), (2, 5, 2)]


def _process(start_ms: int, end_ms: int, result: int) -> list[dict[str, int]]:
    final = {5: 12, 4: 13, 3: 14}.get(result, 0)
    events = [{"timeStamp": start_ms, "eventCode": 1}]
    if result in {2, 4}:
        events.append({"timeStamp": start_ms + (end_ms - start_ms) // 2, "eventCode": 10})
    events.append({"timeStamp": end_ms, "eventCode": final})
    return events


def _reports_for(device: FakeDevice, runs: list[tuple[int, int, int]], prefix: str) -> list[FakeWorkReport]:
    reports: list[FakeWorkReport] = []
    for i, (work_type, result, job) in enumerate(runs):
        end_ms = SEED_BASE_MS - i * DAY_MS - 6 * HOUR_MS
        duration_s = 3600 + 300 * (i % 5)
        start_ms = end_ms - duration_s * 1000
        progress = 100.0 if result == 5 else round(35.0 + 5 * i, 1)
        area = round(120.0 + 7.5 * i, 1)
        reports.append(
            FakeWorkReport(
                device_id=device.device_id,
                work_id=f"{prefix}-{i + 1:04d}",
                start_ms=start_ms,
                end_ms=end_ms,
                work_type=work_type,
                work_result=result,
                progress=progress,
                area_m2=area,
                duration_s=duration_s,
                save_time_min=round(duration_s / 60 * 1.5, 1),
                carbon_g=round(area * 2.1, 1),
                energy_wh=round(duration_s / 36, 1),
                job_content=job,
                process=_process(start_ms, end_ms, result),
                work_params=dict(device.work_params),
                map_file_path=f"https://cdn.fake.invalid/maps/{prefix}-{i + 1:04d}.png?sig=fake",
            )
        )
    return reports


def seed_work_reports(devices: dict[str, FakeDevice]) -> list[FakeWorkReport]:
    return _reports_for(devices[YUKA_ID], _YUKA_RUNS, "work-yuka") + _reports_for(
        devices[LUBA_ID], _LUBA_RUNS, "work-luba"
    )


_BUTTON = {"buttonName": "Contact support", "buttonType": "CONTACT", "url": "https://help.fake.invalid/c", "sort": 1}


def seed_faults() -> list[FakeFault]:
    def fault(device_id: str, code: int, days_ago: int, level: int, priority: int, text: str) -> FakeFault:
        raised = SEED_BASE_MS - days_ago * DAY_MS + 9 * HOUR_MS
        return FakeFault(
            device_id=device_id,
            code=code,
            implication=text,
            solution=f"Follow the steps for error {code} in the app.",
            gmt_create_ms=raised,
            create_time_ms=raised + 1500,
            fault_level=level,
            priority=priority,
            images=[
                {"buttonName": "", "buttonType": "IMAGE", "url": f"https://help.fake.invalid/{code}.png", "sort": 1}
            ],
            videos=[],
            buttons=[dict(_BUTTON)],
        )

    return [
        fault(YUKA_ID, 1005, 0, 2, 2, "Left wheel motor overcurrent"),
        fault(YUKA_ID, 1301, 1, 1, 1, "Low battery, returning to charge"),
        fault(YUKA_ID, 2711, 3, 3, 3, "Mower lifted"),
        fault(YUKA_ID, 1005, 6, 2, 2, "Left wheel motor overcurrent"),
        fault(YUKA_ID, 1302, 10, 1, 0, "Charging station not found"),
        fault(LUBA_ID, 2711, 2, 3, 3, "Mower lifted"),
        fault(LUBA_ID, 1106, 4, 2, 2, "Blade motor stalled"),
        fault(LUBA_ID, 1301, 8, 1, 1, "Low battery, returning to charge"),
    ]


def seed_local_configs() -> list[FakeLocalConfig]:
    return [FakeLocalConfig(YUKA_NAME, FAKE_CLIENT_ID, None, 1, 1, None)]


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass
class FakeState:
    """Seed data, issued tokens, knobs and logs for one fake-cloud instance."""

    client_id: str = FAKE_CLIENT_ID
    client_secret: str = FAKE_CLIENT_SECRET
    user_id: str = FAKE_USER_ID
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], Awaitable[None]] = _real_sleep

    devices: dict[str, FakeDevice] = field(default_factory=dict)
    work_reports: list[FakeWorkReport] = field(default_factory=list)
    faults: list[FakeFault] = field(default_factory=list)
    local_configs: list[FakeLocalConfig] = field(default_factory=list)
    subscriptions: dict[str, list[str]] = field(default_factory=dict)  # deviceId -> subscribed property keys

    tokens: dict[str, TokenRecord] = field(default_factory=dict)
    refresh_tokens: dict[str, str] = field(default_factory=dict)  # refresh token -> client_id

    success_code: int = 200
    token_ttl_s: int = int(DEFAULT_TOKEN_TTL_S)
    reject_next_refresh: bool = False
    reject_client_credentials: bool = False
    next_status: InjectedStatus | None = None
    token_next_status: InjectedStatus | None = None
    next_envelope: InjectedEnvelope | None = None
    delay_ms: int = 0
    detail_as_list: bool = False

    requests: list[RecordedRequest] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    token_grants: dict[str, int] = field(default_factory=lambda: {"client_credentials": 0, "refresh_token": 0})

    _serial: itertools.count[int] = field(default_factory=lambda: itertools.count(1), repr=False)

    def __post_init__(self) -> None:
        if not self.devices:
            self.reseed()

    def reseed(self) -> None:
        """Restore devices, reports, faults and local-network configs to the seed."""
        self.devices = seed_devices()
        self.work_reports = seed_work_reports(self.devices)
        self.faults = seed_faults()
        self.local_configs = seed_local_configs()
        self.subscriptions = {}

    def reset(self) -> None:
        """``/control {"reset": true}``: seed data, knobs, logs and counters back to defaults.

        Issued tokens survive so a client mid-session keeps working; use ``expire_tokens`` to kill them.
        """
        self.reseed()
        self.success_code = 200
        self.token_ttl_s = int(DEFAULT_TOKEN_TTL_S)
        self.reject_next_refresh = False
        self.reject_client_credentials = False
        self.next_status = None
        self.token_next_status = None
        self.next_envelope = None
        self.delay_ms = 0
        self.detail_as_list = False
        self.requests.clear()
        self.actions.clear()
        self.token_grants = {"client_credentials": 0, "refresh_token": 0}

    def next_serial(self) -> int:
        return next(self._serial)

    def next_request_id(self) -> str:
        return f"fake-req-{self.next_serial():06d}"

    def issue_token(self, client_id: str) -> tuple[str, TokenRecord]:
        """Mint an access/refresh pair for ``client_id``; returns the access token and its record."""
        serial = self.next_serial()
        now = self.clock()
        expires_at = now + self.token_ttl_s
        access = make_jwt(
            {"aud": client_id, "sub": self.user_id, "iat": int(now), "exp": int(expires_at), "jti": f"jti-{serial:06d}"}
        )
        refresh = f"rt-{serial:06d}-{hashlib.sha256(access.encode()).hexdigest()[:16]}"
        record = TokenRecord(client_id=client_id, expires_at=expires_at, refresh_token=refresh)
        self.tokens[access] = record
        self.refresh_tokens[refresh] = client_id
        return access, record

    def expire_tokens(self) -> None:
        now = self.clock()
        for record in self.tokens.values():
            record.expires_at = min(record.expires_at, now)

    def record_request(self, *, method: str, path: str, headers: dict[str, str], body: Any) -> None:
        self.requests.append(RecordedRequest(method=method, path=path, headers=headers, body=body))

    @property
    def requests_total(self) -> int:
        return len(self.requests)

    def take_api_fault(self) -> InjectedStatus | None:
        fault, self.next_status = _take(self.next_status)
        return fault

    def take_token_fault(self) -> InjectedStatus | None:
        fault, self.token_next_status = _take(self.token_next_status)
        return fault

    def take_envelope_fault(self) -> InjectedEnvelope | None:
        forced = self.next_envelope
        if forced is None or forced.count <= 0:
            self.next_envelope = None
            return None
        forced.count -= 1
        if forced.count == 0:
            self.next_envelope = None
        return forced

    def device_by_name(self, device_name: str) -> FakeDevice | None:
        return next((d for d in self.devices.values() if d.name == device_name), None)

    def apply_action(self, device: FakeDevice, action: str) -> None:
        device.status = _STATUS_AFTER_ACTION[action]
        if action in {"CMD_START", "START", "RESUME"}:
            device.charging = False

    def knobs(self) -> dict[str, Any]:
        """The knob values ``GET /control`` reports."""
        return {
            "envelope_code": self.success_code,
            "token_ttl_s": self.token_ttl_s,
            "reject_next_refresh": self.reject_next_refresh,
            "reject_client_credentials": self.reject_client_credentials,
            "next_status": _status_dict(self.next_status),
            "token_next_status": _status_dict(self.token_next_status),
            "next_envelope": None
            if self.next_envelope is None
            else {"code": self.next_envelope.code, "msg": self.next_envelope.msg, "count": self.next_envelope.count},
            "delay_ms": self.delay_ms,
            "detail_as_list": self.detail_as_list,
        }


def _status_dict(fault: InjectedStatus | None) -> dict[str, Any] | None:
    if fault is None:
        return None
    return {"status": fault.status, "count": fault.count, "non_json": fault.non_json}


def _take(fault: InjectedStatus | None) -> tuple[InjectedStatus | None, InjectedStatus | None]:
    """Consume one use of ``fault``; returns ``(fault_to_apply, remaining)``."""
    if fault is None or fault.count <= 0:
        return None, None
    fault.count -= 1
    return fault, (fault if fault.count > 0 else None)
