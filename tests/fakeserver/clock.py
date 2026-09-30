"""Controllable stand-ins for :attr:`FakeState.clock` and :attr:`FakeState.sleep`, so tests never wait on real time."""

from __future__ import annotations


class ManualClock:
    """A clock that only moves when a test sets or advances :attr:`now` (seconds)."""

    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSleep:
    """An async ``sleep`` that returns at once and records each requested delay (``delay_ms`` knob)."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
