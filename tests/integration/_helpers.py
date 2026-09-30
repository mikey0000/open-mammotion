"""Builders for the facade tests: an ``OpenMammotion`` pointed at the fake cloud, and server-side log readers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from open_mammotion import OpenMammotion
from open_mammotion.const import DEFAULT_TOKEN_TTL_S, TOKEN_PATH, TOKEN_REFRESH_LEAD_S
from tests._helpers import CREDENTIALS, SECRET_VALUES
from tests.integration._fakeserver_client import TIMEOUT_S

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.fakeserver.server import FakeCloud
    from tests.fakeserver.state import RecordedRequest

MOWERS = ("GET", "/v1/mowers")
TOKEN = ("POST", TOKEN_PATH)
TOKEN_TTL_S = int(DEFAULT_TOKEN_TTL_S)
#: Seconds after a grant at which the token first falls inside the refresh lead window.
INTO_LEAD_WINDOW_S = TOKEN_TTL_S - TOKEN_REFRESH_LEAD_S + 1


def facade(fake_cloud: FakeCloud, *, clock: Callable[[], float], **kwargs: Any) -> OpenMammotion:
    """An ``OpenMammotion`` whose API and token hosts are the fake, on the fake's clock.

    Pass ``session=`` to lend it an ``aiohttp.ClientSession``; without one it creates and owns its own.
    """
    kwargs.setdefault("timeout_s", TIMEOUT_S)
    return OpenMammotion(CREDENTIALS, api_url=fake_cloud.url, auth_url=fake_cloud.url, clock=clock, **kwargs)


def requests_since(fake_cloud: FakeCloud, start: int) -> list[tuple[str, str]]:
    """``(method, path)`` of every request the fake recorded from index ``start`` on."""
    return [(r.method, r.path) for r in fake_cloud.state.requests[start:]]


def grant_types(fake_cloud: FakeCloud, start: int = 0) -> list[str]:
    """The ``grant_type`` of every token request the fake received from index ``start`` on, accepted or not."""
    return [r.body["grant_type"] for r in _token_requests(fake_cloud.state.requests[start:])]


def _token_requests(requests: list[RecordedRequest]) -> list[RecordedRequest]:
    return [r for r in requests if r.path == TOKEN_PATH]


def secrets_in_text(text: str, fake_cloud: FakeCloud) -> list[str]:
    """Which fixture secrets, or which tokens the fake has ever issued, appear in ``text``."""
    issued = [value for access, record in fake_cloud.state.tokens.items() for value in (access, record.refresh_token)]
    return [value for value in (*SECRET_VALUES, *issued) if value in text]
