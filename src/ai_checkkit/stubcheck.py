"""stubcheck — detect silent no-op function stubs that ship to production."""

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

NOISE = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".egg-info",
    ".ruff_cache",
    ".pytest_cache",
}

# lower number = more severe (gated first under --min-severity high)
SEV = {"bare": 0, "docstring": 1}

_TEST_RE = re.compile(r"^test_.*\.py$|.*_test\.py$")


@dataclass
class Finding:
    file: str
    line: int
    col: int
    kind: str
    detail: str


def _is_test_file(path: str) -> bool:
    p = Path(path)
    if p.name == "conftest.py":
        return True
    if _TEST_RE.match(p.name):
        return True
    for part in p.parts:
        if part in ("tests", "test"):
            return True
    return False


def _noop(stmt) -> bool:
    """True if a statement is a no-op placeholder (pass, .../Ellipsis, docstring, None)."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        v = stmt.value.value
        if v is None or v is Ellipsis or isinstance(v, str):
            return True
    return False


def _is_abstract(node) -> bool:
    """True if the function is decorated as abstract (e.g. @abstractmethod)."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and "abstractmethod" in dec.id:
            return True
        if isinstance(dec, ast.Attribute) and "abstractmethod" in dec.attr:
            return True
    return False


def _has_docstring(node) -> bool:
    return (
        bool(node.body)
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def detect(source: str, path: str, include_test: bool = False) -> list[Finding]:
    if path.endswith(".pyi"):
        return []
    if not include_test and _is_test_file(path):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # abstractmethods are *meant* to be stubs
        if _is_abstract(node):
            continue
        essential = [s for s in node.body if not _noop(s)]
        if essential:
            continue
        if _has_docstring(node):
            kind = "docstring"
            detail = (
                f"{node.name}() — body is only a docstring + pass/ellipsis; "
                "documented as pending but returns None at runtime"
            )
        else:
            kind = "bare"
            detail = (
                f"{node.name}() — body is only pass/ellipsis; "
                "silent no-op returning None — unimplemented logic shipped"
            )
        found.append(Finding(path, node.lineno, node.col_offset + 1, kind, detail))
    found.sort(key=lambda f: (f.line, f.col))
    return found


def scan_paths(
    paths: list[str], hidden: bool, include_test: bool = False
) -> list[Finding]:
    found: list[Finding] = []
    for p in paths:
        root = Path(p)
        if root.is_file():
            if root.suffix == ".py":
                found.extend(
                    detect(
                        root.read_text(encoding="utf-8", errors="replace"),
                        str(root),
                        include_test,
                    )
                )
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if not hidden:
                dirnames[:] = [d for d in dirnames if d not in NOISE]
            for fn in filenames:
                if fn.endswith(".py"):
                    full = os.path.join(dirpath, fn)
                    found.extend(
                        detect(
                            Path(full).read_text(encoding="utf-8", errors="replace"),
                            full,
                            include_test,
                        )
                    )
    return found


def _keep(f: Finding, floor: int) -> bool:
    return SEV[f.kind] <= floor


def _emit_table(found: list[Finding]) -> str:
    lines = ["file:line:col → kind|detail"]
    for f in found:
        lines.append(f"{f.file}:{f.line}:{f.col} → {f.kind}|{f.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stubcheck",
        description=(
            "Detect silent no-op function stubs (pass/ellipsis bodies) that "
            "ship to production and return None — the unimplemented logic "
            "AI leaves behind in callbacks, handlers, and overrides."
        ),
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], help="files or directories to scan"
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if any findings")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument(
        "--min-severity",
        default="medium",
        choices=["high", "medium", "low"],
        help="lowest severity to report (default: medium)",
    )
    parser.add_argument(
        "--include-test",
        action="store_true",
        help="scan test files too (stubs are sometimes legit in tests)",
    )
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="scan noise dirs (.git, __pycache__, venvs — skipped by default)",
    )
    args = parser.parse_args(argv)

    floor = {"high": 0, "medium": 1, "low": 2}[args.min_severity]
    found = [
        f
        for f in scan_paths(args.paths, args.hidden, args.include_test)
        if _keep(f, floor)
    ]
    found.sort(key=lambda f: (f.file, f.line, f.col))

    if args.json:
        print(json.dumps([f.__dict__ for f in found], indent=2))
    elif found:
        print(_emit_table(found))
        print(f"\n{len(found)} no-op stub function(s) that return None.")
    else:
        print("Clean: no silent no-op stub functions found.")
    return 1 if (args.check and found) else 0


if __name__ == "__main__":
    sys.exit(main())
