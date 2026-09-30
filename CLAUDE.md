# CLAUDE.md

Guidance for agents working in this repository. Read `CONSTITUTION.md`
first; it is short and it is binding.

## What this is

`open-mammotion`: an async Python client for the Mammotion Open API, written
clean-room from `docs/openapi/*.json`. No code from `pymammotion` or the
Mammotion app is ported here, ever.

## Commands

```bash
uv sync
uv run ruff check --fix . && uv run ruff format .
uv run ty check open_mammotion/
uv run pytest                      # all tiers except live
uv run pytest tests/unit           # fast tier
uv run pytest -m live              # needs OPEN_MAMMOTION_CLIENT_ID/SECRET
uv run pre-commit run --all-files
```

## Where things are

| Need | Read |
|---|---|
| the rules | `CONSTITUTION.md` |
| the map (layers, flows, single homes, recipes) | `docs/architecture.md` |
| how to write code | `docs/code_style.md` |
| how to write tests | `docs/testing.md` |
| why something is the way it is | `docs/decisions.md` (numbered; cite as D7) |
| what the API is | `docs/api/*.md`, `docs/openapi/*.json` |
| what we do not know | `docs/open_questions.md` (cite as Q2) |
| what is left to do | `docs/backlog.md` |

## Rules of work

- **Audit before adding.** Every concern has a single home
  (`architecture.md` §3). If you are writing a check that exists elsewhere,
  stop and extend the existing site.
- **Spec first.** An endpoint is added in four places: model, API method,
  fake-server route, tests, plus its section in `docs/api/`. Nothing else.
- **Tests before merge, in the right tier.** Regression tests are seen red
  first and marked `regression`. Launch the `test-reviewer` agent over any
  test file you touched and fix its blocking findings before reporting done.
- **Reviews.** Non-trivial changes get the `code-reviewer` agent
  (`.claude/agents/`) before they are reported complete. The author fixes;
  the reviewer does not rewrite.
- **Decisions are written down.** A new non-obvious choice is a new numbered
  entry in `docs/decisions.md`; a new unknown is a `Qn` in
  `docs/open_questions.md`.
- **No secrets anywhere** in logs, reprs, exceptions, tests or commit
  messages.
- **Comments say why, in one or two lines, or do not exist.**
- **Commits**: imperative subject, one change per commit, no attribution
  trailers of any kind.

## Layout

```
open_mammotion/
  __init__.py  client.py  const.py  exceptions.py
  auth/        credentials.py protocols.py token_client.py token_manager.py
  transport/   session.py aiohttp_session.py requester.py api.py
  api/         _base.py devices.py actions.py work_reports.py faults.py local_network.py
  models/      common.py device.py action.py work_params.py task.py work_report.py fault.py local_network.py
tests/
  conftest.py  _helpers.py
  unit/        _fakes.py  auth/ transport/ api/ models/ test_client.py
  integration/ fake_cloud tests through the facade
  regression/  cross-module pins
  fakeserver/  aiohttp fake of the whole API + /control fault injection
  meta/        test_conventions.py
docs/          architecture.md code_style.md testing.md decisions.md backlog.md open_questions.md api/ openapi/
```
