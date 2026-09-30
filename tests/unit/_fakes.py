"""Hand-written fakes for every seam the unit tier replaces (docs/testing.md §3, D13).

Each fake has the real protocol's interface, scripted outcomes and recorded calls.
``FakeHttpSession``, ``FakeRequester`` and ``FakeTokenClient`` also take an optional
``gate`` that holds every call open until set, and a ``wait_for_calls(n)`` that resolves
once ``n`` calls have arrived, so a test controls interleaving without sleeping.

Misuse of a fake (an unscripted call, a contract violation) raises ``FakeMisuseError``,
which derives from ``BaseException`` so that code under test mapping ``except Exception``
cannot swallow it into a passing result.
"""

from __future__ import annotations

import asyncio
from collections import deque
import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from open_mammotion.exceptions import CredentialsRejectedError
from open_mammotion.models.common import Envelope

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from open_mammotion.auth.credentials import ClientCredentials, TokenSet
    from open_mammotion.models.common import JsonObject
    from open_mammotion.transport.session import HttpResponse

__all__ = [
    "FakeHttpSession",
    "FakeMisuseError",
    "FakeRequester",
    "FakeTokenClient",
    "FakeTokenProvider",
    "RaisingClientSession",
    "RecordedCall",
    "RecordedRequest",
]

type Outcome[T] = T | BaseException


class FakeMisuseError(BaseException):
    """A test drove a fake outside its script; never catchable by the code under test."""


class _Arrivals:
    """Counts calls and lets any number of tests wait until ``n`` have arrived."""

    def __init__(self) -> None:
        self.count = 0
        self._waiters: list[asyncio.Event] = []

    def note(self) -> None:
        self.count += 1
        for waiter in self._waiters:
            waiter.set()
        self._waiters.clear()

    async def wait_for(self, n: int) -> None:
        while self.count < n:
            waiter = asyncio.Event()
            self._waiters.append(waiter)
            await waiter.wait()


async def _gated(gate: asyncio.Event | None) -> None:
    if gate is not None:
        await gate.wait()


def _pop[T](queue: deque[Outcome[T]], what: str) -> T:
    if not queue:
        raise FakeMisuseError(f"no outcome scripted for {what}")
    outcome = queue.popleft()
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    json: JsonObject | None
    form: Mapping[str, str] | None
    timeout_s: float | None

    @property
    def authorization(self) -> str | None:
        return next((v for k, v in self.headers.items() if k.lower() == "authorization"), None)

    @property
    def bearer(self) -> str | None:
        auth = self.authorization
        return auth.removeprefix("Bearer ") if auth and auth.startswith("Bearer ") else None


class FakeHttpSession:
    """Implements ``HttpSession``.

    Responses are consumed in order; an exception outcome is raised. A ``router``, when
    set, answers from the recorded request instead of the queue (for example by bearer
    token), which is what a concurrent test needs when arrival order is not fixed.
    """

    def __init__(self, *outcomes: Outcome[HttpResponse]) -> None:
        self.outcomes: deque[Outcome[HttpResponse]] = deque(outcomes)
        self.requests: list[RecordedRequest] = []
        self.gate: asyncio.Event | None = None
        self.router: Callable[[RecordedRequest], Outcome[HttpResponse]] | None = None
        self.closed = False
        self._arrivals = _Arrivals()

    def queue(self, *outcomes: Outcome[HttpResponse]) -> None:
        self.outcomes.extend(outcomes)

    async def wait_for_calls(self, n: int) -> None:
        """Resolve once ``n`` requests have been recorded (they may still be parked at the gate)."""
        await self._arrivals.wait_for(n)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: JsonObject | None = None,
        form: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse:
        if json is not None and form is not None:
            raise FakeMisuseError(f"{method} {url} sent both json and form; HttpSession allows one")
        recorded = RecordedRequest(
            method, url, dict(headers or {}), copy.deepcopy(json), dict(form) if form else None, timeout_s
        )
        self.requests.append(recorded)
        self._arrivals.note()
        await _gated(self.gate)
        if self.router is not None:
            outcome = self.router(recorded)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return _pop(self.outcomes, f"{method} {url}")

    async def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class RecordedCall:
    method: str
    path: str
    json: JsonObject | None


