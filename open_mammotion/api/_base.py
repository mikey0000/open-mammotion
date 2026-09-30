"""``ApiGroup``: the typed request helpers every specification tag builds on.

The only place raw envelope ``data`` becomes a model. A group method is the path, the
payload and one of these helpers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from mashumaro.exceptions import InvalidFieldValue, MissingField, UnserializableDataError

from open_mammotion.exceptions import ContractError
from open_mammotion.models.common import describe_decode_error

if TYPE_CHECKING:
    from open_mammotion.models.common import Envelope, JsonObject, WireModel
    from open_mammotion.transport.requester import Requester

_LOGGER = logging.getLogger(__name__)

_DOT_SEGMENTS = frozenset({".", ".."})
_DECODE_ERRORS = (MissingField, InvalidFieldValue, UnserializableDataError, TypeError, ValueError)


class ApiGroup:
    """One specification tag; subclasses add exactly one public method per endpoint."""

    def __init__(self, requester: Requester) -> None:
        self._requester = requester

    @staticmethod
    def _require(value: str, name: str) -> str:
        """Refuse an identifier that cannot address a resource, before any I/O.

        ``.`` and ``..`` survive percent-encoding and are then normalised away by the URL
        layer, so they would silently address a different endpoint.
        """
        if not value or value in _DOT_SEGMENTS:
            raise ValueError(f"{name} must be a non-empty string and not a dot segment")
        return value

    @classmethod
    def _mower_path(cls, device_id: str, *segments: str) -> str:
        """``/v1/mower/{deviceId}`` plus any further segments, each URL-encoded."""
        parts = [cls._require(device_id, "device_id"), *segments]
        return "/v1/mower/" + "/".join(quote(part, safe="") for part in parts)

    async def _request(self, method: str, path: str, *, json: JsonObject | None = None) -> Envelope:
        return await self._requester.request(method, path, json=json)

    async def _get[M: WireModel](self, path: str, model: type[M]) -> M:
        envelope = await self._request("GET", path)
        return self._decode(model, envelope.data, path=path)

    async def _get_list[M: WireModel](self, path: str, model: type[M]) -> list[M]:
        envelope = await self._request("GET", path)
        return self._decode_list(model, envelope.data, path=path)

    async def _post[M: WireModel](self, path: str, payload: JsonObject, model: type[M]) -> M:
        envelope = await self._request("POST", path, json=payload)
        return self._decode(model, envelope.data, path=path)

    async def _post_list[M: WireModel](self, path: str, payload: JsonObject, model: type[M]) -> list[M]:
        envelope = await self._request("POST", path, json=payload)
        return self._decode_list(model, envelope.data, path=path)

    @staticmethod
    def _decode[M: WireModel](model: type[M], data: object, *, path: str) -> M:
        """Decode one object; a shape mismatch is a contract violation, not a crash."""
        if not isinstance(data, dict):
            raise ContractError(model.__name__, f"{path}: expected an object in data, got {type(data).__name__}")
        try:
            return model.from_dict(data)
        except _DECODE_ERRORS as exc:
            raise ContractError(model.__name__, f"{path}: {describe_decode_error(exc)}") from None

    @classmethod
    def _decode_list[M: WireModel](cls, model: type[M], data: object, *, path: str) -> list[M]:
        if data is None:
            return []
        if not isinstance(data, list):
            raise ContractError(model.__name__, f"{path}: expected a list in data, got {type(data).__name__}")
        return [cls._decode(model, item, path=path) for item in data]
