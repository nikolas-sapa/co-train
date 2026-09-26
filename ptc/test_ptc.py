"""Acceptance suite for the restricted PTC runtime.

The three escapes in `docs/spike-verifiers.md` each scored reward 1.0 against the `rlm`
harness -- `rlm.shell.run`, raw `subprocess`, and a direct file write. Every one of them
must be REJECTED here while the catalog path still works. That asymmetry is the whole
definition of the PTC arm.

Written against a runtime that did not exist when the escapes were found, which is the
only ordering under which this counts as evidence rather than decoration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from runtime import SAFE_BUILTINS, Catalog, ProgramRejected, run, validate  # noqa: E402

# ---------------------------------------------------------------- the catalog

WROTE: list[str] = []


def write_answer(value: str) -> str:
    """The one legitimate action. Stands in for a real typed tool."""
    WROTE.append(value)
    return f"wrote {value}"


def catalog() -> Catalog:
    return Catalog(tools={"write_answer": write_answer})


@pytest.fixture(autouse=True)
def _clear():
    WROTE.clear()


# ---------------------------------------------------------------- the arm works

def test_catalog_path_works():
    """The green half. Without this the suite proves only that nothing runs."""
    ns = run("write_answer(str(2 + 3))", catalog())
    assert WROTE == ["5"]
    assert "write_answer" in ns


def test_composition_works():
    """PTC's whole point is chaining and looping over catalog calls, so a runtime that
    only permits a single call would be a different, weaker interface."""
    run(
        "total = 0\n"
        "for n in range(5):\n"
        "    total = total + n\n"
        "write_answer(str(total))",
        catalog(),
    )
    assert WROTE == ["10"]


def test_comprehension_and_fstring_work():
    run("write_answer(f\"{sum([n * n for n in range(4)])}\")", catalog())
    assert WROTE == ["14"]


def test_function_def_works():
    run("def double(x):\n    return x * 2\nwrite_answer(str(double(21)))", catalog())
    assert WROTE == ["42"]


# ------------------------------------------------- the three measured escapes

def test_escape_import_subprocess_rejected():
    """Mode `subprocess` from the spike: scored 1.0 against rlm."""
    with pytest.raises(ProgramRejected, match="Import"):
        validate("import subprocess\nsubprocess.run('ls', shell=True)", catalog())
    assert WROTE == []


def test_escape_from_import_rejected():
    with pytest.raises(ProgramRejected, match="ImportFrom"):
        validate("from os import system\nsystem('ls')", catalog())


def test_escape_rlm_shell_rejected():
    """Mode `shell` from the spike: `await rlm.shell.run(...)`, scored 1.0 against rlm.

    Rejected twice over -- `await` is not an allowed node and `.shell` is an attribute --
    so assert only that it is refused, not on which rule fired first.
    """
    with pytest.raises(ProgramRejected):
        validate("job = await rlm.shell.run('echo hi')", catalog())


def test_escape_direct_file_write_rejected():
    """Mode `pure` from the spike: `open(...).write(...)` scored 1.0 against rlm. The
    catalog is the only action channel, so even the benign-looking one is refused."""
    with pytest.raises(ProgramRejected, match="unknown name 'open'"):
        validate("open('answer.txt', 'w')", catalog())


# ------------------------------------------------- escapes the spike did not try

def test_dunder_class_walk_rejected():
    """The classic CPython sandbox escape. Attribute access is refused outright, which is
    why this dies at `.__class__` rather than needing a bespoke rule."""
    with pytest.raises(ProgramRejected, match="attribute access"):
        validate("().__class__.__bases__[0].__subclasses__()", catalog())


def test_builtins_lookup_rejected():
    with pytest.raises(ProgramRejected, match="not permitted"):
        validate("__import__('os')", catalog())


def test_getattr_rejected():
    with pytest.raises(ProgramRejected, match="unknown name 'getattr'"):
        validate("getattr(write_answer, 'x')", catalog())


def test_eval_and_exec_rejected():
    for src in ("eval('1+1')", "exec('x=1')", "compile('1', 'f', 'eval')"):
        with pytest.raises(ProgramRejected, match="unknown name"):
            validate(src, catalog())


def test_globals_rejected():
    with pytest.raises(ProgramRejected, match="unknown name 'globals'"):
        validate("globals()", catalog())


def test_unknown_name_rejected():
    """The second validation pass. `subprocess` alone, with no import, is still unknown."""
    with pytest.raises(ProgramRejected, match="unknown name 'subprocess'"):
        validate("subprocess", catalog())


def test_lambda_rejected():
    """Lambda is absent from ALLOWED_NODES; it is a function body that the name-binding
    pass does not track, so permitting it would open a hole in the second pass."""
    with pytest.raises(ProgramRejected, match="Lambda is not permitted"):
        validate("f = lambda: 1", catalog())


def test_with_and_try_rejected():
    for src in ("with open('f') as f:\n    pass", "try:\n    pass\nexcept:\n    pass"):
        with pytest.raises(ProgramRejected, match="not permitted"):
            validate(src, catalog())


def test_syntax_error_is_rejection_not_crash():
    with pytest.raises(ProgramRejected, match="syntax error"):
        validate("write_answer(", catalog())


# ------------------------------------------------- the guards must be able to fail

def test_safe_builtins_omits_the_dangerous_ones():
    """A guard that has never gone red is not evidence. This pins the ABSENCES, so a
    future edit that helpfully adds `open` or `getattr` back breaks a test instead of
    silently widening the interface."""
    for name in (
        "open", "eval", "exec", "compile", "__import__", "getattr", "setattr",
        "globals", "locals", "vars", "dir", "input", "breakpoint", "help", "memoryview",
    ):
        assert name not in SAFE_BUILTINS, f"{name} must not be reachable"


def test_runtime_replaces_builtins_wholesale():
    """The belt behind the guard: even if validation were bypassed, the exec namespace
    has no real __builtins__ to reach."""
    ns = run("write_answer('x')", catalog())
    assert "__builtins__" not in ns


def test_catalog_is_the_only_injected_name():
    ns = run("write_answer('x')", catalog())
    assert set(ns) == {"write_answer"}


# ------------------------------------------------- behaviour, not error messages

def test_dunder_walk_does_not_execute():
    """The escape tests above assert on `validate`'s message, which a refactor could
    reword. This one asserts the OUTCOME: the program does not run and the catalog is
    never reached. Verified against a deliberately broken runtime -- with the attribute
    guard disabled AND `ast.Attribute` allowed, this exact program executes and reaches
    270 live subclasses, so the assertion has been seen to fail."""
    with pytest.raises(ProgramRejected):
        run("x = ().__class__.__bases__[0].__subclasses__()\nwrite_answer(str(len(x)))",
            catalog())
    assert WROTE == []


def test_subprocess_escape_does_not_execute():
    """Same, for the escape that scored 1.0 against rlm."""
    with pytest.raises(ProgramRejected):
        run("import subprocess\nsubprocess.run('touch pwned', shell=True)", catalog())
    assert WROTE == []


def test_rejected_program_never_reaches_the_catalog():
    """A program that is part-valid must not half-run: validation precedes execution,
    so the legitimate first call must NOT happen when a later line is illegal."""
    with pytest.raises(ProgramRejected):
        run("write_answer('first')\nimport os", catalog())
    assert WROTE == [], "validation must precede execution, not interleave with it"
