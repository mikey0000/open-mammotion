# open-mammotion

An asynchronous Python client for the [Mammotion Open API](https://developer.mammotion.com/apis):
list your mowers, read their status, start and stop tasks, and query work
reports and fault history with the developer credentials from the Mammotion
developer portal.

Written clean-room from the published OpenAPI specification. It does not
depend on, or share code with, `pymammotion`; it is a different identity
(developer client credentials, not the app login) against a different host.

## Status

Phase 2: authentication and every request/response endpoint in the
specification. The push channel (SSE) and the LAN WebSocket are on the
[backlog](docs/backlog.md). Only mower models released in 2025 are served by
the API.

## Install

```bash
uv add open-mammotion      # or: pip install open-mammotion
```

Python 3.13 or newer.

## Use

```python
import asyncio
import os

from open_mammotion import ClientCredentials, OpenMammotion


async def main() -> None:
    credentials = ClientCredentials(
        client_id=os.environ["OPEN_MAMMOTION_CLIENT_ID"],
        client_secret=os.environ["OPEN_MAMMOTION_CLIENT_SECRET"],
    )
    async with OpenMammotion(credentials) as api:
        for mower in await api.devices.list():
            detail = await api.devices.get(mower.device_id)
            print(mower.nickname, detail.status, detail.battery_level)

        tasks = await api.actions.tasks(mower.device_id)
        await api.actions.start(mower.device_id, task_name=tasks[0].task_name)


asyncio.run(main())
```

Bring your own `aiohttp.ClientSession` with `OpenMammotion(credentials,
session=...)`; the library never closes a session it did not create. Persist
tokens across restarts with `on_token_updated` and `TokenSet.to_dict()`.

## Errors

| Exception | Meaning | What to do |
|---|---|---|
| `TransportError` | network, timeout, 429, 5xx, malformed body | back off and retry |
| `ApiError` | the API answered with a non-success `code` | read `.code`, `.msg`, `.request_id` |
| `CommandRejectedError` | the mower refused an action | read `.message` |
| `UnauthorizedError` | 401 even after one token refresh | the next call refreshes again; persistent means Q2 |
| `CredentialsRejectedError` | the client id/secret was rejected; terminal | obtain new credentials from the portal |
| `ContractError` | the response did not match the specification | file an issue with the `request_id` |

## Documentation

- [Constitution](CONSTITUTION.md) — the rules
- [Architecture](docs/architecture.md) — layers, flows, single homes
- [API reference](docs/api/README.md) — every endpoint in library terms
- [Decisions](docs/decisions.md), [Open questions](docs/open_questions.md), [Backlog](docs/backlog.md)
- [Code style](docs/code_style.md), [Testing](docs/testing.md)

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ty check open_mammotion/
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

GPL-3.0-or-later.
