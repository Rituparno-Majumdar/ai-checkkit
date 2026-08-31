"""mutablecheck — detect mutable default arguments (the classic aliasing footgun)."""

import argparse
import ast
import json
import os
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

MUTABLE_KINDS = {
    "List": "list literal",
    "Dict": "dict literal",
    "Set": "set literal",
    "Call:list": "list() call",
    "Call:dict": "dict() call",
    "Call:set": "set() call",
    "Call:bytearray": "bytearray() call",
    "Call:defaultdict": "defaultdict() call",
}

MUTABLE_CALLS = {"list", "dict", "set", "bytearray", "defaultdict"}


@dataclass
class Finding:
    file: str
    line: int
    col: int
    func: str
    arg: str
    kind: str


def _default_kind(node: ast.AST) -> str | None:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return MUTABLE_KINDS[type(node).__name__]
    if isinstance(node, ast.Call):
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in MUTABLE_CALLS:
            return MUTABLE_KINDS[f"Call:{name}"]
    return None


def detect(source: str, path: str, allow: set[str]) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[Finding] = []
    for fnode in ast.walk(tree):
        if not isinstance(fnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fnode.name in allow:
            continue
        args = fnode.args
        defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
        for an, d in zip(args.args, defaults):
            kind = _default_kind(d) if d is not None else None
            if kind:
                found.append(
                    Finding(path, d.lineno, d.col_offset + 1, fnode.name, an.arg, kind)
                )
        for an, d in zip(args.kwonlyargs, args.kw_defaults):
            if d is None:
                continue
            kind = _default_kind(d)
            if kind:
                found.append(
                    Finding(path, d.lineno, d.col_offset + 1, fnode.name, an.arg, kind)
                )
    return found


def scan_paths(paths: list[str], allow: set[str], hidden: bool) -> list[Finding]:
    found: list[Finding] = []
    for p in paths:
        root = Path(p)
        if root.is_file():
            if root.suffix == ".py":
                found.extend(
                    detect(
                        root.read_text(encoding="utf-8", errors="replace"),
                        str(root),
                        allow,
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
                            allow,
                        )
                    )
    return found


def _emit_table(found: list[Finding]) -> str:
    lines = ["file:line:col → func: arg (kind)"]
    for f in found:
        lines.append(f"{f.file}:{f.line}:{f.col} → {f.func}: {f.arg} ({f.kind})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutablecheck",
        description="Detect mutable default arguments in Python functions (the aliasing footgun).",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], help="files or directories to scan"
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if any findings")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument(
        "--allow", default="", help="comma-separated function names to skip"
    )
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="ignore noise dirs (__.pycache__, .git, etc.)",
    )
    args = parser.parse_args(argv)

    allow = {s.strip() for s in args.allow.split(",") if s.strip()}
    found = scan_paths(args.paths, allow, args.hidden)
    found.sort(key=lambda f: (f.file, f.line, f.col))

    if args.json:
        print(json.dumps([f.__dict__ for f in found], indent=2))
    else:
        if found:
            print(_emit_table(found))
            print(f"\n{len(found)} mutable default argument(s) found.")
        else:
            print("Clean: no mutable default arguments found.")
    return 1 if (args.check and found) else 0


if __name__ == "__main__":
    sys.exit(main())
