"""Mechanical checks of the conventions in docs/testing.md, docs/code_style.md and CONSTITUTION.md.

Each class is one rule. A rule is a pure ``_<rule>(path, tree) -> list[Offence]`` function: one test drives it over
the real tree and lists every offending ``path:line``; the others feed it snippets so the check cannot pass vacuously.
"""

from __future__ import annotations

import ast
import importlib
import re
from typing import TYPE_CHECKING

import pytest

from tests.meta._helpers import (
    FAKESERVER_DIR,
    META_DIR,
    PACKAGE,
    PACKAGE_DIR,
    REGRESSION_DIR,
    REPO_ROOT,
    TESTS_DIR,
    UNIT_DIR,
    Offence,
    calls,
    collect_tests,
    function_params,
    functions,
    import_aliases,
    imported_modules,
    is_under,
    is_within,
    parse,
    python_files,
    qualified_name,
    rel,
    report,
    string_literals,
    top_level_defs,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    type Rule = Callable[[Path, ast.Module], list[Offence]]

EXEMPT_FROM_MIRRORING = frozenset(
    {
        "const.py",  # constants only; exercised through every module that reads them
        "exceptions.py",  # the hierarchy is exercised by every test that expects a raise
        "auth/protocols.py",  # pure typing.Protocol definitions, no behaviour
        "transport/requester.py",  # pure typing.Protocol definition, no behaviour
    }
)

MOCK_MODULES = ("unittest.mock", "mock", "pytest_mock")
MOCKER_FIXTURES = frozenset({"mocker", "class_mocker", "module_mocker", "package_mocker", "session_mocker"})

EVENT_LOOP_CALLS = frozenset(
    {
        "asyncio.run",
        "asyncio.Runner",
        "asyncio.get_event_loop",
        "asyncio.new_event_loop",
        "asyncio.set_event_loop",
    }
)

SOCKET_TEST_NAMES = frozenset({"TestServer", "TestClient", "RawTestServer"})
SOCKET_TEST_FIXTURES = frozenset({"aiohttp_client", "aiohttp_server", "aiohttp_raw_server"})
UNIT_FORBIDDEN_MODULES = ("tests.fakeserver", "aiohttp.test_utils")

REAL_HOST = "mammotion.com"
JWT_SHAPE = re.compile(r"eyJ[\w-]*\.[\w-]*\.")
SECRET_RUN = re.compile(r"[A-Za-z0-9+/=_-]{41,}")
SECRET_SEGMENT = re.compile(r"[A-Za-z0-9+/=]{20,}")

BUILDER = re.compile(r"_?make_\w+")

FORBIDDEN_EVERYWHERE = ("homeassistant", "pymammotion", "tests")

# layer → (package modules it may import, package modules it may not; None forbids every other one)
LAYER_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...] | None]] = {
    "models": (("exceptions", "const"), None),
    "auth": (("transport.session",), ("transport", "api", "client")),
    "transport": (("auth.protocols", "auth.credentials"), ("auth", "api", "client")),
    "api": (("transport.requester", "auth.protocols", "auth.credentials"), ("transport", "auth", "client")),
}


def _source_modules() -> list[Path]:
    return python_files(PACKAGE_DIR)


def _unit_test_files() -> list[Path]:
    return python_files(UNIT_DIR)


def _sweep(rule: Rule, paths: Iterable[Path]) -> list[Offence]:
    return [offence for path in paths for offence in rule(path, parse(path))]


def _snippet(rule: Rule, source: str, path: Path) -> list[Offence]:
    return rule(path, ast.parse(source))


SNIPPET_TEST = UNIT_DIR / "api" / "test_snippet.py"
SNIPPET_REGRESSION_TEST = REGRESSION_DIR / "test_snippet.py"


