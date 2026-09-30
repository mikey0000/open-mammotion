"""``create_app(state)``: the fake Mammotion cloud — token host and ``api-open`` host on one aiohttp app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from tests.fakeserver._common import make_middlewares
from tests.fakeserver.routes import actions, auth, control, devices, faults, local_network, work_reports

if TYPE_CHECKING:
    from tests.fakeserver.state import FakeState

_ROUTE_GROUPS = (auth, devices, actions, work_reports, faults, local_network, control)


def create_app(state: FakeState) -> web.Application:
    """An application serving every route in ``docs/openapi/`` plus ``/control``, all backed by ``state``."""
    app = web.Application(middlewares=make_middlewares(state))
    for group in _ROUTE_GROUPS:
        group.register(app, state)
    return app
