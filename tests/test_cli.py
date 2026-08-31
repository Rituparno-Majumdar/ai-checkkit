import pathlib
import tempfile
import textwrap

import ai_checkkit.stubcheck as sc_stub
import ai_checkkit.assertcheck as sc_assert
import ai_checkkit.shadowcheck as sc_shadow
import ai_checkkit.mutablecheck as sc_mut
from ai_checkkit.cli import main as cli_main


def _tmp_file(code: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    f.write(textwrap.dedent(code))
    f.flush()
    return f.name


def test_stubcheck_detects_bare_stub():
    code = "def foo():\n    pass\n"
    found = sc_stub.detect(code, "x.py")
    assert len(found) == 1 and found[0].kind == "bare"


def test_stubcheck_detects_docstring_stub():
    code = 'def foo():\n    """todo"""\n    pass\n'
    found = sc_stub.detect(code, "x.py")
    assert found[0].kind == "docstring"


def test_assertcheck_detects_bare():
    code = "def f(x):\n    assert x\n"
    found = sc_assert.detect(code, "x.py")
    assert found[0].kind == "bare"


def test_assertcheck_detects_msg():
    code = 'def f(x):\n    assert x, "bad"\n'
    found = sc_assert.detect(code, "x.py")
    assert found[0].kind == "msg"


def test_shadowcheck_detects_builtin():
    code = "def foo(list):\n    pass\n"
    found = sc_shadow.detect(code, "x.py", set())
    assert any(f.name == "list" for f in found)


def test_shadowcheck_allow():
    code = "def foo(list):\n    pass\n"
    found = sc_shadow.detect(code, "x.py", {"list"})
    assert found == []


def test_mutablecheck_detects_list():
    code = "def foo(x=[]):\n    pass\n"
    found = sc_mut.detect(code, "x.py", set())
    assert len(found) == 1 and found[0].arg == "x"


def test_mutablecheck_allow():
    code = "def foo(x=[]):\n    pass\n"
    found = sc_mut.detect(code, "x.py", {"foo"})
    assert found == []


def test_cli_all_runs(tmp_path: pathlib.Path = None):
    # create temp dir with one file triggering each linter
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "a.py")
    open(p, "w").write("def foo():\n    pass\n\ndef bar(x=[]):\n    pass\n\ndef baz(list):\n    pass\n\ndef qux(v):\n    assert v\n")
    # should not crash
    rc = cli_main(["all", d])
    assert rc == 0
    rc2 = cli_main(["all", d, "--check"])
    assert rc2 == 1


def test_cli_help():
    try:
        cli_main(["--help"])
    except SystemExit as e:
        assert e.code == 0
