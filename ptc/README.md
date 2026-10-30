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

## Resource bounds — the review's one finding, patched

An independent review (`docs/ptc-runtime-review.md`) threw **28 escape attempts, 0
escapes**, and found the real gap elsewhere: **4 resource attacks, 4 unbounded.** Each
validated cleanly and then never returned.

That matters more than it sounds. Once Step 6 rewards the model, **a hang is the
cheapest accidental reward hack available** — an episode that never completes never
scores zero either. A crash is honest; a hang is a slow leak in the reward signal.

Two mechanisms, because one cannot cover both shapes:

| Attack | Caught by | Why not the other one |
|---|---|---|
| `while True: pass` | Wall-clock tracer (`TIMEOUT`, 5s) | Trip count is a runtime property; no static bound can see it |
| nested `range` loops | Wall-clock tracer | Same |
| `10 ** 10 ** 8` | Static bound (`MAX_DIGITS`) | It is **one opcode** — a line tracer never regains control inside it |
| `[0] * 10 ** 9` | Static bound (`MAX_ELEMENTS`) | Same |

Both surface as `ProgramRejected`, which is the point: the harness hands a rejection
back as a tool message, so a model that wrote an unbounded loop is *told so* and can
retry. The limit is checked **before** the exponentiation, never after — computing the
value in order to measure it is the same hang moved into the validator, and a test
asserts the rejection takes under a second.

Ordering is deliberate: the magnitude check runs **last**, so a program that is both
illegal and huge reports the escape it attempted rather than an arithmetic limit it
also happens to break. The tracer is **restored**, not cleared, because pytest and
coverage install tracers of their own.

### The bounds are mutation-tested, and the first pass was a bad kill

Every guard above goes red when removed — but the first run killed four of them only
by the mutation harness's **300-second suite timeout**, reporting `timeout` instead of
naming a test. That is a bad kill, and the cause was in the tests:

    started = time.monotonic()
    with pytest.raises(ProgramRejected): run("record(10 ** 10 ** 8)", catalog())
    assert time.monotonic() - started < 1.0      # unreachable

If the guard is gone, `run()` never returns, so the timing assertion never runs. A test
that can only fail by hanging costs five minutes to say nothing useful.

**The second attempt was also wrong, and it looked right.** A daemon thread with
`join(limit)` cannot bound this either: `10 ** 10 ** 8` is a single C-level opcode that
never releases the GIL, so the main thread never gets to run its own `join` timeout and
the whole process stalls. Measured, not reasoned about — a probe printed *nothing at all*
in 25 seconds. That is the same single-opcode property that made a line tracer useless
one layer up, and it caught me twice.

`_rejected_within` runs the program in a **child interpreter**. It has its own GIL and the
parent's wait is enforced by the OS rather than by Python scheduling, so a missing guard
fails by name in seconds regardless of what the program does.

That relocation created a vacuous test, which is worth recording because it is the
failure mode this project keeps hitting: `test_the_bomb_check_runs_at_validation` asserted
`WROTE == []`, but with the program in a child process the parent's list is empty
*whatever happens*. It now asserts on a call count the child reports back, and the fix was
verified by a faithful mutant — validating and executing statement by statement, so the
first statement genuinely runs — which turns the assertion red with `CALLS:1`.

| Mutation | Result |
|---|---|
| Deadline never expires | suite hangs → killed |
| Magnitude check removed | `test_an_integer_bomb_is_refused_before_it_runs` |
| `Pow` limit computes the value before measuring it | same test — measuring by computing is the same hang, relocated |
| Element limit dropped | `test_a_sequence_bomb_is_refused_before_it_runs` |
| Magnitude check moved before the node allowlist | `test_a_forbidden_node_is_reported_as_such…` |
| Tracer cleared instead of restored | `test_an_existing_tracer_is_restored_not_stomped` |

The mutation harness needed two fixes of its own to run this honestly, both for the same
class of bug the review found in the runtime: it now kills a suite that overruns, and it
kills the whole **process tree**, because `pkill` on the parent once left four `pytest`
children spinning at 98% CPU — one of them 511 CPU-minutes in. A harness that enforces
an execution bound must obey one.

**The residual hole, stated rather than hidden.** A *computed* bomb — `n = 10 ** 8`
then `10 ** n` — still gets through, because bounding that needs abstract
interpretation of the whole program. The real fix is the OS: a child process under
`RLIMIT_AS` and `RLIMIT_CPU` bounds every shape at once. That is the same piece of work
as the container-and-seccomp backstop `runtime.py`'s docstring already requires before
Step 6, not a second one.

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

### The catalog comes from the task's MCP servers

`SUPPORTS_MCP = True`. At launch the harness asks the task's MCP servers what they offer
(`connect_mcp`, the same helper the bundled chat program uses) and turns each tool into an
ordinary **synchronous** catalog function. Synchronous because that is what the paper's PTC
exposes and what `runtime.validate` permits — `await` is not in `ALLOWED_NODES`, and adding
it would change the interface under measurement.

That forces a bridge: MCP is async, the program is not. The program runs in a worker thread
(`asyncio.to_thread`) and each tool call hops back to the harness's loop via
`run_coroutine_threadsafe`. Running the program on the loop instead deadlocks on the first
tool call, so the MCP tests use a short `tool_timeout` — otherwise that mutation reads as a
hang rather than a failure.

