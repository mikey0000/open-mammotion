"""``LocalNetworkApi``: HA local-network configuration and the LAN WebSocket ticket (``docs/api/local_network.md``)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from open_mammotion.api._base import ApiGroup
from open_mammotion.models.local_network import (
    LocalNetworkConfig,
    LocalNetworkQueryRequest,
    LocalNetworkSaveRequest,
    WsTicket,
    WsTicketRequest,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from open_mammotion.models.local_network import LocalNetworkDevice
    from open_mammotion.transport.requester import Requester


class LocalNetworkApi(ApiGroup):
    """Let named mowers accept a local connection from an OAuth client, and mint its ticket.

    ``clock`` returns Unix seconds; it stamps the ticket request when no timestamp is given.
    """

    def __init__(self, requester: Requester, *, clock: Callable[[], float] = time.time) -> None:
        super().__init__(requester)
        self._clock = clock

    async def save(
        self, client_id: str, devices: Sequence[LocalNetworkDevice], *, redirect_uri: str | None = None
    ) -> list[LocalNetworkConfig]:
        """``POST /v1/ha/local-network/save``: store and dispatch the configuration of each device.

        Raises:
            ValueError: ``client_id`` or ``devices`` is empty; nothing is sent.

        """
        self._require(client_id, "client_id")
        if not devices:
            raise ValueError("devices must list at least one device")
        request = LocalNetworkSaveRequest(client_id=client_id, devices=list(devices), redirect_uri=redirect_uri)
        return await self._post_list("/v1/ha/local-network/save", request.to_dict(), LocalNetworkConfig)

    async def query(self, client_id: str, *, device_name: str | None = None) -> list[LocalNetworkConfig]:
        """``POST /v1/ha/local-network/query``: one device's configuration, or every one when unnamed.

        Raises:
            ValueError: ``client_id`` is empty; nothing is sent.

        """
        self._require(client_id, "client_id")
        request = LocalNetworkQueryRequest(client_id=client_id, device_name=device_name)
        return await self._post_list("/v1/ha/local-network/query", request.to_dict(), LocalNetworkConfig)

    async def ws_ticket(self, device_name: str, *, timestamp_s: int | None = None, ip: str | None = None) -> WsTicket:
        """``POST /v1/mower/ws/ticket``: a short-lived ticket for a LAN WebSocket to ``device_name``.

        ``timestamp_s`` defaults to the injected clock; ``ip`` binds the ticket to a source address.

        Raises:
            ValueError: ``device_name`` is empty; nothing is sent.

        """
        self._require(device_name, "device_name")
        stamp = int(self._clock()) if timestamp_s is None else timestamp_s
        request = WsTicketRequest(device_name=device_name, timestamp_s=stamp, ip=ip)
        return await self._post("/v1/mower/ws/ticket", request.to_dict(), WsTicket)