class TestMirroring:
    """testing.md §2: "One test module per source module", laid out to mirror the package."""

    def test_every_source_module_has_a_unit_test_module(self) -> None:
        """§2: ``open_mammotion/<dir>/<mod>.py`` → ``tests/unit/<dir>/test_<mod>.py``."""
        missing = []
        for path in _source_modules():
            relative = path.relative_to(PACKAGE_DIR)
            if path.stem.startswith("_") or relative.as_posix() in EXEMPT_FROM_MIRRORING:
                continue
            expected = UNIT_DIR / relative.parent / f"test_{path.stem}.py"
            if not expected.is_file():
                missing.append(f"{rel(path)} → expected {rel(expected)}")

        assert not missing, report("Source modules without a mirrored unit-test module", missing)

    def test_every_unit_test_module_names_an_existing_source_module(self) -> None:
        """§2: a ``tests/unit/**/test_<mod>[_<concern>].py`` must pin a real ``open_mammotion`` module."""
        orphans = []
        for path in _unit_test_files():
            if not path.stem.startswith("test_"):
                continue
            source_dir = PACKAGE_DIR / path.parent.relative_to(UNIT_DIR)
            stems = {p.stem for p in source_dir.glob("*.py")} if source_dir.is_dir() else set()
            if not _names_a_module(path.stem.removeprefix("test_"), stems):
                orphans.append(f"{rel(path)} → no module in {rel(source_dir)}/ matches")

        assert not orphans, report("Unit-test modules that mirror no source module", orphans)

    def test_every_exemption_names_an_existing_module(self) -> None:
        """§2: a stale exemption would silently exempt whatever file next takes its name."""
        stale = [entry for entry in EXEMPT_FROM_MIRRORING if not (PACKAGE_DIR / entry).is_file()]

        assert not stale, report("EXEMPT_FROM_MIRRORING entries with no source module", stale)

    @pytest.mark.parametrize(
        ("name", "stems", "matches"),
        [
            ("token_manager", {"token_manager"}, True),
            ("token_manager_refresh", {"token_manager"}, True),
            ("base", {"_base"}, True),
            ("gone", {"token_manager"}, False),
        ],
    )
    def test_matches_test_modules_to_source_stems(self, name: str, stems: set[str], *, matches: bool) -> None:
        assert _names_a_module(name, stems) is matches


def _names_a_module(name: str, stems: set[str]) -> bool:
    """``name`` is ``<mod>`` or ``<mod>_<concern>`` for a module stem, where ``_base`` answers to ``base``."""
    candidates = [name] + [name[:i] for i, char in enumerate(name) if char == "_"]
    return any(c in stems or f"_{c}" in stems for c in candidates if c)


def _mocking(path: Path, tree: ast.Module) -> list[Offence]:
    offences = [
        Offence(path, line, f"imports {module}")
        for line, module in imported_modules(tree, path)
        if any(is_within(module, m) for m in MOCK_MODULES)
    ]
    offences.extend(
        Offence(path, fn.lineno, f"{fn.name}() takes the {param!r} fixture")
        for fn in functions(tree)
        for param in function_params(fn)
        if param in MOCKER_FIXTURES
    )
    return offences


class TestNoMockingLibrary:
    """testing.md §8: "no ``MagicMock``"; §3: doubles are real objects or hand-written fakes."""

    def test_no_test_module_imports_a_mocking_library_or_takes_mocker(self) -> None:
        """§8: no ``unittest.mock``, ``mock`` or ``pytest_mock`` import, no ``mocker`` fixture."""
        offences = _sweep(_mocking, python_files(TESTS_DIR))

        assert not offences, report("Mocking library used in tests", offences)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("from unittest.mock import MagicMock", True),
            ("from unittest import mock", True),
            ("import unittest.mock", True),
            ("import mock", True),
            ("def test_x(mocker): ...", True),
            ("from unittest import TestCase", False),
            ("def test_x(monkeypatch): ...", False),
        ],
    )
    def test_flags_every_spelling_of_a_mock(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_mocking, source, SNIPPET_TEST)) is flagged


