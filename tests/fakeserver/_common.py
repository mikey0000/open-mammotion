"""Envelope builders, request-body validation, JSON helpers and the middlewares every route shares.

Assumptions the specification does not settle (candidates for ``docs/open_questions.md``):

- A missing or ill-typed required body field answers HTTP 200 with envelope
  ``{code: 400, msg: "<field> is required" | "<field> is invalid"}``.
- An unknown ``deviceId`` / ``deviceName`` answers HTTP 200 with envelope ``{code: 404, msg: "device not found"}``.
- A missing, unknown or expired Bearer token answers HTTP 401 with envelope ``{code: 401, msg: "Unauthorized"}``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import TYPE_CHECKING, Any

from aiohttp import web
import orjson

from tests.fakeserver.state import TokenRecord

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from tests.fakeserver.state import FakeState

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

TOKEN_KEY: web.RequestKey[TokenRecord] = web.RequestKey("fake_token", TokenRecord)
API_PREFIX = "/v1/"
CONTROL_PATH = "/control"
TOKEN_PATH = "/oauth2/token"

MSG_TITLE_OK = "Operation Successful"
_NON_JSON_BODY = "<html><head><title>{status}</title></head><body><h1>{status} {reason}</h1></body></html>"


def fingerprint(secret: str) -> str:
    """A short, non-reversible label for a token or secret, safe to record and print."""
    return "fp:" + hashlib.sha256(secret.encode()).hexdigest()[:10]


def success_msg(code: int) -> str:
    """The ``msg`` the spec pairs with each success code: portal prose uses 0, OpenAPI examples use 200 (Q1)."""
    return "Request success" if code == 0 else "Success"


def json_response(body: Any, *, status: int = 200) -> web.Response:
    """A JSON response serialised with orjson."""
    return web.Response(status=status, body=orjson.dumps(body), content_type="application/json")


def ok(state: FakeState, data: Any, *, msg_title: str | None = None) -> web.Response:
    """A success envelope carrying ``data``, using the state's current success code."""
    body: dict[str, Any] = {"code": state.success_code, "msg": success_msg(state.success_code)}
    if msg_title is not None:
        body["msgTitle"] = msg_title
    body["data"] = data
    body["requestId"] = state.next_request_id()
    return json_response(body)


def fail(state: FakeState, code: int, msg: str, *, status: int = 200) -> web.Response:
    """An error envelope; the API reports most failures as HTTP 200 with a non-success ``code``."""
    return json_response({"code": code, "msg": msg, "data": None, "requestId": state.next_request_id()}, status=status)


def not_found(state: FakeState, what: str = "device") -> web.Response:
    return fail(state, 404, f"{what} not found")


class BodyError(Exception):
    """A request body that fails validation; carries the envelope message."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


def _type_ok(value: object, expected: type) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, expected)


@dataclass(frozen=True)
class Field:
    """One property of a request schema: its wire name, JSON type and whether it is required."""

    name: str
    kind: type
    required: bool = False


def validate(body: object, fields: tuple[Field, ...], *, prefix: str = "") -> dict[str, Any]:
    """Check ``body`` against ``fields``: required presence and JSON type; unknown keys are ignored.

    ``null`` is treated as absent, matching how most JSON servers bind optional properties.
    """
    if not isinstance(body, dict):
        raise BodyError(f"{prefix or 'body'} is invalid")
    for f in fields:
        value = body.get(f.name)
        if value is None:
            if f.required:
                raise BodyError(f"{prefix}{f.name} is required")
            continue
        if not _type_ok(value, f.kind):
            raise BodyError(f"{prefix}{f.name} is invalid")
        if f.required and f.kind is str and not value:
            raise BodyError(f"{prefix}{f.name} is required")
    return body


async def read_json(request: web.Request) -> object:
    """The request body as JSON, or :class:`BodyError` when it is not JSON."""
    raw = await request.read()
    try:
        return orjson.loads(raw) if raw else None
    except orjson.JSONDecodeError as exc:
        raise BodyError("request body is not valid JSON") from exc


def page_params(body: Mapping[str, Any]) -> tuple[int, int]:
    """``(pageNumber, pageSize)`` with the spec's defaults (1, 10); non-positive values are rejected."""
    number = 1 if (raw_number := body.get("pageNumber")) is None else raw_number
    size = 10 if (raw_size := body.get("pageSize")) is None else raw_size
    if number < 1:
        raise BodyError("pageNumber is invalid")
    if size < 1:
        raise BodyError("pageSize is invalid")
    return number, size


def current_token(request: web.Request) -> TokenRecord:
    """The token record the auth middleware attached to this request."""
    return request[TOKEN_KEY]


def _redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            scheme, _, token = value.partition(" ")
            out[key] = f"{scheme} {fingerprint(token)}" if token else fingerprint(value)
        else:
            out[key] = value
    return out


_SECRET_FORM_FIELDS = frozenset({"client_secret", "refresh_token"})


async def _recorded_body(request: web.Request) -> object:
    raw = await request.read()
    if not raw:
        return None
    if request.content_type == "application/x-www-form-urlencoded":
        form = await request.post()
        return {k: fingerprint(str(v)) if k in _SECRET_FORM_FIELDS else str(v) for k, v in form.items()}
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        return raw.decode(errors="replace")


def _injected_failure(status: int, *, non_json: bool) -> web.Response:
    phrase = _REASONS.get(status, "Error")
    if non_json:
        return web.Response(
            status=status, text=_NON_JSON_BODY.format(status=status, reason=phrase), content_type="text/html"
        )
    return json_response({"code": status, "msg": phrase}, status=status)


_REASONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    408: "Request Timeout",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def _bearer(request: web.Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def make_middlewares(state: FakeState) -> list[Callable[[web.Request, Handler], Awaitable[web.StreamResponse]]]:
    """Recording, delay, fault injection and Bearer auth, applied in that order to every non-control route."""

    @web.middleware
    async def record(request: web.Request, handler: Handler) -> web.StreamResponse:
        if request.path == CONTROL_PATH:
            return await handler(request)
        state.record_request(
            method=request.method,
            path=request.path,
            headers=_redact_headers(request.headers),
            body=await _recorded_body(request),
        )
        return await handler(request)

    @web.middleware
    async def delay(request: web.Request, handler: Handler) -> web.StreamResponse:
        if request.path != CONTROL_PATH and state.delay_ms > 0:
            await state.sleep(state.delay_ms / 1000)
        return await handler(request)

    @web.middleware
    async def inject(request: web.Request, handler: Handler) -> web.StreamResponse:
        if request.path.startswith(API_PREFIX):
            if (fault := state.take_api_fault()) is not None:
                return _injected_failure(fault.status, non_json=fault.non_json)
        elif request.path == TOKEN_PATH and (fault := state.take_token_fault()) is not None:
            return _injected_failure(fault.status, non_json=fault.non_json)
        return await handler(request)

    @web.middleware
    async def auth(request: web.Request, handler: Handler) -> web.StreamResponse:
        if not request.path.startswith(API_PREFIX):
            return await handler(request)
        token = _bearer(request)
        record_ = state.tokens.get(token) if token is not None else None
        if record_ is None or state.clock() >= record_.expires_at:
            return fail(state, 401, "Unauthorized", status=401)
        request[TOKEN_KEY] = record_
        if (forced := state.take_envelope_fault()) is not None:
            return fail(state, forced.code, forced.msg)
        return await handler(request)

    return [record, delay, inject, auth]
