# `ptc/` — the restricted runtime for the PTC arm

**Why this exists:** `docs/spike-verifiers.md` established by execution that the obvious
PTC candidate, the `rlm` harness with `builtin_tools=["ipython"]`, is not the interface
arXiv 2609.11999 measured. Three different escapes each scored reward **1.0** against it:
`await rlm.shell.run(...)`, raw `import subprocess`, and a plain `open(...).write(...)`.
Deleting `rlm.shell` would not have helped — any full Python kernel keeps `subprocess`.

The paper's PTC is Python *plus* a restriction (§3, verbatim): the catalog exposed
"as ordinary functions **within a restricted runtime that provides no shell or other
action channel**". The restriction is the interface. This directory is that restriction.

## What it is

`runtime.py`, ~130 lines. `validate()` walks the AST and rejects anything outside an
allowlist; `run()` validates first, then executes with the catalog as the only names and
`__builtins__` replaced wholesale.

The load-bearing rule is that **attribute access is refused outright**. Every classic
CPython sandbox escape is an attribute walk — `().__class__.__bases__[0].__subclasses__()`,
`f.__globals__`, `x.__getattribute__`. A typed catalog needs no attribute access, because
tools are plain functions, so the blunt rule costs the interface nothing.

Validation strictly precedes execution, so a part-valid program does not half-run.

## What it is not

**Not a security boundary yet.** A static allowlist is necessary and not sufficient
against an adversary who chooses the program text. Before this runs output from a model
being *rewarded* for score — i.e. before Step 6 — it needs an OS-level backstop beneath
it: a container with no shell binaries and seccomp refusing `execve`/`fork`. The ceiling
is stated in `runtime.py`'s docstring so it cannot be forgotten by someone reading only
the code.

## The suite is adversarial, and it has been seen to fail

`test_ptc.py`, 23 tests. Ten reject escapes, seven confirm the arm still *works*
(composition, loops, comprehensions, f-strings, function defs — PTC's whole point is
chaining catalog calls, so a runtime permitting only a single call would be a different
and weaker interface), and the rest pin absences and behaviour.

Mutation-tested, because a guard that has never gone red is not evidence:

| Mutation | Result |
|---|---|
| Allow `ast.Import` / `ast.ImportFrom` | **2 tests fail** |
| Add `open` + `getattr` to `SAFE_BUILTINS` | **3 tests fail** |
| Disable the attribute guard | **1 test fails** |
| Allow `ast.Attribute` **and** disable the guard | **2 tests fail** |
| Allow `ast.Attribute` alone | survives — **equivalent mutant**: the dedicated guard runs before the node-list check, so the mutation changes no behaviour. Verified, not assumed. |

Under the combined mutation the dunder walk **executes and reaches 270 live subclasses**.
That is why the escape tests assert on outcomes (`run()` raises, catalog never reached)
and not only on error messages, which a refactor could reword.

## Acceptance criterion for any future PTC runtime

All three measured escapes go red while the catalog path stays green. Written before the
runtime existed, which is the only ordering under which it counts as evidence.

## Status

The runtime and its suite are done and green. **Not yet wired to a `verifiers` `Harness`** —
that is the next step, and it is what turns this into a usable second arm.