def _sleeps(path: Path, tree: ast.Module) -> list[Offence]:
    return [
        Offence(path, call.lineno, ast.unparse(call))
        for call, name in calls(tree)
        if name == "time.sleep" or (name == "asyncio.sleep" and not _is_one_loop_turn(call))
    ]


def _is_one_loop_turn(call: ast.Call) -> bool:
    delays = [*call.args[:1], *(kw.value for kw in call.keywords if kw.arg == "delay")]
    return len(delays) == 1 and isinstance(delays[0], ast.Constant) and delays[0].value == 0


class TestNoSleepingForSynchronisation:
    """testing.md §4: "``await asyncio.sleep(0.1)`` is not synchronisation"; wait on an Event or future."""

    def test_no_test_sleeps_for_anything_but_one_loop_turn(self) -> None:
        """§4: only ``asyncio.sleep(0)`` is allowed; ``time.sleep`` never.

        ``tests/fakeserver/`` is exempt: its ``/control`` delay fault (§6) is behaviour, not synchronisation.
        """
        offences = _sweep(_sleeps, python_files(TESTS_DIR, exclude=[FAKESERVER_DIR]))

        assert not offences, report("Sleeps used for synchronisation", offences)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("import asyncio\nawait asyncio.sleep(0)", False),
            ("import asyncio\nawait asyncio.sleep(delay=0)", False),
            ("import asyncio\nawait asyncio.sleep(0.1)", True),
            ("import asyncio\nawait asyncio.sleep(delay)", True),
            ("import asyncio as aio\nawait aio.sleep(1)", True),
            ("from asyncio import sleep\nawait sleep(1)", True),
            ("from time import sleep\nsleep(0)", True),
            ("import time\ntime.sleep(0)", True),
        ],
    )
    def test_allows_only_a_zero_delay(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_sleeps, source, SNIPPET_TEST)) is flagged


def _unit_isolation(path: Path, tree: ast.Module) -> list[Offence]:
    offences = [
        Offence(path, line, f"imports {module}")
        for line, module in imported_modules(tree, path)
        if any(is_within(module, m) for m in UNIT_FORBIDDEN_MODULES)
    ]
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) | ast.Attribute(attr=name) if name in SOCKET_TEST_NAMES:
                offences.append(Offence(path, node.lineno, f"names {name}"))
            case ast.ImportFrom(names=names):
                offences.extend(
                    Offence(path, node.lineno, f"imports {a.name}") for a in names if a.name in SOCKET_TEST_NAMES
                )
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                offences.extend(
                    Offence(path, node.lineno, f"{node.name}() takes the {p!r} fixture")
                    for p in function_params(node)
                    if p in SOCKET_TEST_FIXTURES
                )
    return offences


class TestUnitTierIsolation:
    """testing.md §1: "A unit test that imports ``tests.fakeserver`` is an integration test in the wrong directory"."""

    def test_no_unit_test_reaches_the_fake_server_or_a_socket_harness(self) -> None:
        """§1 and §8: no ``tests.fakeserver``, ``aiohttp.test_utils``, ``TestServer``/``TestClient`` under unit/."""
        offences = _sweep(_unit_isolation, _unit_test_files())

        assert not offences, report("Unit tests that leave the unit tier", offences)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("from tests.fakeserver import app", True),
            ("from tests import fakeserver", True),
            ("import tests.fakeserver.routes", True),
            ("from aiohttp import test_utils", True),
            ("from aiohttp.test_utils import TestServer", True),
            ("server = TestClient(app)", True),
            ("async def test_x(aiohttp_client): ...", True),
            ("from tests.unit._fakes import FakeRequester", False),
            ("from aiohttp import ClientSession", False),
        ],
    )
    def test_flags_the_fake_server_and_socket_harnesses(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_unit_isolation, source, SNIPPET_TEST)) is flagged


