"""``python -m tests.fakeserver --port 8765``: run the fake cloud standalone until interrupted."""

from __future__ import annotations

import argparse
import asyncio
import contextlib

from tests.fakeserver.server import LOOPBACK, FakeCloud


async def _serve(port: int) -> None:
    async with FakeCloud(port=port) as cloud:
        print(f"Fake Mammotion cloud listening on {cloud.url}", flush=True)  # noqa: T201 — this is a CLI
        print(f"export OPEN_MAMMOTION_API_URL={cloud.url} OPEN_MAMMOTION_AUTH_URL={cloud.url}", flush=True)  # noqa: T201
        await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fake Mammotion Open API on loopback.")
    parser.add_argument("--port", type=int, default=0, help=f"port on {LOOPBACK} (default: ephemeral)")
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve(args.port))


if __name__ == "__main__":
    main()
