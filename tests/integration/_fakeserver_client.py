"""A raw-HTTP client for pinning the fake cloud's own contract; every wait is bounded (testing.md §4)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import orjson

from tests.fakeserver.state import FAKE_CLIENT_ID, FAKE_CLIENT_SECRET

if TYPE_CHECKING:
    from collections.abc import Awaitable

    import aiohttp

    from tests.fakeserver.server import FakeCloud

TIMEOUT_S = 5
START_S = 1_800_000_000.0
ENVELOPE_KEYS = {"code", "msg", "data", "requestId"}
TITLED_ENVELOPE_KEYS = ENVELOPE_KEYS | {"msgTitle"}


async def bounded[T](awaitable: Awaitable[T]) -> T:
    return await asyncio.wait_for(awaitable, timeout=TIMEOUT_S)


class RawClient:
    """Form grants and bearer JSON calls against a :class:`FakeCloud`, bypassing the library under test."""

    def __init__(self, cloud: FakeCloud, http: aiohttp.ClientSession) -> None:
        self.cloud = cloud
        self.http = http
        self.access_token = ""

    @property
    def state(self) -> Any:
        return self.cloud.state

    async def control(self, **knobs: Any) -> dict[str, Any]:
        return await bounded(self.cloud.control(**knobs))

    async def grant(self, **form: str) -> dict[str, Any]:
        body = {"client_id": FAKE_CLIENT_ID, "client_secret": FAKE_CLIENT_SECRET, "grant_type": "client_credentials"}
        body.update(form)

        async def go() -> dict[str, Any]:
            async with self.http.post(f"{self.cloud.url}/oauth2/token", data=body) as response:
                assert response.status == 200
                return await response.json()

        return await bounded(go())

    async def login(self) -> dict[str, Any]:
        grant = await self.grant()
        self.access_token = grant["data"]["access_token"]
        return grant["data"]

    async def raw(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """``(status, content_type, text)``; ``token=""`` sends no Authorization header."""
        sent = {"Accept-Language": "en-US", **(headers or {})}
        if bearer := self.access_token if token is None else token:
            sent["Authorization"] = f"Bearer {bearer}"

        async def go() -> tuple[int, str, str]:
            async with self.http.request(method, f"{self.cloud.url}{path}", json=json, headers=sent) as response:
                return response.status, response.content_type, await response.text()

        return await bounded(go())

    async def call(self, method: str, path: str, *, json: Any = None, token: str | None = None) -> dict[str, Any]:
        """The decoded envelope of an HTTP 200 response."""
        status, _, text = await self.raw(method, path, json=json, token=token)
        assert status == 200, text
        return orjson.loads(text)

    async def data(self, method: str, path: str, *, json: Any = None) -> Any:
        """``data`` of a success envelope."""
        body = await self.call(method, path, json=json)
        assert body["code"] == 200, body
        return body["data"]