def _undocumented_regressions(path: Path, tree: ast.Module) -> list[Offence]:
    return [
        Offence(path, test.node.lineno, f"{test.node.name}() has no docstring")
        for test in collect_tests(path, tree)
        if test.marked_regression and not ast.get_docstring(test.node)
    ]


def _unmarked_regressions(path: Path, tree: ast.Module) -> list[Offence]:
    return [
        Offence(path, test.node.lineno, f"{test.node.name}() lacks @pytest.mark.regression")
        for test in collect_tests(path, tree)
        if not test.marked_regression and ("regression" in test.node.name or is_under(path, REGRESSION_DIR))
    ]


class TestRegressionContract:
    """testing.md §7: a regression test "is marked ``@pytest.mark.regression``" and "has a docstring"."""

    def test_every_marked_test_has_a_docstring(self) -> None:
        """§7.4: the docstring states what the code did wrong."""
        offences = _sweep(_undocumented_regressions, python_files(TESTS_DIR))

        assert not offences, report("Regression tests without a docstring", offences)

    def test_every_test_named_or_filed_as_one_carries_the_marker(self) -> None:
        """§7.2 and §7.5: a test named for a regression, or living in ``tests/regression/``, is marked."""
        offences = _sweep(_unmarked_regressions, python_files(TESTS_DIR))

        assert not offences, report("Regression tests without the marker", offences)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("@pytest.mark.regression\ndef test_x(): ...", True),
            ('@pytest.mark.regression\ndef test_x():\n    """Did wrong."""', False),
            ("@pytest.mark.regression\nclass TestX:\n    def test_x(self): ...", True),
            ("pytestmark = [pytest.mark.regression]\ndef test_x(): ...", True),
            ("class TestX:\n    pytestmark = pytest.mark.regression\n    def test_x(self): ...", True),
            ("from pytest import mark\n@mark.regression\ndef test_x(): ...", True),
            ("def test_x(): ...", False),
        ],
    )
    def test_requires_a_docstring_wherever_the_marker_comes_from(self, source: str, *, flagged: bool) -> None:
        full = f"import pytest\n{source}"

        assert bool(_snippet(_undocumented_regressions, full, SNIPPET_TEST)) is flagged

    @pytest.mark.parametrize(
        ("source", "path", "flagged"),
        [
            ("def test_regression_keeps_token(): ...", SNIPPET_TEST, True),
            ("def test_keeps_token(): ...", SNIPPET_REGRESSION_TEST, True),
            ("@pytest.mark.regression\ndef test_regression_keeps_token(): ...", SNIPPET_TEST, False),
            ("pytestmark = pytest.mark.regression\ndef test_keeps_token(): ...", SNIPPET_REGRESSION_TEST, False),
            ("def test_keeps_token(): ...", SNIPPET_TEST, False),
        ],
    )
    def test_requires_the_marker_by_name_or_directory(self, source: str, path: Path, *, flagged: bool) -> None:
        full = f"import pytest\n{source}"

        assert bool(_snippet(_unmarked_regressions, full, path)) is flagged


def _hosts_and_secrets(path: Path, tree: ast.Module) -> list[Offence]:
    return [Offence(path, line, reason) for line, text in string_literals(tree) if (reason := _secret_or_host(text))]


def _secret_or_host(text: str) -> str | None:
    """Why ``text`` is suspect, or ``None``.

    A secret-shaped run is 41+ base64/hex characters with a digit and one 20+ character unbroken segment,
    so long snake_case identifiers and test ids do not trip it.
    """
    if REAL_HOST in text.lower():
        return f"names the real host ({text[:60]!r})"
    if JWT_SHAPE.search(text):
        return "contains a JWT-shaped value"
    for run in SECRET_RUN.findall(text):
        if any(c.isdigit() for c in run) and SECRET_SEGMENT.search(run):
            return f"contains a secret-shaped run ({run[:12]}…, {len(run)} chars)"
    return None


