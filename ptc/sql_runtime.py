"""The primitives a restricted PTC program needs before a SQL result is usable.

`runtime.py` is the restriction and must stay blunt: no imports, no attribute access,
no `try`. That bluntness costs the interface nothing while a catalog returns scalars --
and it cost the project an entire run the moment a catalog returned structure the
program owned no primitive to open (defect 5, `docs/deviations.md`). This module is the
narrow set of additions SQL forces, each one added because a probe in
`test_sql_arms.py` failed without it, and each one recorded here with that reason so a
later reader can tell a measured need from a convenience.

Two things live here and nothing else:

1. `rows_from_cursor` -- how a SQL result becomes data a sandboxed program can read.
   The naive `dict(zip(columns, row))` loses a column whenever a query selects two
   columns of the same name, which `SELECT e.name, d.name FROM ...` does on every
   two-table join. Measured: that shape arrives in the sandbox as a row of length 1,
   while `sqlite3 -list -header` prints `name|name` and both values. A typed channel
   that silently drops half a join is defect 5 again in a different costume, so the
   duplicates are suffixed rather than collapsed.

2. `SQL_PRIMITIVES` -- catalog entries added to close a measured asymmetry, with the
   reason as data in `PRIMITIVE_REASONS`. The bar for entry is NOT "a program would be
   tidier with it": every entry has to name the thing the bash arm does in one word
   that the sandbox otherwise reaches only by hand-rolling. Hand-rolling is what the
   model did for 25 calls on `total-invoice` before discovering `ord` was absent too.

Keyword-only on purpose. `harness.py::_bridge` is keyword-only for MCP tools and the
system prompt tells the model to pass every catalog argument by keyword; a locally
registered tool that quietly accepted positionals would teach the opposite of what the
prompt says, which is run 1's defect 3 (34 of 54 tool failures were that mismatch).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from ptc.runtime import ProgramRejected

MAX_ROWS = 200
"""Rows one SQL action may return, on EITHER arm.

Not a performance guard -- a parity axis. An uncapped result is a different amount of
information per arm the moment one arm's observation is truncated by a context limit
and the other's is not, and neither arm would be told it happened. Exceeding it is a
refusal both arms receive as text (see `ptc.sql_arms`), never a silent truncation: a
model that reads 200 of 5,000 rows and answers confidently is the failure mode a cap
is supposed to prevent, not cause.

