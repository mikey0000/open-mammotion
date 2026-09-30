"""The response envelope, the success rule, and the tolerant enum bases every wire model uses."""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
import logging
from typing import Annotated, Any, Self, get_args, get_origin, get_type_hints

from mashumaro.config import BaseConfig
from mashumaro.exceptions import InvalidFieldValue, MissingField
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias, SerializationStrategy

_LOGGER = logging.getLogger(__name__)

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

#: Envelope ``code`` values that mean success. Both appear in Mammotion's own examples (D8, Q1).
SUCCESS_CODES: frozenset[int] = frozenset({0, 200})

_UNKNOWN_SEEN: set[tuple[str, object]] = set()


def _note_unknown(enum_name: str, value: object) -> None:
    key = (enum_name, value)
    if key not in _UNKNOWN_SEEN:
        _UNKNOWN_SEEN.add(key)
        _LOGGER.warning("Unknown %s value %r from the API; decoding as UNKNOWN", enum_name, value)


class TolerantIntEnum(IntEnum):
    """Integer wire enum that decodes an unlisted value to ``UNKNOWN`` and logs it once (D10).

    Every subclass must define an ``UNKNOWN`` member; the base cannot, because an enum
    with members cannot be subclassed.
    """

    @classmethod
    def _missing_(cls, value: object) -> Self:
        _note_unknown(cls.__name__, value)
        return cls["UNKNOWN"]


class TolerantStrEnum(StrEnum):
    """String wire enum: case-insensitive match, else ``UNKNOWN`` logged once (D10).

    Case-insensitivity exists because the specification's own example spells one
    ``status`` value two ways (``Standby`` / ``StandBy``).
    """

    @classmethod
    def _missing_(cls, value: object) -> Self:
        if isinstance(value, str):
            folded = value.casefold()
            for member in cls:
                if member.value.casefold() == folded:
                    return member
        _note_unknown(cls.__name__, value)
        return cls["UNKNOWN"]


class IntBool(SerializationStrategy):
    """A ``bool`` the API spells as ``1``/``0`` (``online``, ``chargeStatus``, ``enabled``).

    Attach with :func:`int_bool`; mashumaro only honours a strategy given through field
    metadata, not through ``Annotated``. Decoding also accepts ``true``/``false`` and the
    strings ``"1"``/``"0"``; encoding always emits the integer.
    """

    def serialize(self, value: bool) -> int:  # noqa: FBT001 — the wire value is a bool by definition
        """Encode as ``1`` or ``0``."""
        return int(value)

    def deserialize(self, value: object) -> bool:
        """Decode ``1``/``0``, ``"1"``/``"0"``, ``"true"``/``"false"`` (any case) or a JSON boolean.

        Raises:
            ValueError: Anything else, ``null`` included; a boolean the API did not send is not a boolean.

        """
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and (folded := value.strip().casefold()) in _INT_BOOL_STRINGS:
            return _INT_BOOL_STRINGS[folded]
        raise ValueError(f"not a 1/0 boolean: {type(value).__name__}")


_INT_BOOL_STRINGS = {"1": True, "0": False, "true": True, "false": False}
_INT_BOOL = IntBool()


def int_bool(*, default: bool = False, required: bool = False) -> bool:
    """Declare a boolean field the API spells as ``1``/``0``.

    Usage: ``online: bool = int_bool()``. With ``required=True`` the field has no default,
    so a missing value is a :class:`ContractError` at the API layer and a caller building
    a request model must state it.
    """
    metadata = {"serialization_strategy": _INT_BOOL}
    if required:
        return field(metadata=metadata)
    return field(default=default, metadata=metadata)


_MS_PER_S = 1000
_US_PER_MS = 1000


def utc_from_ms(ms: int) -> datetime:
    """The UTC instant of a 13-digit millisecond timestamp, exact to the millisecond (D14)."""
    return datetime.fromtimestamp(ms // _MS_PER_S, tz=UTC).replace(microsecond=(ms % _MS_PER_S) * _US_PER_MS)


def utc_from_s(s: int) -> datetime:
    """The UTC instant of a Unix-seconds timestamp."""
    return datetime.fromtimestamp(s, tz=UTC)


def describe_decode_error(exc: Exception) -> str:
    """Name the failing field without echoing its value; a response body never enters a message."""
    if isinstance(exc, MissingField):
        return f'field "{exc.field_name}" is missing'
    if isinstance(exc, InvalidFieldValue):
        return f'field "{exc.field_name}" has an invalid value'
    return type(exc).__name__


class WireModel(DataClassORJSONMixin):
    """Base for every model that crosses the wire.

    Serialises by alias so ``to_dict()`` is what the server accepts; ignores unknown
    keys so a new server field is never a crash (D10). A required ``str`` field refuses
    ``null`` and non-strings, which mashumaro would otherwise coerce with ``str()`` (D19).
    Subclasses are ``@dataclass(frozen=True)``.
    """

    class Config(BaseConfig):
        serialize_by_alias = True
        omit_none = True

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        for alias, name in _required_str_fields(cls):
            if alias in d and not isinstance(d[alias], str):
                raise InvalidFieldValue(name, str, d[alias], cls)
        return d


_REQUIRED_STR_FIELDS: dict[type[WireModel], tuple[tuple[str, str], ...]] = {}


def _required_str_fields(cls: type[WireModel]) -> tuple[tuple[str, str], ...]:
    """``(alias, python_name)`` for every required ``str`` field of ``cls``, computed once."""
    if (cached := _REQUIRED_STR_FIELDS.get(cls)) is not None:
        return cached
    hints = get_type_hints(cls, include_extras=True)
    found: list[tuple[str, str]] = []
    for f in fields(cls):  # ty: ignore[invalid-argument-type] — every WireModel subclass is a dataclass
        if f.default is not MISSING or f.default_factory is not MISSING:
            continue
        hint = hints[f.name]
        metadata = get_args(hint)[1:] if get_origin(hint) is Annotated else ()
        base = get_args(hint)[0] if get_origin(hint) is Annotated else hint
        if base is str:
            alias = next((m.name for m in metadata if isinstance(m, Alias)), f.name)
            found.append((alias, f.name))
    _REQUIRED_STR_FIELDS[cls] = tuple(found)
    return _REQUIRED_STR_FIELDS[cls]


@dataclass(frozen=True)
class Envelope(WireModel):
    """``{code, msg, msgTitle?, data, requestId?}`` — the shape of every API response.

    ``data`` stays raw JSON here; ``api/_base.py`` decodes it into the endpoint's model.
    ``requestId`` is documented as a string but one example shows a bare integer, so it
    is coerced (Q10).
    """

    code: int
    msg: str = ""
    msg_title: Annotated[str | None, Alias("msgTitle")] = None
    data: Any = None
    request_id: Annotated[str | None, Alias("requestId")] = None

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        if (request_id := d.get("requestId")) is not None and not isinstance(request_id, str):
            d = {**d, "requestId": str(request_id)}
        return super().__pre_deserialize__(d)

    @property
    def ok(self) -> bool:
        """Whether ``code`` is one of the success codes."""
        return self.code in SUCCESS_CODES
