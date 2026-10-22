"""Differential parity: run the task class's own gold queries through both arms.

`test_sql_arms.py` measures twelve abilities somebody named. `docs/harness-parity.md` §6
states the structural gap that leaves: "an asymmetry nobody wrote a capability for" is
invisible, and this project's worst historical defect (defect 5) was exactly such an
unlisted asymmetry. This module narrows that gap without asking anyone to name
anything. It takes the corpus's own gold queries -- written by BIRD, not by this
project, before either arm existed -- and runs each one through BOTH arms' execution
channel. Then it asks whether the two arms delivered the same answer.

Why the golds are the right probe. A capability list is a description of what the task
class needs, written by the people who built the arms; the golds ARE the task class.
Anything a gold does that one channel mishandles is a divergence on a real task,
whether or not anyone thought to list it.

**The three comparisons, and why all three are needed.**

1. **Delivery** -- what each arm returns: rows, a row-cap refusal, or an error. bash
   reaches sqlite through the wrapper (`run_bash_sql`'s own command); PTC calls the
   catalog function the arm itself registers (`make_execute_sql`, the object
   `sql_catalog` hands a program). One side refusing or failing where the other
   delivers is the finding, on either arm.

2. **Answer** -- the delivered rows, compared with the SCORER's semantics: `rows_match`
   in `bench/score.py`, `compare="set"` by default (BIRD's own
   `set(predicted) == set(ground_truth)`), multiset available as the sensitivity check.
   Typed values, not text: an int and the float of the same value are one answer, and
   NaN is folded so a query is equal to itself. This is the comparison a task is
   scored on, and it is imported rather than re-implemented for the reason every
   second implementation in this repo has taught.

3. **Render** -- what the MODEL reads. Delivery equality is not enough, because the
   model does not see rows. bash reads `sqlite3 -list -header` text; PTC reads dicts
   that a program must `print` (or subscript), and `print` renders Python `repr`. The
   same typed rows can therefore reach the two arms as different answers: NULL as an
   empty field versus the token `None`, a float at sqlite's CLI digits versus Python's
   shortest round-trip repr, a blob as raw bytes (which can also make the bash
   channel's runner raise `UnicodeDecodeError`), a control byte as caret notation on
   bash against the raw byte on PTC, a `|` or a newline inside a cell shifting the bash
   row's shape, a trailing all-NULL row collapsing into the wrapper's terminator, and
   two columns sharing a name appearing as `name|name` on bash against `name`/`name_2`
   on PTC. Render differences are reported separately from answer differences so a
   rendering divergence is never mistaken for a wrong answer, and never hidden by one.

**Deliberately not compared: ordering.** `compare="set"` is BIRD's convention, so order
is not part of the answer. The sweep reports a multiset sensitivity count.

**What this cannot cover, stated rather than buried.** A gold returns one result set.
It exercises `execute_sql` and the three outcomes above; it does not exercise
multi-query programs, `join`, the model's own `print` formatting, the prompt, or the
budgets. It cannot see an asymmetry that only a *model-written* query triggers -- the
sweep proves the class's own queries survive both channels, not that every reachable
query does. And the row cap here is `sql_runtime.MAX_ROWS` (200) while the scorer runs
at 500,000: a gold over 200 rows is refused by BOTH arms, which is agreement but not a
comparison, so the sweep counts that bucket separately and says so.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ptc.sql_arms import SQL_TOOL, _sh_single, install_wrapper
from ptc.sql_runtime import MAX_ROWS, over_cap_message

__all__ = [
    "Delivery",
    "Differential",
    "differential",
    "DELIVERY_OUTCOMES",
    "RENDER_CAUSES",
    "DELIVERY_CAUSES",
]

DELIVERY_OUTCOMES = ("ok", "refused", "error", "undecodable")
"""What one arm can do with one query.