200 keeps one observation inside a few thousand tokens on both arms. A task needing
more rows than this client-side should aggregate in SQL, which both arms can do with
equal ease -- that is the point of putting the cap on the channel rather than on one
arm's parser.
"""


def dedup_columns(names: list[str]) -> list[str]:
    """Column names with repeats suffixed `_2`, `_3`, ... so no value is unreachable.

    sqlite names both columns of `SELECT e.name, d.name` simply `name`, and a dict
    keyed on that keeps the last one. Suffixing is visibly lossy in the NAME and
    lossless in the VALUE, which is the right trade: a program can still read both
    cells, and the prompt says how the suffix is spelled so the model is not guessing.

    A column already called `name_2` alongside two `name`s would collide with the
    generated suffix, so generated names are checked against the ones already taken
    rather than assumed free.
    """
    taken = set(names)
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 1:
            out.append(name)
            continue
        suffix = seen[name]
        candidate = f"{name}_{suffix}"
        while candidate in taken or candidate in out:
            suffix += 1
            candidate = f"{name}_{suffix}"
        out.append(candidate)
    return out


def over_cap_message(max_rows: int) -> str:
    """The refusal both arms emit when a result exceeds the cap.

    One function rather than two string literals, because the bash arm's channel
    wrapper embeds this text and the PTC arm's `rows_from_cursor` raises it. Two
    copies would drift, and the parity test asserts the two arms refuse *identically* --
    an arm told "add a LIMIT" while the other is told nothing is an arm with more
    information about its own channel.
    """
    return (
        f"the query returned more than {max_rows} rows, the limit one SQL action may "
        f"deliver. Add a LIMIT, or aggregate in SQL (COUNT, SUM, MAX, GROUP BY) so "
        f"the database does the work."
    )


def rows_from_cursor(cursor: sqlite3.Cursor,
                     max_rows: int = MAX_ROWS) -> list[dict[str, Any]]:
    """A SQL result as a list of dicts a sandboxed program can subscript.

    Fetches `max_rows + 1` and refuses on the overflow row rather than fetching
    everything and slicing: the point of the cap is to not materialise a result the
    channel has already decided not to deliver.

    A statement with no result set (`cursor.description is None`) returns `[]`, which
    is the same thing the program sees for a SELECT that matched nothing. That
    conflation is deliberate and declared: the channel is read-only, so the only
    description-less statements reachable through it are ones that have already failed.
    """
    columns = dedup_columns([d[0] for d in cursor.description or []])
    if not columns:
        return []
    fetched = cursor.fetchmany(max_rows + 1)
    if len(fetched) > max_rows:
        raise ProgramRejected(over_cap_message(max_rows))
    return [dict(zip(columns, row)) for row in fetched]


def join(*, sep: str, parts: Any) -> str:
    """Join `parts` with `sep`, as a catalog function.

    Added because the declared task class contains multi-value answers -- "their names
    in alphabetical order, separated by single spaces" is the shape four of `ledger`'s
    own tasks already use -- and the sandbox refuses the str method as attribute
    access. The value stays REACHABLE without this (string accumulation in a loop,
    measured working), so this is not a capability gap; it is a cost gap on a measured
    co-primary. The bash arm formats the same answer with one `tr`, and completion
    tokens are a pre-registered co-primary, so leaving the accumulator loop in place
    would put a three-line tax on one arm's cost figure for a step that is not the
    axis under measurement.

    Stringifies its parts, because the rows a program joins are typed and a model
    joining an integer column with a space should not be handed a TypeError for being
    right about the data.
    """
    return sep.join(str(part) for part in parts)


SQL_PRIMITIVES: dict[str, Callable[..., Any]] = {"join": join}
"""Catalog entries this module adds, over and above the task's own SQL tool."""

PRIMITIVE_REASONS: dict[str, str] = {
    "join": (
        "multi-value answers are in the declared task class and the sandbox refuses "
        "the str method as attribute access. Reachable without it via an accumulator "
        "loop, so this closes a cost gap on a co-primary (completion tokens), not a "
        "capability gap."
    ),
}
"""Why each primitive exists, as data: `docs/harness-parity.md` renders this rather
than restating it, so a primitive cannot be added without a reason or keep a reason
that stopped being true."""

UNREACHABLE_IN_SANDBOX: dict[str, str] = {
    "try/except": (
        "ast.Try is not in runtime.ALLOWED_NODES, so a program cannot recover from a "
        "failed query within one action. The bash arm can, with || or 2>/dev/null. "
        "Both arms see the failure as action output and may retry on the next turn, so "
        "this is a budget asymmetry, not an information one. Declared, not fixed: "
        "adding Try widens the sandbox for every program, and the escape surface it "
        "opens is not worth one retry."
    ),
    "lambda": (
        "ast.Lambda is absent, so a sorted() key written as a lambda is rejected. The "
        "same key written as a def is accepted and measured working, so the capability "
        "is reachable and only the spelling differs."
    ),
    "str methods": (
        "attribute access is refused outright, so lower(), split() and strip() are "
        "unavailable. The grader normalises case and whitespace on both arms "
        "(ledger/taskset.py's reward lowercases and re-joins), so no answer in the "
        "declared class needs them."
    ),
}
"""Sandbox limits that SQL work runs into and this module deliberately does NOT fix,
each with the reason and the direction it pushes. A limit absent from this dict and
absent from `SQL_PRIMITIVES` is an undeclared asymmetry, which is the defect-5 shape."""
