"""A restricted runtime for the PTC arm.

arXiv 2609.11999 §3 defines PTC as a program over a typed catalog executed "within a
restricted runtime that provides no shell or other action channel". The restriction is
not a detail of that interface -- it IS the interface. An unrestricted Python kernel is
a strictly more capable thing, so measuring against one measures a different arm
(docs/spike-verifiers.md: rlm's ipython tool reaches a shell three different ways).

This module is that restriction. It validates a program's AST against an allowlist
before executing it with a catalog as its only names.

ponytail: AST validation, not a VM and not a subprocess sandbox. That is the smallest
thing that reproduces the published interface, and it is auditable by reading it.

SECURITY CEILING, stated because it will otherwise be forgotten: a static allowlist is
necessary and NOT sufficient against an adversary who gets to choose the program text.
CPython has escape routes that live in ordinary-looking expressions, and new ones appear
with new syntax. Before this runs output from a model that is being REWARDED for
score -- i.e. before Step 6 -- it needs an OS-level backstop underneath it: a container
with no shell binaries and seccomp refusing `execve`/`fork`. Until then the acceptance
suite in test_ptc.py is the evidence, and it is deliberately adversarial.
"""

from __future__ import annotations

import ast
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Builtins a program may use. Everything absent is absent on purpose: no `open`, no
# `__import__`, no `eval`/`exec`/`compile`, no `getattr`/`setattr`/`delattr`, no
# `globals`/`locals`/`vars`/`dir`, no `input`, no `breakpoint`, no `help`.
SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "divmod": divmod, "enumerate": enumerate, "filter": filter, "float": float,
    "int": int, "len": len, "list": list, "map": map, "max": max, "min": min,
    "print": print, "range": range, "repr": repr, "reversed": reversed,
    "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip,
}

# Node types a program may contain. Import/ImportFrom are absent, so `import subprocess`
# is rejected at validation rather than at run time.
ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass,
    ast.Return, ast.FunctionDef, ast.arguments, ast.arg,
    ast.Call, ast.Name, ast.Load, ast.Store, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript, ast.Slice,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension, ast.keyword, ast.Starred,
    ast.JoinedStr, ast.FormattedValue,
    # operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot, ast.BitAnd, ast.BitOr, ast.BitXor,
)


TIMEOUT = 5.0
"""Wall-clock seconds a program may run before it is stopped.

Generous for a program whose only work is chaining catalog calls, and short enough
that a hung rollout is a rejection rather than a stalled episode.
"""

MAX_DIGITS = 10_000
"""Decimal digits a statically-computable integer may reach.

`10 ** 10 ** 8` is a hundred million digits and takes CPython effectively forever in a
single opcode. A ten-thousand-digit intermediate is already far past anything a
catalog program needs.
"""

MAX_ELEMENTS = 1_000_000
"""Elements a statically-computable sequence repetition may produce (`[0] * 10 ** 9`)."""


class ProgramRejected(Exception):
    """The program failed validation. It was never executed."""


@dataclass
class Catalog:
    """The typed tool catalog: the program's ONLY action channel."""

    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def names(self) -> set[str]:
        return set(self.tools)


def _static_int(node: ast.AST) -> int | None:
    """The value of a node computable from literals alone, or None.

    Deliberately shallow: constants and the arithmetic that builds a huge number out of
    small literals. Anything involving a name is a runtime value and not this
    function's business.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _static_int(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp):
        left, right = _static_int(node.left), _static_int(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Pow):
            return _checked_pow(left, right, node)
    return None


def _checked_pow(base: int, exponent: int, node: ast.AST) -> int | None:
    """`base ** exponent`, refused before computing it if the result is absurd.

    The check has to happen BEFORE the multiplication, not after: computing the value
    in order to measure it is the same hang, moved into the validator. Digits are
    estimated as `exponent * log10(|base|)`, which needs no big arithmetic.
    """
    if exponent < 0 or base in (0, 1, -1):
        return None if exponent < 0 else base ** exponent
    digits = exponent * math.log10(abs(base)) if base else 0
    if digits > MAX_DIGITS:
        raise ProgramRejected(
            f"{base} ** {exponent} would be about {int(digits):,} digits "
            f"(limit {MAX_DIGITS:,}); the runtime has no memory to spare for it"
        )
    return base ** exponent


def _check_magnitude(tree: ast.Module) -> None:
    """Refuse literal resource bombs that a wall-clock tracer cannot interrupt.

    `while True` is caught at run time because a loop returns to the tracer between
    lines. `10 ** 10 ** 8` and `[0] * 10 ** 9` never do -- each is a single opcode that
    CPython runs to completion. So they are refused here, before execution.

    ponytail: literal forms only, and the ceiling is stated rather than hidden. A
    computed bomb (`n = 10 ** 8` then `10 ** n`) still gets through, because bounding
    that needs abstract interpretation of the whole program. The real fix is the OS:
    run the program in a child process under RLIMIT_AS and RLIMIT_CPU, which bounds
    every shape at once. That belongs with the container-and-seccomp backstop this
    module's docstring already requires before Step 6, and it is the same piece of
    work -- not a second one.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        if isinstance(node.op, ast.Pow):
            _static_int(node)          # raises if the result would be absurd
        elif isinstance(node.op, ast.Mult):
            for sequence, count in ((node.left, node.right), (node.right, node.left)):
                if isinstance(sequence, (ast.List, ast.Tuple, ast.Constant)):
                    size = _static_int(count)
                    if size is not None and size > MAX_ELEMENTS:
                        raise ProgramRejected(
                            f"a sequence repeated {size:,} times exceeds the "
                            f"{MAX_ELEMENTS:,} element limit"
                        )


