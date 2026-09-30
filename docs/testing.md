# Testing

This is the testing constitution. `tests/meta/test_conventions.py` asserts the
mechanical parts; review catches the rest.

## 1. Tiers

| Tier | Directory | Touches | Runs |
|---|---|---|---|
| unit | `tests/unit/` | one module, hand-written fakes for the layer below, no sockets, no real clock | every commit, < 5 s |
| integration | `tests/integration/` | the real `OpenMammotion` facade against `tests/fakeserver` over loopback (`test_facade_*.py`), and the fake's own contract tests through a raw client (`test_fakeserver_contract_*.py`) | every commit, < 30 s |
| regression | `tests/regression/` | cross-module pins for bugs that escaped; single-module pins live beside the module | every commit |
| live | `tests/live/` | the real Open API with real credentials from the environment; marked `live`, skipped when unset | on demand |

A unit test that imports `tests.fakeserver` is an integration test in the
wrong directory. An integration test that patches a private method is a unit
test in the wrong directory.

## 2. Layout mirrors the package

```
open_mammotion/auth/token_manager.py   →  tests/unit/auth/test_token_manager.py
open_mammotion/api/devices.py          →  tests/unit/api/test_devices.py
open_mammotion/models/work_report.py   →  tests/unit/models/test_work_report.py
```

One test module per source module. Split by concern
(`test_token_manager_refresh.py`) when a module passes ~500 lines, never by
number. Tests are grouped in classes named for the behaviour under test
(`class TestGetAccessToken:`), with test names that read as sentences:
`test_returns_cached_token_when_fresh`, `test_raises_terminal_after_client_credentials_rejected`.

Shared builders live in one place:

- `tests/_helpers.py` — envelope and JSON builders used by more than one tier.
- `tests/unit/_fakes.py` — `FakeHttpSession`, `FakeRequester`,
  `FakeTokenProvider`, `FakeTokenClient`. Hand-written, same interface as the
  real thing, scripted responses, recorded calls.
- `tests/unit/<pkg>/_helpers.py` — builders used by more than one module in
  that package.
- `tests/unit/conftest.py` and `tests/integration/conftest.py` — tier fixtures
  (the no-network guard; the fake cloud, its clock and raw clients).
- `tests/conftest.py` — global autouse safety nets only: the `credentials`
  fixture and the guard that fails a test whose setup or call-phase logs
  carry any value in `SECRET_VALUES` (`leaked_secrets` in `tests/_helpers.py`,
  itself pinned by `tests/meta/test_guards.py`). `tests/unit/conftest.py` adds the no-network guard (the
  integration tier needs loopback).

Four copies of `make_token_set` is the failure this rule exists to stop.

Modules that need no mirror are listed in `EXEMPT_FROM_MIRRORING` in
`tests/meta/test_conventions.py`, each with a one-line reason: `const.py`,
`exceptions.py` and the pure-protocol modules `auth/protocols.py`,
`transport/requester.py`. Everything else, `transport/session.py` included, is
mirrored.

## 3. Doubles

Preference order: real object → hand-written fake. `unittest.mock` is not
imported anywhere under `tests/`: a `MagicMock` answers every attribute
truthily forever, so a renamed method keeps passing, and `create_autospec`
still lets a test assert on plumbing instead of outcomes. `monkeypatch` is for
environment variables and `const` values, not for replacing collaborators.

Never mock the unit under test. Assert on outcomes (the returned model, the
raised exception, the recorded request) rather than on call plumbing, unless
the call *is* the contract ("sends exactly one refresh for a burst of 401s").

## 4. Time and concurrency

- Anything that reads a clock takes it as a parameter (`clock: Callable[[],
  float]`) and tests pass a controllable one. `time-machine` with
  `tick=False` is the fallback for code that cannot be parameterised.
- `await asyncio.sleep(0.1)` is not synchronisation. Wait on an
  `asyncio.Event`, a future, or `asyncio.sleep(0)` for exactly one loop turn.
- Bound every wait with `asyncio.wait_for`.
- `asyncio_mode = "auto"`; no `@pytest.mark.asyncio` decorators.
- Concurrency tests (the 401 burst, the refresh lock) use a fake whose
  responses are gated on an `asyncio.Event` so the interleaving is
  deterministic.

## 5. Secrets in tests

Fixture credentials are obviously fake (`client_id="cid-test"`,
`client_secret="not-a-real-secret"`). Tests assert that `repr()` and
`str(exc)` do **not** contain them. Live tests read credentials from
`OPEN_MAMMOTION_CLIENT_ID` / `OPEN_MAMMOTION_CLIENT_SECRET` and never print
them.

## 6. The fake server

`tests/fakeserver/` is an aiohttp application that implements every endpoint
in `docs/openapi/` plus a `/control` endpoint for fault injection (expire the
current token, reject the next refresh, reject client credentials, return a
given envelope code, return a non-JSON body, delay). It keeps its own state
(issued tokens, devices, reports) and asserts request shape server-side
(headers present, body matches the schema). It is the executable form of the
specification; when the spec and the fake disagree, fix the fake and add a
note to `docs/open_questions.md`.

Integration tests point the library at it through the facade's `api_url` and
`auth_url` arguments (`FakeCloud.url`); a host's dev install uses the
`OPEN_MAMMOTION_API_URL` and `OPEN_MAMMOTION_AUTH_URL` environment overrides.
`tests/fakeserver/clock.py` holds `ManualClock` and `RecordingSleep`, injected
into `FakeState`, so nothing in the fake reads real time.
`GET /control` reports `token_grants` for accepted grants only; a rejected
grant is visible in `state.requests`.

## 7. Regression contract

A regression test:

1. was written against the broken code and seen red;
2. is marked `@pytest.mark.regression`;
3. is named for the behaviour, not the ticket;
4. has a docstring stating what the code did wrong;
5. lives beside the module it pins, or in `tests/regression/` when it spans
   modules.

## 8. Coverage and gates

- `pytest --cov=open_mammotion` must not drop below the number in
  `pyproject.toml`. Coverage is a floor, not a target; a line covered by a
  test that asserts nothing is not tested.
- `tests/meta/test_conventions.py` checks: mirroring, no `unittest.mock`, no
  `asyncio.sleep(<non-zero>)` outside `tests/fakeserver/` (whose delay knob is
  behaviour under test), no `tests.fakeserver` import under `unit/`,
  regression marker ↔ docstring, no real hostnames or secret-shaped literals
  in tests, fakes only in `tests/unit/_fakes.py`, builders defined once, the
  layer map, top-level imports only, `__all__` importable and sorted, no
  self-driven event loops.
- Pre-commit runs ruff, ruff-format, ty and the unit tier.

## 9. Writing a test

```python
class TestGetAccessToken:
    async def test_shares_one_refresh_across_concurrent_callers(self, credentials: ClientCredentials) -> None:
        granter = FakeTokenClient(client_credentials=deque([make_token_set()]))
        granter.gate = asyncio.Event()
        manager = TokenManager(credentials, granter, clock=lambda: 1_000.0)

        tasks = [asyncio.create_task(manager.get_access_token()) for _ in range(5)]
        await asyncio.wait_for(granter.wait_for_calls(1), timeout=1)
        granter.gate.set()
        tokens = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert len(set(tokens)) == 1
        assert granter.calls == ["client_credentials"]
```

Arrange, act, assert, separated by blank lines. One behaviour per test. The
assertion says what the contract is. A fake's `wait_for_calls(n)` is how a test
waits for concurrent callers to arrive; `asyncio.sleep(0)` is only for "exactly
one loop turn" and is fragile for anything else.