class TestNoRealHostsOrSecrets:
    """testing.md §5: "Fixture credentials are obviously fake"; hosts come from ``open_mammotion.const``."""

    def test_no_test_literal_names_the_real_host_or_looks_like_a_secret(self) -> None:
        """§5 and §8 ("no real hostnames in tests"): no real host, no JWT, no long base64/hex run.

        ``tests/meta/`` is exempt: it spells out the patterns it forbids.
        """
        offences = _sweep(_hosts_and_secrets, python_files(TESTS_DIR, exclude=[META_DIR]))

        assert not offences, report("Test literals carrying a real host or secret-shaped value", offences)

    @pytest.mark.parametrize(
        ("text", "suspect"),
        [
            ("not-a-real-secret", False),
            ("test_returns_cached_token_when_fresh_and_the_lock_is_free", False),
            (f"https://api-open.{REAL_HOST}/v1", True),
            (f"https://ID.{REAL_HOST.upper()}", True),
            ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig", True),
            ("0123456789abcdef0123456789abcdef0123456789abcdef", True),
        ],
    )
    def test_flags_real_hosts_and_secret_shaped_literals(self, text: str, *, suspect: bool) -> None:
        assert bool(_snippet(_hosts_and_secrets, repr(text), SNIPPET_TEST)) is suspect


def _misplaced_fakes(path: Path, tree: ast.Module) -> list[Offence]:
    return [
        Offence(path, node.lineno, f"defines {node.name}")
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name.startswith("Fake")
    ]


def _duplicated_builders(files: Iterable[tuple[Path, ast.Module]]) -> list[Offence]:
    homes: dict[str, list[Offence]] = {}
    for path, tree in files:
        for fn in top_level_defs(tree):
            if BUILDER.fullmatch(fn.name):
                homes.setdefault(fn.name.lstrip("_"), []).append(Offence(path, fn.lineno, f"defines {fn.name}()"))
    return [o for defs in homes.values() if len({d.path for d in defs}) > 1 for o in defs]


class TestFakesLiveInOnePlace:
    """D13: "``tests/unit/_fakes.py`` holds every hand-written fake"; testing.md §2: builders live in one place."""

    def test_no_fake_class_is_defined_outside_the_fakes_module(self) -> None:
        """D13: ``Fake*`` classes live in ``tests/unit/_fakes.py`` (the fake server is its own thing)."""
        home = UNIT_DIR / "_fakes.py"
        offences = _sweep(_misplaced_fakes, python_files(TESTS_DIR, exclude=[FAKESERVER_DIR, home]))

        assert not offences, report(f"Fakes defined outside {rel(home)}", offences)

    def test_no_builder_is_defined_in_more_than_one_module(self) -> None:
        """§2: "Four copies of ``make_token_set`` is the failure this rule exists to stop".

        Scans ``tests/unit/`` plus ``tests/_helpers.py``, so a unit module shadowing a shared builder is caught.
        """
        files = [(p, parse(p)) for p in [*_unit_test_files(), TESTS_DIR / "_helpers.py"] if p.is_file()]
        duplicated = _duplicated_builders(files)

        assert not duplicated, report("Builders defined in more than one module (move to _helpers.py)", duplicated)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [("class FakeClock: ...", True), ("def f():\n    class FakeX: ...", True), ("class Clock: ...", False)],
    )
    def test_flags_fake_classes_at_any_depth(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_misplaced_fakes, source, SNIPPET_TEST)) is flagged

    @pytest.mark.parametrize(
        ("first", "second", "flagged"),
        [
            ("def make_token(): ...", "def make_token(): ...", True),
            ("def _make_token(): ...", "def make_token(): ...", True),
            ("class TestX:\n    def make_token(self): ...", "def make_token(): ...", True),
            ("def test_a():\n    def make_token(): ...", "def make_token(): ...", False),
            ("def make_token(): ...", "def make_device(): ...", False),
        ],
    )
    def test_flags_a_builder_defined_twice(self, first: str, second: str, *, flagged: bool) -> None:
        files = [(UNIT_DIR / "a.py", ast.parse(first)), (UNIT_DIR / "b.py", ast.parse(second))]

        assert bool(_duplicated_builders(files)) is flagged


