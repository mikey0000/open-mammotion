"""Tree walkers and AST matchers shared by the convention checks in ``test_conventions.py``."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "open_mammotion"
PACKAGE = PACKAGE_DIR.name
TESTS_DIR = REPO_ROOT / "tests"
UNIT_DIR = TESTS_DIR / "unit"
FAKESERVER_DIR = TESTS_DIR / "fakeserver"
REGRESSION_DIR = TESTS_DIR / "regression"
META_DIR = TESTS_DIR / "meta"

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, order=True)
class Offence:
    """One violation, rendered as ``path:line: detail`` so an author can jump straight to it."""

    path: Path
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{rel(self.path)}:{self.line}: {self.detail}"


def rel(path: Path) -> str:
    """``path`` relative to the repository root, POSIX-style."""
    return path.relative_to(REPO_ROOT).as_posix()


def python_files(root: Path, *, exclude: Iterable[Path] = ()) -> list[Path]:
    """Every ``.py`` file under ``root``, sorted, skipping caches and anything under ``exclude``."""
    excluded = tuple(exclude)
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and not any(path.is_relative_to(ex) for ex in excluded)
    )


def is_under(path: Path, *roots: Path) -> bool:
    """Whether ``path`` lies inside any of ``roots``."""
    return any(path.is_relative_to(root) for root in roots)


@cache
def parse(path: Path) -> ast.Module:
    """The parsed module; cached because several checks walk the same files."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def report(summary: str, offences: Iterable[Offence | str]) -> str:
    """A failure message: the rule, then every offender on its own line."""
    lines = sorted(str(o) for o in offences)
    return "\n".join([f"{summary} ({len(lines)}):", *(f"  {line}" for line in lines)])


def module_name(path: Path) -> str:
    """Dotted module name of a file under the repository root (``pkg/__init__.py`` → ``pkg``)."""
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def module_exists(dotted: str) -> bool:
    """Whether ``dotted`` names a module or package in the repository."""
    base = REPO_ROOT.joinpath(*dotted.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Local name → fully qualified name for every absolute import anywhere in ``tree``."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    aliases[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def qualified_name(expr: ast.expr, aliases: dict[str, str]) -> str | None:
    """``asyncio.sleep`` for ``asyncio.sleep``, ``aio.sleep`` or a bare imported ``sleep``; else ``None``."""
    match expr:
        case ast.Name(id=name):
            return aliases.get(name, name)
        case ast.Attribute(value=value, attr=attr):
            base = qualified_name(value, aliases)
            return f"{base}.{attr}" if base else None
        case _:
            return None


def calls(tree: ast.Module) -> Iterator[tuple[ast.Call, str]]:
    """Every call in ``tree`` whose target resolves to a dotted name, with that name."""
    aliases = import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (name := qualified_name(node.func, aliases)):
            yield node, name


def resolve_from(node: ast.ImportFrom, importer: Path) -> str:
    """The absolute module an ``ImportFrom`` reads from, resolving relative levels against ``importer``."""
    if not node.level:
        return node.module or ""
    package = module_name(importer).split(".")
    if importer.name != "__init__.py":
        package = package[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base)


def imported_modules(tree: ast.Module, importer: Path) -> Iterator[tuple[int, str]]:
    """``(line, module)`` for every import in ``tree``, ``TYPE_CHECKING`` blocks included.

    ``from pkg import name`` counts as importing ``pkg.name``; for an in-repo ``pkg`` only when ``name`` is a
    module, else ``pkg`` (so a name re-exported by ``__init__`` counts as depending on the package).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            source = resolve_from(node, importer)
            in_repo = module_exists(source.split(".", maxsplit=1)[0])
            for alias in node.names:
                candidate = f"{source}.{alias.name}"
                yield node.lineno, candidate if module_exists(candidate) or not in_repo else source


def is_within(module: str, prefix: str) -> bool:
    """Whether ``module`` is ``prefix`` or one of its submodules."""
    return module == prefix or module.startswith(f"{prefix}.")


def is_regression_marker(expr: ast.expr, aliases: dict[str, str]) -> bool:
    """``pytest.mark.regression``, called or not, however ``pytest`` or ``mark`` was imported."""
    target = expr.func if isinstance(expr, ast.Call) else expr
    return qualified_name(target, aliases) == "pytest.mark.regression"


def _pytestmark_has_regression(body: list[ast.stmt], aliases: dict[str, str]) -> bool:
    for stmt in body:
        match stmt:
            case (
                ast.Assign(targets=[ast.Name(id="pytestmark")], value=value)
                | ast.AnnAssign(target=ast.Name(id="pytestmark"), value=value)
            ) if value is not None:
                values = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
                if any(is_regression_marker(v, aliases) for v in values):
                    return True
    return False


@dataclass(frozen=True)
class CollectedTest:
    """A pytest-collected test function and whether a regression marker reaches it."""

    path: Path
    node: FunctionNode
    marked_regression: bool


def collect_tests(path: Path, tree: ast.Module) -> Iterator[CollectedTest]:
    """Every ``test*`` function at module level or inside ``Test*`` classes, however deeply nested."""
    aliases = import_aliases(tree)
    module_marked = _pytestmark_has_regression(tree.body, aliases)
    yield from _collect(path, tree.body, aliases, inherited=module_marked)


def _collect(path: Path, body: list[ast.stmt], aliases: dict[str, str], *, inherited: bool) -> Iterator[CollectedTest]:
    for stmt in body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef) and stmt.name.startswith("test"):
            marked = inherited or any(is_regression_marker(d, aliases) for d in stmt.decorator_list)
            yield CollectedTest(path, stmt, marked)
        elif isinstance(stmt, ast.ClassDef) and stmt.name.startswith("Test"):
            marked = (
                inherited
                or any(is_regression_marker(d, aliases) for d in stmt.decorator_list)
                or _pytestmark_has_regression(stmt.body, aliases)
            )
            yield from _collect(path, stmt.body, aliases, inherited=marked)


def string_literals(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """``(line, text)`` for every ``str`` or ``bytes`` constant, docstrings and f-string parts included."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                yield node.lineno, node.value
            elif isinstance(node.value, bytes):
                yield node.lineno, node.value.decode("latin-1")


def function_params(node: FunctionNode) -> Iterator[str]:
    """Every parameter name of ``node``."""
    args = node.args
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg):
        if arg is not None:
            yield arg.arg


def top_level_defs(tree: ast.Module) -> Iterator[FunctionNode]:
    """Module-level functions and methods of module-level classes; closures are not definitions of record."""
    for stmt in tree.body:
        body = stmt.body if isinstance(stmt, ast.ClassDef) else [stmt]
        yield from (n for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))


def functions(tree: ast.Module) -> Iterator[FunctionNode]:
    """Every function or method in ``tree``, nested ones included."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
