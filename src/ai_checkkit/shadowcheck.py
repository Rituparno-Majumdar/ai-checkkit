"""shadowcheck — detect identifiers that shadow Python builtins."""

import argparse
import ast
import builtins
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
BUILTINS = {n for n in dir(builtins) if not n.startswith("_")}


@dataclass
class Finding:
    file: str
    line: int
    col: int
    name: str
    kind: str


class ShadowScanner:
    def __init__(self, path: str, allow: set[str]):
        self.path = path
        self.allow = allow
        self.found: list[Finding] = []

    def _flag(self, node: ast.AST, name: str, kind: str) -> None:
        if name in BUILTINS and name not in self.allow:
            self.found.append(
                Finding(self.path, getattr(node, "lineno", 0), getattr(node, "col_offset", 0) + 1, name, kind)
            )

    def _names(self, node: ast.AST) -> list[tuple[ast.AST, str]]:
        if isinstance(node, ast.Name):
            return [(node, node.id)]
        if isinstance(node, (ast.Tuple, ast.List)):
            return [(n, name) for el in node.elts for n, name in self._names(el)]
        return []

    def _bind(self, targets: list, kind: str) -> None:
        for t in targets:
            for n, name in self._names(t):
                self._flag(n, name, kind)

    def _params(self, args: ast.arguments) -> None:
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            for p in group:
                self._flag(p, p.arg, "param")
        for v in (args.vararg, args.kwarg):
            if v is not None:
                self._flag(v, v.arg, "param")

    def visit(self, node: ast.AST) -> None:
        kind = type(node)
        if kind is ast.Assign:
            self._bind(node.targets, "assign")
        elif kind in (ast.AnnAssign, ast.AugAssign):
            self._bind([node.target], "assign")
        elif kind is ast.NamedExpr and isinstance(node.target, ast.Name):
            self._flag(node.target, node.target.id, "walrus")
        elif kind in (ast.For, ast.AsyncFor):
            self._bind([node.target], "loop")
        elif kind in (ast.With, ast.AsyncWith):
            self._bind([i.optional_vars for i in node.items if i.optional_vars], "with")
        elif kind is ast.ExceptHandler and node.name:
            self._flag(node, node.name, "exception")
        elif kind in (ast.FunctionDef, ast.AsyncFunctionDef):
            self._flag(node, node.name, "def")
            self._params(node.args)
        elif kind is ast.Lambda:
            self._params(node.args)
        elif kind is ast.ClassDef:
            self._flag(node, node.name, "class")
        elif kind is ast.Import:
            for a in node.names:
                self._flag(a, a.asname or a.name.split(".")[0], "import")
        elif kind is ast.ImportFrom:
            for a in node.names:
                if a.name != "*":
                    self._flag(a, a.asname or a.name, "import")
        elif kind in (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp):
            self._bind([g.target for g in node.generators], "comprehension")
        elif kind in (ast.MatchAs, ast.MatchStar):
            if node.name:
                self._flag(node, node.name, "pattern")
        elif kind is ast.MatchMapping and node.rest:
            self._flag(node, node.rest, "pattern")
        for child in ast.iter_child_nodes(node):
            self.visit(child)


def scan_python(path: Path, hidden: bool) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    files = []
    for root, dirs, names in os.walk(path):
        if not hidden:
            dirs[:] = [d for d in dirs if d not in NOISE]
        for name in names:
            if name.endswith(".py"):
                files.append(Path(root) / name)
    return sorted(files)


def parse_file(path: Path, allow: set[str]) -> tuple[list[Finding], str | None]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [], str(exc)
    scanner = ShadowScanner(str(path), allow)
    scanner.visit(tree)
    return scanner.found, None


def run(target: str, allow: set[str], hidden: bool) -> tuple[list[Finding], list[str]]:
    findings, errors = [], []
    for f in scan_python(Path(target), hidden):
        found, err = parse_file(f, allow)
        if err:
            errors.append(f"{f}: {err}")
        findings.extend(found)
    findings.sort(key=lambda x: (x.file, x.line, x.col))
    return findings, errors


def detect(source: str, path: str, allow: set[str]) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    scanner = ShadowScanner(path, allow)
    scanner.visit(tree)
    return scanner.found


def scan_paths(paths: list[str], allow: set[str], hidden: bool) -> list[Finding]:
    found: list[Finding] = []
    for p in paths:
        f, _ = run(p, allow, hidden)
        found.extend(f)
    found.sort(key=lambda x: (x.file, x.line, x.col))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shadowcheck", description="Detect identifiers that shadow Python builtins.")
    parser.add_argument("target", nargs="?", default=".", help="file or directory to scan (default: .)")
    parser.add_argument("--allow", default="", help="comma-separated builtin names tolerated (e.g. --allow id,type)")
    parser.add_argument("--check", action="store_true", help="exit 1 when any shadow is found")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    parser.add_argument("--hidden", action="store_true", help="do not prune noise dirs (__pycache__, .git, venv, ...)")
    args = parser.parse_args(argv)

    allow = {a.strip() for a in args.allow.split(",") if a.strip()}
    unknown = allow - BUILTINS
    if unknown:
        print(f"shadowcheck: --allow got non-builtin names: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    if not os.path.exists(args.target):
        print(f"shadowcheck: no such path: {args.target}", file=sys.stderr)
        return 2

    findings, errors = run(args.target, allow, args.hidden)

    for e in errors:
        print(f"[skip] {e}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                [{"file": f.file, "line": f.line, "col": f.col, "name": f.name, "kind": f.kind} for f in findings],
                indent=2,
            )
        )
    else:
        if findings:
            width = max(len(f.file) for f in findings)
            print(f"{'FILE':<{width}}  {'LINE':<5} {'COL':<4} {'NAME':<14} KIND")
            for f in findings:
                print(f"{f.file:<{width}}  {f.line:<5} {f.col:<4} {f.name:<14} {f.kind}")
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.name] = counts.get(f.name, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        summary = ", ".join(f"{k} x{v}" for k, v in ranked) if ranked else "clean"
        print(f"\n{len(findings)} shadowed builtin(s); top: {summary}")

    if args.check and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