def validate(program: str, catalog: Catalog) -> ast.Module:
    """Reject anything outside the allowlist. Raises `ProgramRejected`.

    Attribute access is refused outright. That is blunt, and it is the single most
    load-bearing rule here: every classic CPython sandbox escape is an attribute walk
    (`().__class__.__bases__[0].__subclasses__()`, `f.__globals__`, `x.__getattribute__`).
    A typed catalog needs no attribute access -- tools are plain functions -- so the
    blunt rule costs the interface nothing.
    """
    try:
        tree = ast.parse(program, mode="exec")
    except SyntaxError as e:
        raise ProgramRejected(f"syntax error: {e}") from e

    allowed_names = catalog.names() | set(SAFE_BUILTINS)
    bound: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            raise ProgramRejected(
                f"attribute access is not permitted (.{node.attr}); "
                "the catalog is the only action channel"
            )
        if not isinstance(node, ALLOWED_NODES):
            raise ProgramRejected(f"{type(node).__name__} is not permitted")
        if isinstance(node, (ast.Name, ast.arg)):
            ident = node.id if isinstance(node, ast.Name) else node.arg
            if ident.startswith("_"):
                raise ProgramRejected(f"name {ident!r} is not permitted")
            if isinstance(node, ast.arg) or (
                isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
            ):
                bound.add(ident)
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                raise ProgramRejected(f"name {node.name!r} is not permitted")
            bound.add(node.name)

    # Second pass: every *read* must resolve to the catalog, a safe builtin, or something
    # the program itself bound. Catches `subprocess.run` -- well, catches `subprocess`.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in allowed_names and node.id not in bound:
                raise ProgramRejected(
                    f"unknown name {node.id!r}; the catalog exposes {sorted(allowed_names - set(SAFE_BUILTINS))}"
                )
    # Last, so that a program which is rejected for a forbidden node says so rather
    # than reporting an arithmetic limit it also happens to break.
    _check_magnitude(tree)
    return tree


def _deadline_trace(deadline: float):
    """A tracer that turns "still running" into a rejection the model can read.

    Fires on every line of the program, so an unbounded loop is interrupted at the
    next line. It CANNOT interrupt a single long-running opcode -- `10 ** 10 ** 8` is
    one BinOp and CPython never returns to the tracer mid-computation. That half of
    the problem is handled at validation by `_static_magnitude`; this half is the one
    static analysis cannot see, because a loop's trip count is a runtime property.
    """
    def trace(frame, event, arg):
        if time.monotonic() > deadline:
            raise ProgramRejected(
                f"program exceeded its {TIMEOUT}s budget and was stopped"
            )
        return trace

    return trace


def run(program: str, catalog: Catalog, timeout: float = TIMEOUT) -> dict[str, Any]:
    """Validate, then execute under a wall-clock budget. Returns the final namespace.

    `__builtins__` is replaced wholesale, so even a name that slipped validation has
    nothing to reach. Validation is the guard; this is the belt.

    The timeout raises `ProgramRejected` like any other refusal, which is the point:
    the harness hands a rejection back as a tool message, so a model that wrote an
    unbounded loop is told so and can retry. A hang, by contrast, is the cheapest
    accidental reward hack there is -- an episode that never completes never scores
    zero either (`docs/ptc-runtime-review.md`).
    """
    tree = validate(program, catalog)
    scope: dict[str, Any] = {"__builtins__": SAFE_BUILTINS, **catalog.tools}
    code = compile(tree, filename="<ptc>", mode="exec")
    previous = sys.gettrace()
    sys.settrace(_deadline_trace(time.monotonic() + timeout))
    try:
        exec(code, scope)  # noqa: S102
    finally:
        # Restore rather than clear: pytest, coverage and debuggers install tracers of
        # their own, and stomping one would break the tools watching this run.
        sys.settrace(previous)
    return {k: v for k, v in scope.items() if not k.startswith("__")}
