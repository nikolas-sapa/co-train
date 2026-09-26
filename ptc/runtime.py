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


class ProgramRejected(Exception):
    """The program failed validation. It was never executed."""


@dataclass
class Catalog:
    """The typed tool catalog: the program's ONLY action channel."""

    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def names(self) -> set[str]:
        return set(self.tools)


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
    return tree


def run(program: str, catalog: Catalog) -> dict[str, Any]:
    """Validate, then execute. Returns the program's final namespace.

    `__builtins__` is replaced wholesale, so even a name that slipped validation has
    nothing to reach. Validation is the guard; this is the belt.
    """
    tree = validate(program, catalog)
    scope: dict[str, Any] = {"__builtins__": SAFE_BUILTINS, **catalog.tools}
    exec(compile(tree, filename="<ptc>", mode="exec"), scope)  # noqa: S102
    return {k: v for k, v in scope.items() if not k.startswith("__")}
