"""ai-checkkit unified CLI — dispatches to stubcheck/assertcheck/shadowcheck/mutablecheck."""

import argparse
import json
import sys
from pathlib import Path

from ai_checkkit import stubcheck as sc_stub
from ai_checkkit import assertcheck as sc_assert
from ai_checkkit import shadowcheck as sc_shadow
from ai_checkkit import mutablecheck as sc_mutable


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories to scan")
    parser.add_argument("--check", action="store_true", help="exit 1 if any findings")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--hidden", action="store_true", help="scan hidden/noise dirs")


def _stubcheck_args(p: argparse.ArgumentParser) -> None:
    _add_common(p)
    p.add_argument("--min-severity", default="medium", choices=["high", "medium", "low"])
    p.add_argument("--include-test", action="store_true", help="include test files")


def _assertcheck_args(p: argparse.ArgumentParser) -> None:
    _add_common(p)
    p.add_argument("--min-severity", default="medium", choices=["high", "medium", "low"])
    p.add_argument("--include-test", action="store_true")


def _shadowcheck_args(p: argparse.ArgumentParser) -> None:
    _add_common(p)
    p.add_argument("--allow", default="", help="comma-separated names to allow")


def _mutablecheck_args(p: argparse.ArgumentParser) -> None:
    _add_common(p)
    p.add_argument("--allow", default="", help="comma-separated function names to allow")


def _all_args(p: argparse.ArgumentParser) -> None:
    _add_common(p)
    p.add_argument("--include-test", action="store_true")
    p.add_argument("--allow-shadow", default="", help="allow list for shadowcheck")
    p.add_argument("--allow-mutable", default="", help="allow list for mutablecheck")


def _run_stub(args) -> tuple[list, int]:
    floor = {"high": 0, "medium": 1, "low": 2}[args.min_severity]
    found = [f for f in sc_stub.scan_paths(args.paths, args.hidden, args.include_test) if sc_stub.SEV[f.kind] <= floor]
    found.sort(key=lambda f: (f.file, f.line, f.col))
    return found, 1 if (args.check and found) else 0


def _run_assert(args) -> tuple[list, int]:
    floor = {"high": 0, "medium": 1, "low": 2}[args.min_severity]
    found = [f for f in sc_assert.scan_paths(args.paths, args.hidden, args.include_test) if sc_assert.SEV[f.kind] <= floor]
    found.sort(key=lambda f: (f.file, f.line, f.col))
    return found, 1 if (args.check and found) else 0


def _run_shadow(args) -> tuple[list, int]:
    allow = set(s.strip() for s in args.allow.split(",") if s.strip()) if args.allow else set()
    found = sc_shadow.scan_paths(args.paths, allow, args.hidden)
    found.sort(key=lambda f: (f.file, f.line, f.col))
    return found, 1 if (args.check and found) else 0


def _run_mutable(args) -> tuple[list, int]:
    allow = set(s.strip() for s in args.allow.split(",") if s.strip()) if args.allow else set()
    found = sc_mutable.scan_paths(args.paths, allow, args.hidden)
    found.sort(key=lambda f: (f.file, f.line, f.col))
    return found, 1 if (args.check and found) else 0


def _run_all(args) -> tuple[dict, int]:
    allow_shadow = set(s.strip() for s in args.allow_shadow.split(",") if s.strip()) if args.allow_shadow else set()
    allow_mutable = set(s.strip() for s in args.allow_mutable.split(",") if s.strip()) if args.allow_mutable else set()
    s_found = [f for f in sc_stub.scan_paths(args.paths, args.hidden, args.include_test)]
    a_found = [f for f in sc_assert.scan_paths(args.paths, args.hidden, args.include_test)]
    sh_found = sc_shadow.scan_paths(args.paths, allow_shadow, args.hidden) if hasattr(sc_shadow, "scan_paths") else _shadow_scan(args.paths, allow_shadow, args.hidden)
    m_found = sc_mutable.scan_paths(args.paths, allow_mutable, args.hidden)
    all_found = {"stubcheck": s_found, "assertcheck": a_found, "shadowcheck": sh_found, "mutablecheck": m_found}
    code = 1 if (args.check and any(all_found.values())) else 0
    return all_found, code