def _layer_rule(importer: Path, module: str) -> str | None:
    """Why ``importer`` may not import ``module``, or ``None`` if the layer map allows it."""
    if module.split(".", maxsplit=1)[0] in FORBIDDEN_EVERYWHERE:
        return f"imports {module}: the package knows no host, legacy library or test code"
    parts = importer.relative_to(PACKAGE_DIR).parts
    if len(parts) > 1 and module == PACKAGE:
        return f"imports the package root {PACKAGE}, which re-exports the client; import the defining module"
    if (rule := LAYER_RULES.get(parts[0])) is None or not is_within(module, PACKAGE):
        return None
    allowed, forbidden = rule
    if any(is_within(module, f"{PACKAGE}.{name}") for name in (parts[0], *allowed)):
        return None
    if forbidden is None or any(is_within(module, f"{PACKAGE}.{name}") for name in forbidden):
        return f"{parts[0]}/ imports {module}"
    return None


def _layer_violations(path: Path, tree: ast.Module) -> list[Offence]:
    return [
        Offence(path, line, reason)
        for line, module in imported_modules(tree, path)
        if (reason := _layer_rule(path, module))
    ]


class TestLayerDirection:
    """Constitution §3: "A layer imports only from the layers to its left"; architecture.md §1."""

    def test_no_package_module_imports_against_the_layer_map(self) -> None:
        """§3: models ← transport ← api ← client; ``TYPE_CHECKING`` imports count as dependencies."""
        offences = _sweep(_layer_violations, _source_modules())

        assert not offences, report("Imports that point the wrong way", offences)

    @pytest.mark.parametrize(
        ("importer", "module", "allowed"),
        [
            ("models/device.py", "open_mammotion.models.common", True),
            ("models/device.py", "open_mammotion.transport.session", False),
            ("auth/token_client.py", "open_mammotion.transport.session", True),
            ("auth/token_client.py", "open_mammotion.transport.api", False),
            ("transport/api.py", "open_mammotion.auth.protocols", True),
            ("transport/api.py", "open_mammotion.auth.token_manager", False),
            ("api/devices.py", "open_mammotion.transport.requester", True),
            ("api/devices.py", "open_mammotion.transport", False),
            ("api/devices.py", "open_mammotion", False),
            ("client.py", "open_mammotion.transport.aiohttp_session", True),
            ("client.py", "homeassistant.core", False),
        ],
    )
    def test_applies_the_layer_map(self, importer: str, module: str, *, allowed: bool) -> None:
        assert (_layer_rule(PACKAGE_DIR / importer, module) is None) is allowed

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("if TYPE_CHECKING:\n    from open_mammotion.transport import session", True),
            ("from open_mammotion.transport import Requester", True),
            ("from ..transport import session", True),
            ("from open_mammotion.transport import requester", False),
            ("from .common import Envelope", False),
        ],
    )
    def test_resolves_type_checking_relative_and_submodule_imports(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_layer_violations, source, PACKAGE_DIR / "api" / "devices.py")) is flagged


def _local_imports(path: Path, tree: ast.Module) -> list[Offence]:
    offences = {
        (node.lineno, ast.unparse(node)): Offence(path, node.lineno, f"{ast.unparse(node)} inside {fn.name}()")
        for fn in functions(tree)
        for stmt in fn.body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Import | ast.ImportFrom)
    }
    return list(offences.values())


