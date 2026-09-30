"""HA local-network configuration and LAN WebSocket ticket models (``docs/api/local_network.md``).

Devices here are addressed by device *name*, not device id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated

from mashumaro.types import Alias

from open_mammotion.models.common import TolerantIntEnum, WireModel, int_bool, utc_from_s

if TYPE_CHECKING:
    from datetime import datetime


class DispatchStatus(TolerantIntEnum):
    """``dispatchStatus``: whether the cloud has delivered the configuration to the mower."""

    UNKNOWN = -1
    PENDING = 0
    SUCCESS = 1
    FAILED = 2


@dataclass(frozen=True)
class LocalNetworkDevice(WireModel):
    """``DeviceHaLocalConfigSaveItem``: switch local access on or off for one mower."""

    device_name: Annotated[str, Alias("deviceName")]
    enabled: bool = int_bool(required=True)


@dataclass(frozen=True)
class LocalNetworkSaveRequest(WireModel):
    """``DeviceHaLocalConfigSaveReq``. ``redirect_uri`` is the spec's "HA OAuth redirect URI" (Q8)."""

    client_id: Annotated[str, Alias("clientId")]
    devices: list[LocalNetworkDevice]
    redirect_uri: Annotated[str | None, Alias("redirectUri")] = None


@dataclass(frozen=True)
class LocalNetworkQueryRequest(WireModel):
    """``DeviceHaLocalConfigQueryReq``; no ``device_name`` lists every configured device."""

    client_id: Annotated[str, Alias("clientId")]
    device_name: Annotated[str | None, Alias("deviceName")] = None


@dataclass(frozen=True)
class LocalNetworkConfig(WireModel):
    """``DeviceHaLocalConfigVo``: one mower's local-network configuration and its dispatch state.

    ``device_name`` and ``client_id`` are required (they identify the row); the rest default.
    """

    device_name: Annotated[str, Alias("deviceName")]
    client_id: Annotated[str, Alias("clientId")]
    redirect_uri: Annotated[str | None, Alias("redirectUri")] = None
    enabled: bool = int_bool()
    dispatch_status: Annotated[DispatchStatus, Alias("dispatchStatus")] = DispatchStatus.UNKNOWN
    fail_reason: Annotated[str | None, Alias("failReason")] = None


@dataclass(frozen=True)
class WsTicketRequest(WireModel):
    """``WsTicketReq``. ``timestamp_s`` is the client's Unix time, for skew checking; ``ip`` binds the ticket."""

    device_name: Annotated[str, Alias("deviceName")]
    timestamp_s: Annotated[int, Alias("timestamp")]
    ip: str | None = None


@dataclass(frozen=True, repr=False)
class WsTicket(WireModel):
    """A short-lived signed ticket for a LAN WebSocket connection (Q7).

    ``signature`` authenticates the holder to the mower, so it is redacted in ``repr``.
    ``allowed_ip`` is empty when the ticket is not bound to a source address. The id,
    device name, ``iat``, ``exp`` and signature are required: without them the ticket
    cannot be presented; the descriptive fields default to empty.
    """

    ticket_id: Annotated[str, Alias("ticketId")]
    device_name: Annotated[str, Alias("deviceName")]
    issued_at_s: Annotated[int, Alias("iat")]
    expires_at_s: Annotated[int, Alias("exp")]
    signature: Annotated[str, Alias("sign")] = field(repr=False)
    product_key: Annotated[str, Alias("productKey")] = ""
    user_id: Annotated[str, Alias("userId")] = ""
    client_id: Annotated[str, Alias("clientId")] = ""
    allowed_ip: Annotated[str, Alias("allowedIp")] = ""

    @property
    def issued_at(self) -> datetime:
        """When the ticket was issued, in UTC."""
        return utc_from_s(self.issued_at_s)

    @property
    def expires_at(self) -> datetime:
        """When the ticket expires, in UTC."""
        return utc_from_s(self.expires_at_s)

    def __repr__(self) -> str:
        return (
            f"WsTicket(ticket_id={self.ticket_id!r}, device_name={self.device_name!r}, "
            f"issued_at_s={self.issued_at_s!r}, expires_at_s={self.expires_at_s!r}, signature=<redacted>, "
            f"product_key={self.product_key!r}, user_id={self.user_id!r}, client_id={self.client_id!r}, "
            f"allowed_ip={self.allowed_ip!r})"
        )