def _print_findings(name: str, found: list, args) -> None:
    if args.json:
        print(json.dumps([f.__dict__ for f in found], indent=2))
    elif found:
        # use module's emit if available
        emit = None
        mod = {"stubcheck": sc_stub, "assertcheck": sc_assert, "shadowcheck": sc_shadow, "mutablecheck": sc_mutable}.get(name)
        if mod and hasattr(mod, "_emit_table"):
            print(mod._emit_table(found))
        else:
            for f in found:
                print(f"{f.file}:{f.line}:{f.col} → {f}")
        print(f"\n{len(found)} {name} finding(s).")
    else:
        print(f"Clean: no {name} findings.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-checkkit", description="AI-era Python lint bundle: stubcheck + assertcheck + shadowcheck + mutablecheck")
    sub = parser.add_subparsers(dest="command")

    p_stub = sub.add_parser("stubcheck", help="silent no-op stubs")
    _stubcheck_args(p_stub)
    p_stub.set_defaults(func=lambda a: _dispatch_single("stubcheck", a))

    p_assert = sub.add_parser("assertcheck", help="vanishing asserts")
    _assertcheck_args(p_assert)
    p_assert.set_defaults(func=lambda a: _dispatch_single("assertcheck", a))

    p_shadow = sub.add_parser("shadowcheck", help="builtin shadowing")
    _shadowcheck_args(p_shadow)
    p_shadow.set_defaults(func=lambda a: _dispatch_single("shadowcheck", a))

    p_mut = sub.add_parser("mutablecheck", help="mutable defaults")
    _mutablecheck_args(p_mut)
    p_mut.set_defaults(func=lambda a: _dispatch_single("mutablecheck", a))

    p_all = sub.add_parser("all", help="run all 4 checks")
    _all_args(p_all)
    p_all.set_defaults(func=_dispatch_all)

    # default to 'all' when no subcommand given
    parser.set_defaults(func=_dispatch_all_default)
    return parser


def _dispatch_single(name: str, args) -> int:
    runners = {"stubcheck": _run_stub, "assertcheck": _run_assert, "shadowcheck": _run_shadow, "mutablecheck": _run_mutable}
    found, code = runners[name](args)
    _print_findings(name, found, args)
    return code


def _dispatch_all(args) -> int:
    found_map, code = _run_all(args)
    if args.json:
        print(json.dumps({k: [f.__dict__ for f in v] for k, v in found_map.items()}, indent=2))
    else:
        for name, found in found_map.items():
            print(f"\n=== {name} ===")
            _print_findings(name, found, args)
        total = sum(len(v) for v in found_map.values())
        print(f"\nTotal: {total} finding(s) across 4 checks.")
    return code


def _dispatch_all_default(args) -> int:
    # when no subcommand, treat as 'all' with defaults
    if not hasattr(args, "paths"):
        args.paths = ["."]
        args.hidden = False
        args.include_test = False
        args.allow_shadow = ""
        args.allow_mutable = ""
        args.check = False
        args.json = False
    elif not hasattr(args, "allow_shadow"):
        # called via 'all' alias with missing fields -> fill
        for k, v in [("allow_shadow", ""), ("allow_mutable", ""), ("include_test", False)]:
            if not hasattr(args, k):
                setattr(args, k, v)
    # ensure required attrs
    if not hasattr(args, "allow_shadow"):
        args.allow_shadow = ""
    if not hasattr(args, "allow_mutable"):
        args.allow_mutable = ""
    if not hasattr(args, "include_test"):
        args.include_test = False
    return _dispatch_all(args)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # handle case where first arg is not a subcommand but a path -> route to all
    if args.command is None and args.paths and args.paths[0] not in ("stubcheck", "assertcheck", "shadowcheck", "mutablecheck", "all"):
        # check if user passed flags without subcommand, ensure all dispatch
        return _dispatch_all_default(args)
    return args.func(args)


# Backward-compat entry points
def stubcheck_main(argv=None) -> int:
    import sys as _sys
    if argv is None:
        argv = _sys.argv[1:]
    # if called as stubcheck without subcommand, parse as stubcheck args
    p = argparse.ArgumentParser(prog="stubcheck")
    _stubcheck_args(p)
    a = p.parse_args(argv if argv and argv[0] not in ("--help", "-h") else argv)
    # inject dummy command for dispatcher
    found, code = _run_stub(a)
    _print_findings("stubcheck", found, a)
    return code


def assertcheck_main(argv=None) -> int:
    import sys as _sys
    if argv is None:
        argv = _sys.argv[1:]
    p = argparse.ArgumentParser(prog="assertcheck")
    _assertcheck_args(p)
    a = p.parse_args(argv)
    found, code = _run_assert(a)
    _print_findings("assertcheck", found, a)
    return code


def shadowcheck_main(argv=None) -> int:
    import sys as _sys
    if argv is None:
        argv = _sys.argv[1:]
    p = argparse.ArgumentParser(prog="shadowcheck")
    _shadowcheck_args(p)
    a = p.parse_args(argv)
    found, code = _run_shadow(a)
    _print_findings("shadowcheck", found, a)
    return code


def mutablecheck_main(argv=None) -> int:
    import sys as _sys
    if argv is None:
        argv = _sys.argv[1:]
    p = argparse.ArgumentParser(prog="mutablecheck")
    _mutablecheck_args(p)
    a = p.parse_args(argv)
    found, code = _run_mutable(a)
    _print_findings("mutablecheck", found, a)
    return code
