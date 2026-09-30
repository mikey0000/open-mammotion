"""Builders and fixture values shared across test tiers: envelopes, HTTP responses, secrets."""

from __future__ import annotations

import logging
from typing import Any

import orjson

from open_mammotion.auth.credentials import ClientCredentials
from open_mammotion.transport.session import HttpResponse

REQUEST_ID = "req-0001"
ACCESS_TOKEN = "access-token-1"
REFRESH_TOKEN = "refresh-token-1"
CREDENTIALS = ClientCredentials(client_id="cid-test", client_secret="not-a-real-secret")

#: Every fixture value that Constitution §6 says must never reach a log line or a repr.
SECRET_VALUES: tuple[str, ...] = (CREDENTIALS.client_secret, ACCESS_TOKEN, REFRESH_TOKEN)


def leaked_secrets(records: list[logging.LogRecord]) -> list[str]:
    """The fixture secrets that appear in any record's message or exception text."""
    texts = [r.getMessage() + (logging.Formatter().formatException(r.exc_info) if r.exc_info else "") for r in records]
    return [value for value in SECRET_VALUES if any(value in text for text in texts)]


def envelope(
    data: Any = None,
    *,
    code: int = 0,
    msg: str = "Request success",
    request_id: str | None = REQUEST_ID,
    msg_title: str | None = None,
) -> dict[str, Any]:
    """The API's response envelope as a plain dict."""
    body: dict[str, Any] = {"code": code, "msg": msg, "data": data}
    if request_id is not None:
        body["requestId"] = request_id
    if msg_title is not None:
        body["msgTitle"] = msg_title
    return body


def json_response(body: Any, *, status: int = 200) -> HttpResponse:
    """An ``HttpResponse`` carrying ``body`` as JSON."""
    return HttpResponse(status=status, headers={"Content-Type": "application/json"}, body=orjson.dumps(body))


def text_response(text: str, *, status: int = 200, content_type: str = "text/html") -> HttpResponse:
    """An ``HttpResponse`` with a non-JSON body."""
    return HttpResponse(status=status, headers={"Content-Type": content_type}, body=text.encode())


def token_grant_body(
    *,
    access_token: str = ACCESS_TOKEN,
    refresh_token: str | None = REFRESH_TOKEN,
    expires_in: int = 3600,
    code: int = 0,
) -> dict[str, Any]:
    """The token endpoint's envelope for a grant; a non-zero ``code`` makes it a rejection."""
    data: dict[str, Any] = {"access_token": access_token, "token_type": "Bearer", "expires_in": expires_in}
    if refresh_token is not None:
        data["refresh_token"] = refresh_token
    return envelope(data, code=code, msg="Success" if code == 0 else "invalid client", request_id=None)
