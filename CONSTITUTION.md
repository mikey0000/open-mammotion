# Constitution

These are the rules that do not bend. Everything else in `docs/` explains how
to apply them; this file says what they are. A change that breaks one of these
needs a new numbered entry in `docs/decisions.md` that supersedes the rule, not
a quiet exception.

## 1. Clean room

`open-mammotion` is written from the published Mammotion Open API alone:
`docs/openapi/*.json` (captured from developer.mammotion.com) and the pages
under `docs/api/`. No code, comments or tests are copied from `pymammotion`,
from the Mammotion app, or from any decompiled source. Where the specification
is silent, the gap is recorded in `docs/open_questions.md` and the code takes
the conservative reading, stated in a docstring.

## 2. The specification is the map

The package mirrors the API. Each tag in the specification is one module under
`open_mammotion/api/`, each schema is one model under `open_mammotion/models/`,
and each endpoint is exactly one public method (D18 allows thin per-enum-value
wrappers over it). Every endpoint has one
documentation page section (`docs/api/<group>.md`), one fake-server route
(`tests/fakeserver/`), and one unit-test module. Adding an endpoint means
touching those four places and nothing else.

## 3. Layers point one way

```
models  ←  transport  ←  api  ←  client
```

A layer imports only from the layers to its left. `api` depends on the
`Requester` protocol, never on the aiohttp adapter. `transport` depends on the
`TokenProvider` protocol, never on `TokenManager`. Nothing in the package knows
that Home Assistant, or any other host, exists.

## 4. All I/O is asynchronous

Every network call is `async`. There is no blocking I/O, no thread pool, and no
global event loop reference. A host may supply its own HTTP session; the
library must work with it and must not close it.

## 5. Errors are typed, scoped and honest

- A non-success response is an exception, never a return value. A 401 raises;
  it is not a `Response(code=401)` that a caller can mistake for an empty list.
- Transient failures (network, timeout, 5xx, 429, non-JSON body) are
  `TransportError`. They never change credential state.
- A rejected client credential is terminal: `CredentialsRejectedError` is
  raised, the manager refuses every later call without touching the network,
  and only the host can clear it by supplying new credentials. There are no
  retry timers or cooldowns; a rejected secret does not become valid by waiting.
- Exactly one reactive refresh per stale token. Concurrent callers that hit the
  same dead token share one refresh; they do not each rotate it.

## 6. Secrets stay secret

`client_secret`, `access_token` and `refresh_token` never appear in log lines,
`repr`, exception messages or test output. Models holding them redact in
`__repr__`. Logs may carry a token fingerprint (`jti` or short hash plus expiry)
and nothing more.

## 7. Wire models are tolerant

The library never crashes on a new field, a new enum value, or a missing
optional field. Unknown keys are ignored, unknown enum values decode to
`UNKNOWN` and are logged once, optional fields have defaults. A required field
that is missing is a contract violation and raises `ContractError` with the
field named.

## 8. Tests are part of the deliverable

Nothing merges without tests in the right tier (`docs/testing.md`). A
regression test has been watched failing against the bug before the fix.
Doubles are real objects or hand-written fakes with the same interface; a bare
`MagicMock` is not a test double.

## 9. Documentation lives outside the code

Design lives in `docs/`, not in comments. A comment states a constraint the
code cannot express; it is one or two lines and never a paragraph. Every
non-obvious design choice is a numbered entry in `docs/decisions.md` with the
reason. Open debt is in `docs/backlog.md`; unknowns about the API are in
`docs/open_questions.md`.

## 10. The public surface is deliberate

`open_mammotion.__all__` lists the supported API. Anything not in it may
change without notice. Versioning follows semver; a breaking change to a
listed name bumps the major version.