`undecodable` is bash-only: `sqlite3 -list` writes a BLOB's raw bytes, and both the
arm's runner (`run_bash_sql`, `text=True`) and a model reading text hit that. Reported
rather than fixed -- the PTC arm delivers `b'\\x00\\xff'`, so the undecodable case IS
the finding, not a harness problem.
"""

RENDER_CAUSES = (
    "null_rendering",        # bash: empty field;    PTC: `None`
    "float_rendering",       # bash: CLI digits;     PTC: Python repr
    "blob_rendering",        # bash: raw bytes;      PTC: `b'..'`
    "separator_in_cell",     # a cell contains `|`: the bash row gains fields
    "newline_in_cell",       # a cell contains a newline: the bash row spans lines
    "duplicate_columns",     # bash: `name|name`;     PTC: `name`, `name_2`
    "column_count",          # the two channels disagree about how many columns exist
    "row_count",             # same answer rows, different line counts on bash
    "trailing_empty_row",    # bash: a final row of all-NULLs renders as a blank line
    "control_char_rendering",  # bash: caret notation (`^]`); PTC: the raw byte
    "type_rendering",        # same value, different type on bash (`'0'` against `0`)
)
"""What a render comparison can report, as data, so the sweep's summary is a Counter
over these names rather than strings assembled at three call sites."""

DELIVERY_CAUSES = (
    "one_sided_refusal",
    "one_sided_error",
    "one_sided_undecodable",
    "refusal_text_differs",
    "error_text_differs",
    "rows_differ",
    "trailing_empty_row",
)
"""What a delivery/answer comparison can report. Same reason as `RENDER_CAUSES`.
`trailing_empty_row` is a DELIVERY cause rather than a render one because the row is
gone from the answer the bash arm can compute from its text, not merely spelled
differently; it also appears in `RENDER_CAUSES` when both arms delivered the same
number of rows and the difference is only spelling."""


@dataclass(frozen=True)
class Delivery:
    """One arm's delivery of one query, reduced to what the comparisons need.

    `rows` is the typed answer -- tuples of int/float/str/bytes/None -- or None when
    the arm did not deliver one. `outcome` is one of `DELIVERY_OUTCOMES`; `detail`
    carries the refusal or error text so a one-sided refusal can be quoted. `text`
    keeps the channel rendering, because render parity is a second question about the
    same delivery and re-running the query to ask it would let the two questions be
    answered against two states of a nondeterministic query.
    """

    outcome: str
    rows: list[tuple] | None = None
    detail: str = ""
    text: str = ""
    columns: tuple[str, ...] = ()
    """Column names as the arm's channel knows them: on bash, the `-list -header`
    line; on PTC, the deduped dict keys (`name`, `name_2`). Empty when no rows."""

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    @property
    def n_rows(self) -> int:
        return len(self.rows or ())


@dataclass(frozen=True)
class Differential:
    """One query, both arms, every comparison, and every cause found.

    `agreed` is the delivery+answer verdict: both arms the same rows (or the same
    refusal, or the same error). `delivery_causes` names why not, when not.
    `render_causes` is orthogonal -- non-empty means the two models would read
    different things off a delivery that already agreed.
    """

    name: str
    question_id: Any
    bash: Delivery
    ptc: Delivery
    agreed: bool
    method: str = "set"
    """`set` or `multiset` -- which comparison produced `agreed`."""
    delivery_causes: tuple[str, ...] = ()
    render_causes: tuple[str, ...] = ()
    note: str = ""

    @property
    def diverged(self) -> bool:
        return not self.agreed

    @property
    def capped(self) -> bool:
        """Both arms refused at the cap. Agreement, but not a row comparison: a gold
        in this bucket is covered by neither the answer nor the render pass."""
        return self.bash.outcome == self.ptc.outcome == "refused"


# ------------------------------------------------------------------------------------
# Delivery: the same query through each arm's channel.
# ------------------------------------------------------------------------------------

def bash_command(db_path: str, query: str, *, bindir: str | Path,
                 max_rows: int = MAX_ROWS, install: bool = True) -> subprocess.CompletedProcess:
    """Run `execute_sql "<query>"` through the arm's wrapper, bytes undecoded.

    Byte-for-byte the command `run_bash_sql` builds (same wrapper, same quoting, same
    PATH prepend), reached without `text=True` for one reason: `run_bash_sql` raises
    `UnicodeDecodeError` on a BLOB and returns no observation at all. That is a real
    property of the bash channel and the differential has to be able to report it
    instead of crashing on it. `test_sql_diff.py` pins this command against
    `run_bash_sql` on a query the two can both handle, so "the same channel" is
    measured rather than asserted.

    `install=False` reuses a wrapper already written. Concurrent callers should install
    into a directory of their own: the wrapper embeds the task's database path, so two
    concurrent queries against different databases in one `bindir` overwrite each
    other's script even now that the install is atomic. The sweep gives each watched
    invocation its own directory, even if it outlives the worker's timeout. A first
    version shared one and produced fifteen one-sided errors that were sqlite running
    against the wrong file.
    """
    if install:
        install_wrapper(bindir, db_path, max_rows)
    env = dict(os.environ)
    env["PATH"] = f"{Path(bindir)}{os.pathsep}{env.get('PATH', '')}"
    command = f"{SQL_TOOL} {_sh_single(query)}"
    return subprocess.run(["/bin/sh", "-c", command], capture_output=True, env=env,
                          cwd=str(bindir), timeout=60.0)


def _typed(cell: str, like: Any = None) -> Any:
    """One `-list` field, read against the value the PTC arm saw for the same cell.

    **Type-directed, not guessed.** `-list` prints values without quotes, so its text
    alone cannot distinguish the string `'04653'` from the integer 4653 or the TEXT
    `'0'` from the integer 0. Guessing numbers from the bytes destroyed the leading
    zero and reported three of the first forty BIRD dev golds as divergent when the
    rows agreed -- the differential's own parser manufacturing the finding it exists
    to look for. So the parse is TOLD the storage class by the PTC value for the same
    cell: text stays text, an integer or a real parses, a NULL is the empty field.

    The residual is the channel's and is reported rather than smoothed: a model reading
    `-list` sees `0` where the row holds the TEXT `'0'`, and nothing in the output says
    which it was. `''` from a NULL and `''` from an empty string are likewise one field
    on this channel, which is `null_rendering`.
    """
    if cell == "":
        # NULL and the empty string are ONE field on this channel. Which one it was is
        # not recoverable from `-list` output, so the value is typed as the empty string
        # and the delivery comparison folds the pair on both sides (see `_same_answer`).
        # The loss is named separately as `null_rendering`.
        return ""
    if like is None or isinstance(like, (bool, bytes)):
        return cell
    if isinstance(like, (int, float)) and not isinstance(like, bool):
        try:
            return int(cell) if isinstance(like, int) else float(cell)
        except ValueError:
            return cell
    return cell


def _bash_delivery(proc: subprocess.CompletedProcess, *, max_rows: int,
                   typed_like: list[tuple] | None = None) -> Delivery:
    """What the bash model reads, and what rows it can recover from that text.

    `typed_like` is the PTC arm's rows when it delivered any, used to give the
    unquoted `-list` text the storage class it cannot carry (see `_typed`). Passing it
    is not cheating on behalf of bash: the text IS the channel's output, and the
    question is what answer an agent could read off it, which is exactly what a model
    does with its own knowledge of the schema's column types.
    """
    raw_out, raw_err = proc.stdout, proc.stderr
    try:
        stdout = raw_out.decode("utf-8")
        stderr = raw_err.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A BLOB reached stdout. The model reads replacement characters; the exact
        # bytes are not recoverable through this channel at all.
        return Delivery("undecodable", None, f"UnicodeDecodeError: {exc}",
                        text=raw_out.decode("utf-8", "replace"))
    if proc.returncode != 0:
        outcome = "refused" if over_cap_message(max_rows) in stderr else "error"
        return Delivery(outcome, None, (stderr or stdout).strip(), text=stdout)
    if stdout == "":
        return Delivery("ok", [], text=stdout)
    # `sqlite3 -list` renders a row whose fields are all NULL/empty as a blank line.
    # The wrapper prints the CLI's output through `printf '%s\n'`, so the text ends in
    # a newline and a trailing run of blank rows is indistinguishable from that
    # terminator: those rows are LOST here. The loss is the channel's (`-list` has no
    # quoting; `-csv` would), not a parser's convenience. Keeping the final split
    # element means an INTERIOR blank row survives, which is the best any parser of
    # this text can do; `trailing_empty_row` records the rest as a finding.
    lines = stdout.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    header = tuple(lines[0].split("|"))
    body = lines[1:]
    rows: list[tuple] = []
    for i, line in enumerate(body):
        cells = line.split("|")
        like_row = (typed_like[i] if typed_like is not None and i < len(typed_like)
                    and len(typed_like[i]) == len(cells) else None)
        rows.append(tuple(
            _typed(cell, None if like_row is None else like_row[j])
            for j, cell in enumerate(cells)
        ))
    return Delivery("ok", rows, text=stdout, columns=header)


def _ptc_delivery(db_path: str, query: str, *, max_rows: int = MAX_ROWS) -> Delivery:
    """What the PTC model reads, and the typed rows behind it -- from ONE execution.

    The rows come from `make_execute_sql`, the exact object `sql_catalog` registers for
    a program, so the action space compared is the arm's rather than a test double.
    The text is `repr(rows)`, which is what `print(rows)` sends the model and what
    `run_ptc_program` returns for that program; taking both from one execution matters
    because a gold may not be deterministic and a differential that re-ran the query
    to ask a second question about it would report its own re-run as a finding.

    A failed query raises `ProgramRejected` carrying sqlite's own message, exactly as
    `run_ptc_program` surfaces it.
    """
    from ptc.runtime import ProgramRejected
    from ptc.sql_arms import make_execute_sql

    try:
        rows = make_execute_sql(db_path, max_rows)(query=query)
    except ProgramRejected as exc:
        reason = f"rejected: {exc}"
        outcome = "refused" if over_cap_message(max_rows) in reason else "error"
        return Delivery(outcome, None, reason, text=reason)
    except Exception as exc:  # noqa: BLE001 -- run_ptc_program's third outcome
        reason = f"error: {type(exc).__name__}: {exc}"
        return Delivery("error", None, reason, text=reason)
    return Delivery("ok", [tuple(row.values()) for row in rows], text=repr(rows),
                    columns=tuple(rows[0].keys()) if rows else ())


# ------------------------------------------------------------------------------------
# Answer comparison: the scorer's, imported.
# ------------------------------------------------------------------------------------

def _normalise(value: Any) -> Any:
    """The scorer's NaN fold, applied to a cell from either arm.

    `float('nan') != float('nan')`, so a NaN would make a query unequal to itself.
    Reproduced rather than imported because `bench.score` imports `bench.task`, and
    `ptc` has to stay importable where `bench` is not -- the constraint `adapt_task`
    documents. `test_sql_diff.py::test_the_answer_comparison_is_the_scorers` pins this
    against `execution_accuracy`'s behaviour so it cannot drift.
    """
    if isinstance(value, float) and math.isnan(value):
        return "<nan>"
    return value


def _canonical(rows: list[tuple], compare: str) -> tuple[str, Any]:
    """`(kind, key)`: two result sets are one answer iff both tuples are equal.

    `kind` keeps a multiset key from ever equalling a set key; `key` is the normalised
    rows. The relation is `rows_match`'s: set equality by default, `Counter` equality
    for multiset. `bench.score.rows_match` is the one definition of "same answer" in
    this repo, and `execution_accuracy` calls it; the differential imports it when
    available and pins the fallback against it when not.
    """
    from collections import Counter

    normalised = [tuple(_normalise(v) for v in row) for row in rows]
    key = Counter(normalised) if compare == "multiset" else set(normalised)
    return compare, key


def _same_answer(bash_rows: list[tuple], ptc_rows: list[tuple],
                 compare: str) -> bool:
    """Compare two deliveries with `bench.score.rows_match` where it can be imported.

    The rows are aligned first: a NULL and the empty string are ONE field on the bash
    channel, so BOTH sides fold `""` and `None` to one token before the comparison.
    Folding only the bash side would have made the comparison asymmetric in bash's
    favour on every NULL-vs-empty-string gold -- measured on 445 and 584 -- which is the
    wrong direction for a parity check. The text side, where the two arms genuinely
    differ, is reported as `null_rendering`.
    """
    def fold(row):
        return tuple(None if v == "" else _normalise(v) for v in row)

    def unrender(row):
        return tuple(_unrender_control(v) if isinstance(v, str) else v for v in row)

    bash = [fold(row) for row in bash_rows]
    ptc = [fold(row) for row in ptc_rows]
    try:
        from bench.score import rows_match
    except ImportError:  # `ptc` without `bench`: the docstring's constraint, honoured
        hit = _canonical(bash, compare) == _canonical(ptc, compare)
    else:
        hit = rows_match(ptc, bash, compare=compare)
    if hit:
        return True
    # The CLI prints a control byte as caret notation (`\x1d` -> `^]`); the program gets
    # the byte. The ANSWER is the same value, so the delivery agrees, and the text
    # difference is reported as `control_char_rendering` rather than scored as a
    # divergence. Applied after the normal comparison and only as a fallback, so this
    # reversal can never turn a genuinely different answer into agreement except by
    # mapping a literal `^X` cell to the control byte it spells -- measured at zero
    # occurrences in BIRD dev.
    return _canonical([unrender(r) for r in bash], compare) == _canonical(ptc, compare)


# ------------------------------------------------------------------------------------
# Render comparison: what each MODEL reads.
# ------------------------------------------------------------------------------------

def _sqlite_message(detail: str) -> str:
    """sqlite's own sentence out of an arm's wrapper text.

    The CLI prefixes `Parse error in Nth command line argument:` (and, in some forms,
    `Error: near line ...`); the sandbox prefixes `rejected: OperationalError:`. Both
    end in sqlite's message, which is the information; the wrapper is the channel
    (`error_message_framing`). Everything up to and including the last known prefix is
    dropped -- after the *last* one, so the CLI's two prefixes on one line are both
    removed and a message that itself contains a colon (`no such column: x`) survives
    whole.
    """
    position = re.match(
        r"Parse error in \d+(?:st|nd|rd|th) command line argument: ", detail)
    cut = position.end() if position else 0
    for marker in ("rejected: OperationalError: ", "OperationalError: ",
                   "Parse error in ", "Error: near line "):
        i = detail.find(marker)
        if i != -1:
            cut = max(cut, i + len(marker))
    return detail[cut:].strip()


def _unrender_control(cell: str) -> str:
    """The raw control bytes a CLI cell's caret notation stands for.

    Only used to decide WHETHER a cell differs, never to rewrite the delivery: the bash
    model reads the caret text, which is the finding. sqlite prints a control byte as
    `^` plus the byte XOR 0x40 (`\\x1d` -> `^]`, `\\x00` -> `^@`, `\\x7f` -> `^?`), so the
    reversal is exact for every caret escape. A literal `^]` in the data would be
    mapped to `\\x1d`, which can only make a difference look SMALLER, never invent one;
    measured at zero occurrences in BIRD dev's in-cap golds.
    """
    out = []
    i = 0
    while i < len(cell):
        ch = cell[i]
        nxt = cell[i + 1] if i + 1 < len(cell) else ""
        if ch == "^" and nxt and (64 <= ord(nxt) <= 95 or nxt == "?"):
            out.append(chr(ord(nxt) ^ 0x40))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _cell_cause(bash_value: Any, ptc_value: Any) -> str:
    """One cell's rendering difference, or empty when the two read the same.

    Only called when the answer comparison already agreed, so `bash_value ==
    ptc_value` (modulo int/float) is the normal case and the branches below are the
    narrow set where the text says something the value does not.
    """
    if ptc_value is None:
        return "null_rendering"
    if isinstance(ptc_value, bytes):
        return "blob_rendering"
    if isinstance(ptc_value, float):
        # bash's text is parsed back to a float above; a difference means the CLI's
        # digits did not round-trip to the same double.
        return "" if bash_value == ptc_value else "float_rendering"
    if isinstance(ptc_value, str):
        if "\n" in ptc_value:
            return "newline_in_cell"
        if "|" in ptc_value:
            return "separator_in_cell"
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in ptc_value):
            return "control_char_rendering"
        return "" if bash_value == ptc_value else "type_rendering"
    return ""


def _render_causes(bash: Delivery, ptc: Delivery) -> tuple[str, ...]:
    """Compare the two model-visible renderings, when both arms delivered rows.

    Read off the two Delivery objects, never re-executed: the query may not be
    deterministic, and two questions asked against two states is how a differential
    starts reporting its own re-run as a finding.
    """
    causes: list[str] = []
    if len(bash.columns) != len(ptc.columns):
        causes.append("column_count")
    if bash.columns and ptc.columns and bash.columns != ptc.columns:
        if any(c.endswith(("_2", "_3")) for c in ptc.columns) or \
                any(bash.columns.count(c) > 1 for c in bash.columns):
            causes.append("duplicate_columns")

    bash_rows, ptc_rows = bash.rows or [], ptc.rows or []
    if len(bash_rows) != len(ptc_rows):
        # Two shapes produce a row-count difference without either arm being wrong
        # about a value: a newline in a cell splits one bash row into several, and a
        # trailing run of all-NULL rows collapses into the wrapper's terminator.
        # Distinguish them before calling it a plain count mismatch, because the first
        # two are findings about the rendering and the third is a finding about the
        # answer.
        if any(isinstance(v, str) and "\n" in v for row in ptc_rows for v in row):
            causes.append("newline_in_cell")
        elif len(bash_rows) < len(ptc_rows) and all(
                all(v in (None, "") for v in row)
                for row in ptc_rows[len(bash_rows):]):
            causes.append("trailing_empty_row")
        else:
            causes.append("row_count")
        return tuple(causes)

    for b_row, p_row in zip(bash_rows, ptc_rows):
        if len(b_row) != len(p_row):
            if any(isinstance(v, str) and "|" in v for v in p_row):
                causes.append("separator_in_cell")
            continue
        for b_val, p_val in zip(b_row, p_row):
            cause = _cell_cause(b_val, p_val)
            if cause and cause not in causes:
                causes.append(cause)
    return tuple(causes)


# ------------------------------------------------------------------------------------
# The entry point.
# ------------------------------------------------------------------------------------

def differential(task: Any, *, bindir: str | Path, max_rows: int = MAX_ROWS,
                 compare: str = "set", answer_only: bool = False) -> Differential:
    """Run one task's gold through both arms and report every comparison.

    `task` is anything `ptc.sql_arms.adapt_task` can read; a gold query is required,
    because a differential over no gold is a differential over nothing. `answer_only`
    skips the render pass, which is the sweep's cheap path -- render causes are only
    meaningful where both arms delivered rows, and the pass is pure computation once
    both deliveries exist, so the flag saves little; it exists for callers that only
    need agreement.
    """
    from ptc.sql_arms import adapt_task

    view = adapt_task(task)
    if not view.gold_sql.strip():
        raise ValueError(f"task {view.name!r} has no gold query to compare")
    if compare not in ("set", "multiset"):
        raise ValueError(f"compare must be 'set' or 'multiset', got {compare!r}")

    # PTC first even though bash's command is the cheaper one: its typed rows are what
    # gives the unquoted `-list` text a storage class (`_typed`), and a bash delivery
    # parsed without them cannot tell TEXT '04653' from INTEGER 4653.
    ptc = _ptc_delivery(view.db_path, view.gold_sql, max_rows=max_rows)
    proc = bash_command(view.db_path, view.gold_sql, bindir=bindir, max_rows=max_rows)
    bash = _bash_delivery(proc, max_rows=max_rows,
                          typed_like=ptc.rows if ptc.ok else None)

    delivery_causes, note = _delivery_causes(bash, ptc, compare, max_rows)
    render: tuple[str, ...] = ()
    if not answer_only and bash.ok and ptc.ok:
        render = _render_causes(bash, ptc)
    return Differential(
        name=view.name,
        question_id=getattr(task, "question_id", None),
        bash=bash, ptc=ptc,
        agreed=not delivery_causes,
        method=compare,
        delivery_causes=delivery_causes,
        render_causes=render,
        note=note,
    )


def _delivery_causes(bash: Delivery, ptc: Delivery, compare: str,
                     max_rows: int) -> tuple[tuple[str, ...], str]:
    """Every reason the two deliveries disagree, and a human-readable note.

    A one-sided refusal or error is a divergence regardless of which arm had it. Where
    both arms fail the same way, the TEXT is compared too, because
    `SECOND_HARNESS_REQUIREMENTS` entry 5 promises the same refusal text on both arms
    and the sweep is where that promise gets measured over real queries rather than
    over one probe. Error text is compared on sqlite's own message:
    `error_message_framing` is a declared asymmetry about the wrapper, not the message.
    """
    causes: list[str] = []
    if bash.outcome != ptc.outcome:
        causes.append({
            "refused": "one_sided_refusal",
            "error": "one_sided_error",
            "undecodable": "one_sided_undecodable",
            "ok": "one_sided_refusal",
        }[ptc.outcome if bash.outcome == "ok" else bash.outcome])
        return tuple(causes), f"bash {bash.outcome} vs ptc {ptc.outcome}"

    if not bash.ok:
        if bash.outcome == "refused":
            shared = over_cap_message(max_rows)
            if not (shared in bash.detail and shared in ptc.detail):
                return ("refusal_text_differs",), "refusal text differs"
        elif bash.outcome == "error":
            if _sqlite_message(bash.detail) != _sqlite_message(ptc.detail):
                return (("error_text_differs",),
                        f"bash {_sqlite_message(bash.detail)!r} vs "
                        f"ptc {_sqlite_message(ptc.detail)!r}")
        return (), f"both {bash.outcome}"

    if not _same_answer(bash.rows or [], ptc.rows or [], compare):
        causes = ["rows_differ"]
        # Name the cause when it is one of the two structural losses, so a sweep does
        # not count a channel defect as an unexplained row difference.
        b, p = bash.rows or [], ptc.rows or []
        if len(b) < len(p) and all(all(v in (None, "") for v in row)
                                   for row in p[len(b):]):
            causes.append("trailing_empty_row")
        return tuple(causes), (
            f"bash {bash.n_rows} rows vs ptc {ptc.n_rows} rows; "
            f"bash sample {list(b)[:2]!r}, ptc sample {list(p)[:2]!r}")
    return (), ""
