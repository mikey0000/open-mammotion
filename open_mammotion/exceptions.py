"""The exception hierarchy; nothing else in the package defines an exception type.

See ``docs/architecture.md`` §2.3 for which observation raises which type and what a
caller should do about it. Messages describe the condition; structured fields carry the
detail. No exception ever holds a token or a secret.
"""

from __future__ import annotations


class OpenMammotionError(Exception):
    """Base class for every error raised by this library."""


class TransportError(OpenMammotionError):
    """The request could not be completed: network, timeout, 408/429/5xx or a non-JSON body.

    Transient by definition. Raising it never changes credential state.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ContractError(OpenMammotionError):
    """The response did not match the specification the models were written from."""

    def __init__(self, model: str, detail: str) -> None:
        super().__init__(f"{model}: {detail}")
        self.model = model
        self.detail = detail


class AuthError(OpenMammotionError):
    """Base class for credential and token failures."""


class UnauthorizedError(AuthError):
    """The API answered 401 even after the single reactive token refresh (D9)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"{path} rejected the access token after one refresh")
        self.path = path


class GrantRejectedError(AuthError):
    """The token endpoint rejected a grant with a non-success envelope."""

    def __init__(self, grant_type: str, code: int, msg: str) -> None:
        super().__init__(f"{grant_type} grant rejected (code={code}): {msg}")
        self.grant_type = grant_type
        self.code = code
        self.msg = msg


class CredentialsRejectedError(AuthError):
    """The client id/secret was rejected. Terminal: every later call fails fast without I/O."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"client credentials rejected: {reason}")
        self.reason = reason


class ApiError(OpenMammotionError):
    """The API returned an envelope whose ``code`` is not a success code."""

    def __init__(self, code: int, msg: str, *, request_id: str | None = None, path: str | None = None) -> None:
        super().__init__(f"{path or 'request'} failed (code={code}): {msg}")
        self.code = code
        self.msg = msg
        self.request_id = request_id
        self.path = path


class CommandRejectedError(ApiError):
    """A successfully delivered command was refused by the mower (``commandResult: false``).

    ``code`` is the envelope's code, a success value: the delivery succeeded and the mower
    refused. ``message`` is the mower's ``resultMessage``.
    """

    def __init__(self, message: str, *, code: int, request_id: str | None = None, path: str | None = None) -> None:
        super().__init__(code, message, request_id=request_id, path=path)
        self.message = message
