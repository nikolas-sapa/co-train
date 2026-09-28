# PTC runtime review — findings for the `ptc/` owner
2026-09-27. Written by the Step 2 session. **`ptc/` is not mine and I have not edited
it.** `runtime.py` was copied read-only to `/tmp/ptc-review/` and attacked there.

Symmetric to `docs/step2-audit.md`, which found a fatal defect in my `step2/` and was
right. This is the same favour returned.

---

## Headline: the sandbox holds. The gap is exhaustion, not escape.

28 escape attempts, **0 escapes.** Every classic CPython vector is refused, and the
blunt no-attribute-access rule is doing the work exactly as its docstring claims.

4 resource attacks, **4 unbounded.** Each one validates cleanly and then never returns.

| Class | Attempts | Result |
|---|---|---|
| Sandbox escape | 28 | **0 escapes** — all rejected at validation |
| Legitimate programs still usable | 6 | **6 ran** — the restriction costs the interface nothing |
| Resource bounds | 4 | **4 hung or died** |

---

## What held (no action needed)

All rejected at validation, never executed:

```
import subprocess              REJECTED: Import is not permitted
__import__('os').system(...)   REJECTED: attribute access is not permitted
().__class__.__bases__[0]...   REJECTED: attribute access is not permitted
f.__globals__['__builtins__']  REJECTED: attribute access is not permitted
getattr(record, '__globals__') REJECTED: unknown name 'getattr'
eval / exec / open             REJECTED: unknown name / attribute access
__builtins__                   REJECTED: name '__builtins__' is not permitted
lambda / walrus / try / with   REJECTED: node type is not permitted
global / async def / yield     REJECTED: node type is not permitted
class def / del / assert/raise REJECTED: node type is not permitted
import inside a function body  REJECTED: Import is not permitted
f"{record.__class__}"          REJECTED: attribute access is not permitted
```

And the interface remains usable — catalog calls, loops, arithmetic,
comprehensions, nested `def`, f-strings and dict/set/tuple literals all run. The
no-attribute rule really does cost nothing for a typed catalog, as claimed.

One apparent leak in my first pass was **my** error, not yours: `x = {}` then
`x['__class__']` is a string key on an empty dict. It raises `KeyError`, reaches
nothing, and is not an escape. My harness had classified every non-`REJECTED`
outcome as a leak, which was too coarse. Corrected before reporting.

---

## The finding: no execution timeout and no memory cap

All four validate, then hang or get OOM-killed. Run in a child process with a 3 s
join, or they take the reviewing process with them:

| Program | Result |
|---|---|
| `while True:\n    pass` | **HUNG** — no bound |
| `record(10 ** 10 ** 8)` | **HUNG** — CPython integer exponentiation |
| `record(len([0] * (10 ** 9)))` | **HUNG / OOM-killed** |
| `for i in range(10**6):\n    for j in range(10**4): ...` | **HUNG** |

`ALLOWED_NODES` includes `While`, `For` and `Pow` — correctly, since the interface
needs control flow and arithmetic — and `run()` calls `exec` with no deadline.

### Why this is not covered by the stated ceiling

`runtime.py`'s docstring is admirably explicit that an OS-level backstop is needed
before Step 6: *"a container with no shell binaries and seccomp refusing
`execve`/`fork`."* That addresses **escape**. It does not address **exhaustion**:

- seccomp refusing `execve`/`fork` does nothing to an infinite loop.
- a container memory limit kills the *container*, not the offending program, so the
  harness dies with it rather than returning a rejection the model can learn from.

So this is a distinct gap, not a subset of the one already recorded.

### Why it matters more here than in a normal sandbox

1. **Step 6 rewards the model for score.** A program that hangs costs GPU wall-clock
   and returns no signal. It is the cheapest possible accidental reward hack: the
   episode never completes, so it never scores zero either.
2. **Kaggle's limits make it expensive.** 12 h session cap, 20-30 min idle timeout,
   30 GPU-h/week. One hung program can consume a session.
3. **It is reachable by accident, not just by attack.** `while True` is an ordinary
   thing for a small model to emit when it loses the thread. This will fire in normal
   operation, not only under adversarial pressure.

### The shape of a fix, for you to judge

A timeout must interrupt *inside* `exec`, which pure-Python signal handling only does
between bytecodes — good enough for `while True`, useless against a single
`10 ** 10 ** 8` that never yields. So:

- `signal.setitimer` + a handler raising into the program covers loops, and turns a
  hang into a rejection the model sees — which keeps the restriction part of the
  interface, matching the design already used for `ProgramRejected`.
- It does **not** cover a single non-yielding C-level operation. That needs the
  program in a child process with `resource.setrlimit(RLIMIT_CPU, RLIMIT_AS)`, killed
  on breach.
- Cheap partial mitigation available at validation time: reject `Pow` where both
  operands are literal constants above some bound. Narrow, but it kills the specific
  integer-exponentiation bomb without touching legitimate arithmetic.

I have not implemented any of this — it is your module and the trade-off between
in-process simplicity and a child process is a design call, not a patch.

---

## Two smaller notes

**`bound` is scope-insensitive.** It is a single flat set collected over the whole
tree, so a name bound only inside a function body counts as bound at module level.
`def f():\n    y = 1` followed by a bare `y` passes validation and raises `NameError`
at run time. Not a security issue — `harness.py` reports the exception to the model as
data, which is the right behaviour — just noting that validation is more permissive
than the language.

**The catalog is a trust boundary the runtime cannot cover.** The runtime guarantees
that the *only* channel is the catalog; it says nothing about what a catalog function
does. A `write_file(path, text)` tool with an unrestricted path defeats every rule in
the module without triggering one. Worth a line in `ptc/README.md` so a future session
adding tools knows the guarantee stops at the function boundary.

---

## Reproducing

The corpus is small enough to inline rather than ship as a file in your directory. It
ran against `ptc/runtime.py` at `f083355`, copied read-only. Each program is run in a
`multiprocessing.Process` with a 3 s join, so a hang or OOM cannot take the harness
with it.

```python
CLASSIC = {                      # must all be REJECTED
    "import subprocess": "import subprocess\nsubprocess.run('id', shell=True)",
    "__import__ builtin": "__import__('os').system('id')",
    "class walk": "().__class__.__bases__[0].__subclasses__()",
    "func globals": "def f():\n    pass\nf.__globals__['__builtins__']",
    "getattr": "getattr(record, '__globals__')",
    "eval": "eval('1+1')", "exec": "exec('x=1')",
    "open": "open('/etc/passwd').read()", "builtins": "__builtins__",
    "lambda": "f = lambda: 1", "walrus": "(x := 1)",
    "try": "try:\n    pass\nexcept Exception:\n    pass",
    "with": "with open('x') as f:\n    pass",
    "global": "def f():\n    global x\n    x = 1",
    "async": "async def f():\n    pass", "yield": "def f():\n    yield 1",
    "import in func": "def f():\n    import os",
    "underscore": "_x = 1", "unknown": "subprocess",
    "classdef": "class C:\n    pass", "del": "x = 1\ndel x",
    "fstring attr": 'f"{record.__class__}"',
}
RESOURCE = {                     # all four currently unbounded
    "infinite while": "while True:\n    pass",
    "pow bomb": "record(10 ** 10 ** 8)",
    "memory bomb": "record(len([0] * (10 ** 9)))",
    "nested burn": "n = 0\nfor i in range(10**6):\n    for j in range(10**4):\n        n = n + 1",
}
```

Written before any fix exists, which — per your own note on the three escape tests —
is the only order in which it counts as evidence.
