"""``POST /oauth2/token``: the client-credentials and refresh-token grants.

Assumptions (the specification documents only the success shape):

- Failures answer HTTP 200 with a non-success envelope, portal style: ``40101 "invalid client"`` for a wrong
  id/secret or a rejected client-credentials grant, ``40102 "Refresh token has expired"`` for an unknown,
  used or rejected refresh token, ``400 "<field> is required"`` / ``400 "grant_type is invalid"`` otherwise.
- The refresh grant rotates: the presented refresh token is invalidated and a new pair is issued. The old
  access token stays valid until it expires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.fakeserver._common import TOKEN_PATH, json_response

if TYPE_CHECKING:
    from aiohttp import web

    from tests.fakeserver.state import FakeState

INVALID_CLIENT = 40101
REFRESH_EXPIRED = 40102
_GRANTS = frozenset({"client_credentials", "refresh_token"})


def _envelope(code: int, msg: str, data: Any = None) -> web.Response:
    return json_response({"code": code, "msg": msg, "data": data})


def register(app: web.Application, state: FakeState) -> None:
    def granted(client_id: str, kind: str) -> web.Response:
        access, record = state.issue_token(client_id)
        state.token_grants[kind] += 1
        return _envelope(
            state.success_code,
            "Success",
            {
                "access_token": access,
                "refresh_token": record.refresh_token,
                "token_type": "Bearer",
                "expires_in": state.token_ttl_s,
            },
        )

    async def token(request: web.Request) -> web.Response:
        form = await request.post()
        values = {k: str(v) for k, v in form.items()}
        for name in ("client_id", "client_secret", "grant_type"):
            if not values.get(name):
                return _envelope(400, f"{name} is required")
        grant = values["grant_type"]
        if grant not in _GRANTS:
            return _envelope(400, "grant_type is invalid")
        if values["client_id"] != state.client_id or values["client_secret"] != state.client_secret:
            return _envelope(INVALID_CLIENT, "invalid client")

        if grant == "client_credentials":
            if state.reject_client_credentials:
                return _envelope(INVALID_CLIENT, "invalid client")
            return granted(values["client_id"], grant)

        if not (presented := values.get("refresh_token")):
            return _envelope(400, "refresh_token is required")
        owner = state.refresh_tokens.pop(presented, None)
        if state.reject_next_refresh:
            state.reject_next_refresh = False
            return _envelope(REFRESH_EXPIRED, "Refresh token has expired")
        if owner != values["client_id"]:
            return _envelope(REFRESH_EXPIRED, "Refresh token has expired")
        return granted(owner, grant)

    app.router.add_post(TOKEN_PATH, token)