class FakeRequester:
    """Implements ``Requester``. Script outcomes per ``(method, path)`` or as an ordered queue.

    A route with a script is served only from that script; the ordered queue serves
    routes with no script of their own. A returned envelope must be a success, as the
    protocol promises; script a failure as an exception.
    """

    def __init__(self) -> None:
        self.by_route: dict[tuple[str, str], deque[Outcome[Envelope]]] = {}
        self.queued: deque[Outcome[Envelope]] = deque()
        self.calls: list[RecordedCall] = []
        self.gate: asyncio.Event | None = None
        self._arrivals = _Arrivals()

    def on(self, method: str, path: str, *outcomes: Outcome[Envelope] | Any) -> None:
        """Script outcomes for a route; a plain value is wrapped as a success envelope's ``data``."""
        self.by_route.setdefault((method, path), deque()).extend(self._wrap(o) for o in outcomes)

    def queue(self, *outcomes: Outcome[Envelope] | Any) -> None:
        self.queued.extend(self._wrap(o) for o in outcomes)

    async def wait_for_calls(self, n: int) -> None:
        await self._arrivals.wait_for(n)

    @staticmethod
    def _wrap(outcome: Any) -> Outcome[Envelope]:
        if isinstance(outcome, BaseException):
            return outcome
        if isinstance(outcome, Envelope):
            if not outcome.ok:
                raise FakeMisuseError("a Requester never returns a non-success envelope; script an ApiError")
            return outcome
        return Envelope(code=0, msg="Request success", data=outcome, request_id="req-fake")

    async def request(self, method: str, path: str, *, json: JsonObject | None = None) -> Envelope:
        self.calls.append(RecordedCall(method, path, copy.deepcopy(json)))
        self._arrivals.note()
        await _gated(self.gate)
        route = self.by_route.get((method, path))
        if route is not None:
            return _pop(route, f"{method} {path}")
        return _pop(self.queued, f"{method} {path} (no route script, queue empty)")


class FakeTokenProvider:
    """Implements ``TokenProvider`` with the held-token semantics of D9.

    ``get_access_token`` returns the current token every time. ``invalidate(stale)``
    advances to the next scripted token only when ``stale`` is the current one; otherwise
    it is recorded and ignored. The last token repeats once the script is exhausted.
    """

    def __init__(self, *tokens: str, rejected: str | None = None) -> None:
        self._upcoming: deque[str] = deque(tokens[1:] if tokens else ())
        self.current: str = tokens[0] if tokens else "access-token-1"
        self.rejected = rejected
        self.invalidated: list[str] = []
        self.get_calls = 0

    async def get_access_token(self) -> str:
        self.get_calls += 1
        if self.rejected is not None:
            raise CredentialsRejectedError(self.rejected)
        return self.current

    def invalidate(self, stale_token: str) -> None:
        self.invalidated.append(stale_token)
        if stale_token == self.current and self._upcoming:
            self.current = self._upcoming.popleft()


@dataclass
class FakeTokenClient:
    """Implements ``TokenGranter``. Each grant pops the next outcome from its own queue."""

    client_credentials: deque[Outcome[TokenSet]] = field(default_factory=deque)
    refresh: deque[Outcome[TokenSet]] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self.client_credentials = deque(self.client_credentials)
        self.refresh = deque(self.refresh)

    calls: list[str] = field(default_factory=list)
    seen_credentials: list[ClientCredentials] = field(default_factory=list)
    seen_refresh_tokens: list[str] = field(default_factory=list)
    gate: asyncio.Event | None = None
    _arrivals: _Arrivals = field(default_factory=_Arrivals, init=False, repr=False)

    async def wait_for_calls(self, n: int) -> None:
        await self._arrivals.wait_for(n)

    async def grant_client_credentials(self, credentials: ClientCredentials) -> TokenSet:
        self.calls.append("client_credentials")
        self.seen_credentials.append(credentials)
        self._arrivals.note()
        await _gated(self.gate)
        return _pop(self.client_credentials, "the client_credentials grant")

    async def grant_refresh_token(self, credentials: ClientCredentials, refresh_token: str) -> TokenSet:
        self.calls.append("refresh_token")
        self.seen_credentials.append(credentials)
        self.seen_refresh_tokens.append(refresh_token)
        self._arrivals.note()
        await _gated(self.gate)
        return _pop(self.refresh, "the refresh_token grant")


class RaisingClientSession:
    """Stands in for a borrowed ``aiohttp.ClientSession`` whose ``request`` fails before any I/O.

    Only ``AiohttpSession``'s error mapping and ownership rules need it; everything else
    about the adapter is covered by the integration tier.
    """

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: object) -> object:
        self.calls.append((method, url))
        raise self.error

    async def close(self) -> None:
        self.closed = True
