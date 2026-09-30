"""Integration-tier fixtures: a fake cloud on loopback with a manual clock and a recording sleep."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import pytest

from tests.fakeserver.clock import ManualClock, RecordingSleep
from tests.fakeserver.server import FakeCloud
from tests.fakeserver.state import FakeState
from tests.integration._fakeserver_client import START_S, RawClient, bounded
from tests.integration._helpers import facade

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from open_mammotion import OpenMammotion


@pytest.fixture
def fake_clock() -> ManualClock:
    return ManualClock(START_S)


@pytest.fixture
def fake_sleep() -> RecordingSleep:
    return RecordingSleep()


@pytest.fixture
async def fake_cloud(fake_clock: ManualClock, fake_sleep: RecordingSleep) -> AsyncIterator[FakeCloud]:
    cloud = FakeCloud(FakeState(clock=fake_clock, sleep=fake_sleep))
    await bounded(cloud.start())
    try:
        yield cloud
    finally:
        await bounded(cloud.stop())


@pytest.fixture
async def raw_http() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def anon_client(fake_cloud: FakeCloud, raw_http: aiohttp.ClientSession) -> RawClient:
    """A raw client holding no token."""
    return RawClient(fake_cloud, raw_http)


@pytest.fixture
async def raw_client(anon_client: RawClient) -> RawClient:
    """A raw client that has already completed one client-credentials grant."""
    await anon_client.login()
    return anon_client


@pytest.fixture
async def api(fake_cloud: FakeCloud, fake_clock: ManualClock) -> AsyncIterator[OpenMammotion]:
    """The real facade against the fake cloud, owning its own HTTP session; closed after the test."""
    client = facade(fake_cloud, clock=fake_clock)
    try:
        yield client
    finally:
        await bounded(client.close())
