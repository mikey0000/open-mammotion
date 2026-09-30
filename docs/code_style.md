# Code style

Ruff and ty enforce most of this (`pyproject.toml`); the rest is convention
and gets caught in review. Where this document and a linter disagree, fix the
linter configuration, not the code.

## Language and tooling

- Python 3.13 or newer. Use the modern syntax that implies: `type X = ...`
  aliases, PEP 695 generics, `match`, `Self`, `override`.
- `uv` manages the environment. `uv run ruff check --fix .`,
  `uv run ruff format .`, `uv run ty check open_mammotion/`, `uv run pytest`.
- Line length is 120. Ruff `select = ["ALL"]` with a short, justified ignore
  list; every ignore has a comment saying why.

## Structure

- **One concern per module.** A module's docstring says what it owns in one
  sentence. If you cannot write that sentence, split the module.
- **Top-level imports only.** No imports inside functions. Circular-import
  pressure is solved with a `TYPE_CHECKING` block for type-only names, or by
  moving the code to the right layer.
- **Layers import downward only** (see `architecture.md` §1). `api/` never
  imports `transport/aiohttp_session.py`; `transport/` never imports
  `auth/token_manager.py`.
- **Protocols over base classes** for anything a test replaces: `HttpSession`,
  `Requester`, `TokenProvider` are `typing.Protocol`s. Inheritance is for
  shared implementation (`ApiGroup`), not for polymorphism.
- **Public names are curated.** Each package `__init__.py` re-exports what the
  layer above needs and nothing else. `open_mammotion/__init__.py::__all__` is
  the supported surface.

## Typing

- Everything is annotated, including tests. `ty` runs clean on the package.
- No `Any` in a public signature. Raw JSON is `Mapping[str, object]` or
  `JsonValue`; `Any` is confined to the decode boundary in `models/`.
- Prefer `X | None` to `Optional[X]`, `list[X]` to `List[X]`, `Mapping` for
  read-only parameters, concrete types for return values.
- Enums for closed sets the specification enumerates. Wire enums subclass
  `TolerantIntEnum` or `TolerantStrEnum` (`models/common.py`) so an unknown
  value decodes to `UNKNOWN` instead of raising.

## Async

- Every I/O method is `async def`. Nothing blocks the loop.
- `asyncio.Lock` guards shared mutable state that spans an `await`; re-check
  the condition after acquiring the lock.
- Bound every external wait with a timeout taken from `const.py`; never a
  literal at the call site.
- No `asyncio.create_task` fire-and-forget inside the library. Tasks are owned
  and cancelled in `close()`.

## Naming

- Modules and functions are `snake_case`; classes are `CapWords`; constants are
  `UPPER_SNAKE`. Wire names (`deviceId`) appear only as `Alias(...)` strings
  in models; Python attributes are always `snake_case` (`device_id`).
- Endpoint methods are verbs named for what the caller wants, not the HTTP
  verb: `devices.list()`, `devices.get(device_id)`, `actions.start(...)`,
  `work_reports.search(...)`. The path lives in the method body.
- Exceptions end in `Error`. Protocols are named for the role
  (`Requester`, `TokenProvider`), not `IFoo` or `FooProtocol`.
- Booleans read as predicates: `is_fresh`, `has_more`, `ok`.
- Private is one underscore. Do not reach into another module's `_private`
  names; surface a public property.

## Models

- `@dataclass(frozen=True)` subclassing `WireModel`. Models are values;
  nothing mutates them after decode. (`slots=True` is avoided: mashumaro
  compiles decoders on the pre-slots class.)
- Wire aliases via `Annotated[T, Alias("camelName")]`; `WireModel` turns
  `serialize_by_alias` and `omit_none` on so `to_dict()` is what the server
  accepts. `1`/`0` booleans are declared `online: bool = int_bool()`
  (`int_bool(required=True)` for a field a caller must state). A required
  `str` field refuses `null` (D19).
- Every optional wire field has a default. A field the specification marks
  `required` has no default; a missing one raises `ContractError`.
- Timestamps: the API sends 13-digit milliseconds. Store them as `int`
  milliseconds with the suffix `_ms` (seconds as `_s`); expose `datetime`
  through a property built on `models/common.py::utc_from_ms` / `utc_from_s`,
  never by decoding to `datetime` in the model.
- Model modules import their field types for real (mashumaro resolves
  annotations at class creation); ruff knows this through
  `runtime-evaluated-base-classes`, so no `noqa: TC00x` is needed. Types used
  only in property return annotations still go in a `TYPE_CHECKING` block.
- Money-like floats (`work_area`, `carbon_reduction`) stay `float`; do not
  round in the model.
- Redact in `__repr__` anything the constitution calls a secret.

## Errors

- Raise the exceptions in `exceptions.py`; never `raise Exception` or a bare
  `ValueError` for an API condition.
- Exception messages describe the condition, not the fix, and never include
  a secret or a full response body. Attach structured fields (`code`, `msg`,
  `request_id`, `status`) as attributes.
- Do not `try/except` an exception a preceding guard already rules out.
- Do not swallow. Log-and-continue is allowed only in a `close()` path and
  in the one case D16 names (a host's `on_token_updated` callback).

## Logging

- One module logger: `_LOGGER = logging.getLogger(__name__)`.
- DEBUG for request/response outlines (method, path, status, `request_id`),
  INFO for token rotation (fingerprint only), WARNING for a rejected refresh
  and for an unknown enum value (once per value, D10), ERROR never (the
  exception carries it).
- Use `%s` formatting, not f-strings, in log calls.

## Comments and docstrings

- Default to no comment. Write one when a competent reader could not infer
  the constraint from the code: a server quirk, a spec ambiguity, a workaround.
- One or two lines. Longer explanations belong in `docs/`, linked by decision
  number (`# D7: client credentials may be re-granted once`).
- Never a comment that restates the next line, never a comment that explains
  what the code used to be, never a section divider.
- Every public module, class and method has a docstring: one summary line,
  then only what the signature does not say (units, spec gaps, raised
  exceptions). Google style sections (`Args:`, `Raises:`) when there is more
  than one thing to say.

## Small things

- Walrus (`:=`) where it removes a line without hiding the binding.
- `pathlib`, `orjson`, f-strings, `Self`.
- No magic numbers at a call site: name it in `const.py` or the module.
- No dead code, no commented-out code, no `TODO` without a backlog entry.