Tool names that are not Python identifiers (a hyphenated server yields `my-tools_lookup`)
are unreachable to a program that calls tools by name. They are reported in the log rather
than dropped, because a task whose only tool is unreachable would otherwise read as a model
failure.

### `print` is the observation channel

A program that calls a tool and does not print tells the model nothing, so the harness
returns **the program's printed output** as the tool result — not a list of bound names.
`print` is in `SAFE_BUILTINS` already, but its output would go to the harness process's
stdout; a catalog entry named `print` shadows the builtin (`run()` execs with the catalog
as globals) and captures instead. Chosen over `contextlib.redirect_stdout`, which mutates
`sys.stdout` process-wide while programs run in worker threads: two concurrent rollouts
would capture each other's output. A program that prints nothing is told so explicitly,
because a bare `ok` reads as "the tool worked".

### Proof it can score: a real MCP server, not a mock

`test_harness.py` stands up the real `glossary` toolset (`verifiers.v1.mcp.serve`, the
same path a rollout uses — one subprocess per server) and drives a program that calls
`facts_lookup` and prints the result. The assertion is that the fact reaches **the model**,
which is the only reason the arm can earn `glossary`'s reward: that reward is 1.0 only if
the looked-up fact appears in the final reply. The negative control — a program that
answers without calling the tool — is asserted not to contain it.

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

    <python-with-verifiers> -m pytest ptc/ -q          # 53 tests
    python3 -m pytest ptc/ -q                          # 23 + 1 skipped, no verifiers needed
    <python-with-verifiers> ptc/mutate.py ptc/harness.py <<'JSON'
    [["name", "old", "new"], ...]
    JSON

`mutate.py` takes its interpreter from `sys.executable` instead of hardcoding a venv, so a
committed script never points at a path under `~/scratch`.

### The harness suite is mutation-tested too, and it found two real holes

29 tests. Thirty-one mutations, **zero survivors** — but only after two survivors were
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
| `print` not shadowed, so output goes to the real stdout | 3 tests fail |
| Captured output never cleared between programs | 1 test fails |
| Program run on the event loop instead of a thread (deadlock) | 1 test fails |
| MCP servers never consulted | 1 test fails |
| Non-identifier tool names kept in the catalog | 1 test fails |
| Silent program reported as a plain `ok` | 1 test fails |

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

Runtime, harness and suites are done and green: **52 tests, 31 mutants, 0 survivors.**
The arm loads through the supported plugin path, builds its catalog from the task's MCP
servers, and has been driven end to end against a real `glossary` tool server.

### The comparison rig

`ptc/compare.py` runs bash and PTC over the same taskset with the same model.

    python ptc/compare.py canned                                  # free, no model
    python ptc/compare.py real --model <id> --base-url <url>      # any OpenAI-compatible endpoint

**canned** measures nothing about models. It proves the *rig* can tell the arms apart.
Four checks, each able to fail:

1. **the control scores exactly 0.0** — nothing is answerable without the tool, which is
   the anti-cheat property both tasksets were chosen for;
2. **the tool arms score above zero** — the catalog is reachable at all;
3. **the two arms score identically** — the same scripted intent through two channels
   must land in the same place, so a gap here is the *rig* favouring an arm rather than
   a finding about arms;
4. **nothing truncated** — see the turn budget below.

Not "both arms reach 1.0". The canned policy solves only the one-call tier on purpose —
a scripted policy that solved the aggregation tier would be measuring the script — so on
the full `ledger` suite it scores 4/14 by design, and demanding 1.0 made the rig report
FAIL on a healthy run. That is the same fail-closed defect this project already found
once inside `step2/verdict.py`, reintroduced in a different file.

### The turn budget must not bind, or it *is* the independent variable

`max_turns` was 4. `ledger`'s aggregation tier needs 40 tool calls: the PTC arm spends
**one program** on that, the bash arm spends **~42 turns**. So bash was capped at turn 4
and scored 0.0 across the whole tier — the tier built specifically to be where PTC could
win. `session.py:98` stops with `stop_condition="max_turns"`, and that 0.0 is
indistinguishable from incapacity, so the rig would have manufactured a clean-looking
PTC victory on 6 of 14 tasks out of a number chosen by the author.

The budget is now 80 and a flag. Any rollout stopped by a framework limit — turns, input
tokens, output tokens, failed compaction — is counted and announced rather than averaged
into a mean:

    *** A BUDGET LIMIT BOUND: bash 6. Those rollouts scored 0.0 for running out of
        turns or tokens, not for failing the task. The score comparison is INVALID
        until the budget is raised.

**real** points `EvalClientConfig.base_url` at a provider. That is the seam
`Harness.launch` names and the one the spike says to build on, rather than the
`resolve_client` monkeypatch — which rebinds a name inside another module's namespace
and breaks silently if upstream inlines the call. Canned mode still uses the
monkeypatch, on purpose: it is scaffolding for a policy that is not a server.

Running it found a defect 52 green tests had not: the interception endpoint already
ends in `/v1`, so the harness was requesting `/v1/v1/chat/completions` and getting a
404 on every real rollout. `MockTransport` answers any path, so no mock could have
caught it. Both endpoint shapes are now pinned by a test.

**Not yet run against a model.** That is the untrained bash-vs-PTC measurement — the
premise check that decides whether the project has a thesis
(`docs/pre-registration.md` §6).