class TestTopLevelImportsOnly:
    """code_style.md: "Top-level imports only. No imports inside functions"."""

    def test_no_package_function_contains_an_import(self) -> None:
        """code_style.md Structure: circular-import pressure is solved with ``TYPE_CHECKING``, not local imports."""
        offences = _sweep(_local_imports, _source_modules())

        assert not offences, report("Imports inside function bodies", offences)

    @pytest.mark.parametrize(
        ("source", "count"),
        [
            ("def f():\n    import os", 1),
            ("class C:\n    async def f(self):\n        def g():\n            from os import path", 1),
            ("import os\nif TYPE_CHECKING:\n    from os import path", 0),
        ],
    )
    def test_flags_each_import_inside_a_function_once(self, source: str, count: int) -> None:
        assert len(_snippet(_local_imports, source, PACKAGE_DIR / "client.py")) == count


class TestPublicSurface:
    """Constitution §10: "``open_mammotion.__all__`` lists the supported API"."""

    def test_every_listed_name_is_importable_from_the_package(self) -> None:
        """§10: a name in ``__all__`` that the package cannot hand out is a broken promise."""
        package = importlib.import_module(PACKAGE)
        listed = getattr(package, "__all__", None)

        assert listed is not None, f"{PACKAGE}/__init__.py defines no __all__"
        missing = [name for name in listed if not hasattr(package, name)]
        assert not missing, report(f"Names in {PACKAGE}.__all__ the package does not export", missing)

    def test_all_is_sorted_without_duplicates(self) -> None:
        """§10: the surface is deliberate, so it is kept in one reviewable order."""
        listed = list(getattr(importlib.import_module(PACKAGE), "__all__", []))

        assert listed == sorted(set(listed)), (
            f"{PACKAGE}.__all__ is not sorted and unique; expected {sorted(set(listed))}"
        )


def _hand_driven_loops(path: Path, tree: ast.Module) -> list[Offence]:
    aliases = import_aliases(tree)
    offences = [
        Offence(path, call.lineno, f"calls {name}")
        for call, name in calls(tree)
        if name in EVENT_LOOP_CALLS or name.endswith(".run_until_complete")
    ]
    offences.extend(
        Offence(path, fn.lineno, f"{fn.name}() carries @pytest.mark.asyncio (asyncio_mode is auto)")
        for fn in functions(tree)
        for decorator in fn.decorator_list
        if _is_asyncio_marker(decorator, aliases)
    )
    return offences


def _is_asyncio_marker(expr: ast.expr, aliases: dict[str, str]) -> bool:
    target = expr.func if isinstance(expr, ast.Call) else expr
    return qualified_name(target, aliases) == "pytest.mark.asyncio"


class TestAsyncTests:
    """testing.md §4: "``asyncio_mode = "auto"``; no ``@pytest.mark.asyncio`` decorators"."""

    def test_no_unit_test_drives_its_own_event_loop(self) -> None:
        """§4: async tests are ``async def``; no ``asyncio.run``, ``get_event_loop``, ``run_until_complete``."""
        offences = _sweep(_hand_driven_loops, _unit_test_files())

        assert not offences, report("Unit tests driving their own event loop", offences)

    @pytest.mark.parametrize(
        ("source", "flagged"),
        [
            ("import asyncio\nasyncio.run(main())", True),
            ("from asyncio import run\nrun(main())", True),
            ("import asyncio\nasyncio.get_event_loop().run_until_complete(main())", True),
            ("import pytest\n@pytest.mark.asyncio\nasync def test_x(): ...", True),
            ("import asyncio\nasync def test_x():\n    await asyncio.wait_for(main(), 1)", False),
            ("import pytest\n@pytest.mark.parametrize('a', [1])\nasync def test_x(a): ...", False),
        ],
    )
    def test_flags_hand_driven_loops(self, source: str, *, flagged: bool) -> None:
        assert bool(_snippet(_hand_driven_loops, source, SNIPPET_TEST)) is flagged


def test_the_checks_walk_the_real_tree() -> None:
    """Guards every sweep above against passing vacuously on a mislocated root."""
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert _source_modules(), f"no source modules found under {rel(PACKAGE_DIR)}"
    assert _unit_test_files(), f"no unit-test files found under {rel(UNIT_DIR)}"
