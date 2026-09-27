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

## The harness — `harness.py`

`PTCHarness` is a `verifiers.v1.harness.Harness`. It runs its loop **in-process**, which
`Harness.launch`'s own contract permits verbatim: *"a harness may run its loop in-process
instead of launching a program, as long as every model call goes through `endpoint` +
`secret`"*. So there is no program to install and `NEEDS_CONTAINER = False`.

The model gets **exactly one tool**, `run_program(code)`. The catalog lives *inside* the
program, not beside it as sibling tools — that is the whole distinction between PTC and
plain typed-tool calling, and it is the axis this project measures. A test pins it, because
an arm that also exposed the catalog as tools would be the bash arm with different names
and the comparison would measure nothing.

Two decisions worth naming:

- **A rejection is data, not an error.** An escape comes back as a tool message the model
  can read (`rejected: import is not permitted`) and the loop continues. A crash would make
  the restriction a bug rather than part of the interface, and a model being trained could
  never learn the boundary.
- **`ctx.sampling` is not forwarded.** The interception server applies temperature/top_p/
  max_tokens as overrides onto whatever body a harness sends
  (`verifiers/v1/interception/server.py:596`), so sending them here would be dead at best
  and a silent divergence between arms at worst. Pinned by a test.

### It is a loadable plugin, not a fork

`--env.<role>.harness.id ptc` is all it takes. `verifiers` resolves a harness id by
importing that module and taking the single `Harness` subclass in its `__all__`
(`utils/loaders.py:145` → `_import_plugin` → `_plugin_class`), so a third-party arm needs
no fork, no entry point, and none of the private-name monkeypatching the spike ruled out
(`docs/spike-verifiers.md`, "The seam that was demonstrated is NOT the seam to build on").
`ptc/__init__.py` is the whole contract; a test loads the arm through
`load_harness(PTCHarnessConfig(id="ptc"))` rather than trusting that reading.

`PTCHarness` is exported **lazily**, via PEP 562's module `__getattr__`, so that
`runtime.py` stays importable on an interpreter with no `verifiers`: an eager harness
import in `__init__.py` would make `import ptc.runtime` require httpx, pydantic and
verifiers to reach a module that uses none of them. `_plugin_class` goes through
`getattr`, so the contract is unaffected. Both halves are pinned, and the eager-import
mutation goes red.

### Running the suites

`ptc/` needs an interpreter with `verifiers` installed; `.venv-tok` does not have it.
`test_ptc.py` runs anywhere (runtime only, no imports beyond stdlib), and `test_harness.py`
skips itself when `verifiers` is absent rather than failing.

    <python-with-verifiers> -m pytest ptc/ -q          # 46 tests
    python3 -m pytest ptc/ -q                          # 23 + 1 skipped, no verifiers needed
    <python-with-verifiers> ptc/mutate.py harness.py <<'JSON'
    [["name", "old", "new"], ...]
    JSON

`mutate.py` takes its interpreter from `sys.executable` instead of hardcoding a venv, so a
committed script never points at a path under `~/scratch`.

### The harness suite is mutation-tested too, and it found two real holes

23 tests. Twenty-five mutations, **zero survivors** — but only after two survivors were
fixed, which is the part worth recording:

| Mutation | Result |
|---|---|
| Rejection re-raised instead of returned as data | **6 tests fail** |
| Program `exec`'d directly, skipping `validate()` | **6 tests fail** |
| Catalog also exposed as sibling tools | 1 test fails |
| `ctx.sampling` forwarded in the request body | 1 test fails |
| `max_turns` unbounded (`while True`) | 1 test fails |
| `max_turns` off by one | 1 test fails |
| Catalog back to a class attribute (the real pre-fix shape) | **19 tests fail** |
| Only the first tool call in a turn is run | **10 tests fail** |
| System prompt elides the catalog names | 2 tests fail |
| Task's own system prompt dropped | 1 test fails |
| Tool exception swallowed as `ok` | 1 test fails |
| Bearer secret dropped from the request | 1 test fails |
| Rejection never appended to the message list | 1 test fails |
| `tool` message mislabelled `user` | 2 tests fail |
| **`tool_call_id` not echoed back** | **SURVIVED** → fixed |
| **Assistant turn not appended to history** | **SURVIVED** → fixed |
| `__all__` omits the harness / exports a second one / re-exports nothing | 2 tests fail each |
| Eager `ptc.harness` import in `__init__.py` | 1 test fails |
| `__getattr__` never resolves, or resolves to `None` | 2 tests fail each |

Both survivors were the same class of defect: the conversation the harness replays was
malformed in a way `httpx.MockTransport` accepts and a **real** OpenAI-compatible endpoint
rejects — a `tool` message answering no preceding `tool_calls` is a 400. Every other test
stayed green, so the arm would have failed only on first contact with a live model.
`test_the_replayed_conversation_is_a_valid_tool_exchange` now asserts the message sequence
and the id echo, and kills both.

One equivalent mutant is also recorded, since a table of only-kills invites suspicion:
setting `PTCHarness.catalog` *alongside* `self.catalog` survives, because the instance
attribute shadows it and behaviour is unchanged. That mutation is not the bug; the
class-attribute row above is.

## Status

Runtime, harness and suites are done and green: **46 tests, 25 mutants, 0 survivors.**
The arm loads through the supported plugin path and is drivable by anything that can play
a `verifiers` policy.

**Not yet run against a model.** The next step is the untrained bash-vs-PTC comparison —
the premise check that decides whether the project has a thesis.
