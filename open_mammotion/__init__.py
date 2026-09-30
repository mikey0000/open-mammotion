"""open-mammotion: an async client for the Mammotion Open API.

``__all__`` is the supported surface (Constitution §10): the facade, credentials and
token set, the exceptions, the session seam a host may implement, and every model and
enum a host constructs or receives. ``open_mammotion.models`` re-exports the same
models.
"""

from __future__ import annotations

from open_mammotion.auth.credentials import ClientCredentials, TokenSet
from open_mammotion.client import OpenMammotion
from open_mammotion.exceptions import (
    ApiError,
    AuthError,
    CommandRejectedError,
    ContractError,
    CredentialsRejectedError,
    GrantRejectedError,
    OpenMammotionError,
    TransportError,
    UnauthorizedError,
)
from open_mammotion.models.action import ActionResult, WorkAction
from open_mammotion.models.device import DeviceDetail, DeviceInfo, DeviceStatus, Network, NetworkType
from open_mammotion.models.fault import Attachment, Fault, FaultLevel, FaultPage, FaultQuery, NotificationPriority
from open_mammotion.models.local_network import DispatchStatus, LocalNetworkConfig, LocalNetworkDevice, WsTicket
from open_mammotion.models.task import WorkTask
from open_mammotion.models.work_params import ChannelMode, JobContent, ObstacleMode, PathOrder, TowardMode, WorkParams
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
from open_mammotion.transport.session import HttpResponse, HttpSession

__all__ = [
    "ActionResult",
    "ApiError",
    "Attachment",
    "AuthError",
    "ChannelMode",
    "ClientCredentials",
    "CommandRejectedError",
    "ContractError",
    "CredentialsRejectedError",
    "DeviceDetail",
    "DeviceInfo",
    "DeviceStatus",
    "DispatchStatus",
    "Fault",
    "FaultLevel",
    "FaultPage",
    "FaultQuery",
    "GrantRejectedError",
    "HttpResponse",
    "HttpSession",
    "JobContent",
    "LocalNetworkConfig",
    "LocalNetworkDevice",
    "Network",
    "NetworkType",
    "NotificationPriority",
    "ObstacleMode",
    "OpenMammotion",
    "OpenMammotionError",
    "PathOrder",
    "ReportJobContent",
    "TokenSet",
    "TowardMode",
    "TransportError",
    "UnauthorizedError",
    "WorkAction",
    "WorkEvent",
    "WorkParams",
    "WorkProcessEvent",
    "WorkReport",
    "WorkReportDetail",
    "WorkReportPage",
    "WorkReportQuery",
    "WorkReportSummary",
    "WorkResult",
    "WorkTask",
    "WorkType",
    "WsTicket",
]
