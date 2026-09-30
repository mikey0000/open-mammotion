"""``FakeCloud``: runs :func:`create_app` on an ephemeral loopback port for the duration of an ``async with``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

import aiohttp
from aiohttp import web

from tests.fakeserver.app import create_app
from tests.fakeserver.state import FakeState

if TYPE_CHECKING:
    from types import TracebackType

LOOPBACK = "127.0.0.1"
CONTROL_TIMEOUT_S = 5


class FakeCloud:
    """The fake cloud as an async context manager; point both base URLs at :attr:`url`."""

    def __init__(self, state: FakeState | None = None, *, host: str = LOOPBACK, port: int = 0) -> None:
        self.state = state if state is not None else FakeState()
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None
        self._session: aiohttp.ClientSession | None = None
        self.url = ""

    async def start(self) -> None:
        self._runner = web.AppRunner(create_app(self.state), access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        port = self._runner.addresses[0][1]
        self.url = f"http://{self._host}:{port}"
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=CONTROL_TIMEOUT_S))

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def control(self, **knobs: Any) -> dict[str, Any]:
        """``POST /control`` with ``knobs``, or ``GET /control`` when none are given; returns the snapshot."""
        assert self._session is not None, "FakeCloud is not started"
        if knobs:
            async with self._session.post(f"{self.url}/control", json=knobs) as response:
                body = await response.json()
                if response.status != 200:
                    raise ValueError(body["error"])
                return body
        async with self._session.get(f"{self.url}/control") as response:
            return await response.json()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.stop()
