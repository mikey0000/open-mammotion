"""The ``Requester`` seam between the API groups and the transport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from open_mammotion.models.common import Envelope, JsonObject


class Requester(Protocol):
    """Performs an authenticated API call and returns the decoded envelope.

    The implementation (``transport/api.py``) owns authentication headers, the single
    401 retry, status-to-exception mapping and the envelope success check. A returned
    ``Envelope`` is therefore always a success; its ``data`` is raw JSON.
    """

    async def request(self, method: str, path: str, *, json: JsonObject | None = None) -> Envelope:
        """Call ``path`` (relative to the API base URL) and return its envelope.

        Raises:
            TransportError: The call could not complete or the server was unavailable.
            UnauthorizedError: 401 after the one reactive refresh.
            CredentialsRejectedError: The credential is terminally rejected.
            ApiError: The envelope ``code`` is not a success code.
            ContractError: The body was JSON but not an envelope.

        """
        ...
