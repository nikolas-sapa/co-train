"""The paired bash and PTC arms for SQL tasks, plus the parity contract between them.

Run 1 reported bash ahead of PTC by 64.3 pp and **the whole gap was instrument**
(defect 5, `docs/deviations.md`). Both arms were handed the same three MCP tools, so
the arms looked paired. They were not: bash held those tools as native tool calls and
read their JSON with the model's own attention, while PTC reached them through a
sandbox with no `import json`, no attribute access and no `ord` -- so it received a
JSON *string it owned no primitive to parse*. bash's action space was a strict
superset. Five of nine harness faults penalised PTC and a green test suite saw none of
them, because nothing in the suite compared what the two arms could DO.

So this module does not assert parity in prose. It carries the contract as data:

* `CAPABILITIES` -- one entry per ability the declared SQL task class needs, each
  holding an executable probe **per arm**. A capability is present on an arm when that
  arm's probe actually runs and returns the expected answer. `test_sql_arms.py` runs
  both probes for every capability and fails on any arm that reaches something the
  other cannot. That is a measurement, not a claim, and it goes red when either arm
  changes shape.
* `DECLARED_ASYMMETRIES` -- the gaps that are known, deliberate and signed off, read
  straight out of `sql_runtime.UNREACHABLE_IN_SANDBOX`. A gap in neither the probe set
  nor this dict is an undeclared asymmetry, which is the defect-5 shape, and the test
  says so by name.

Two invariants are structural rather than probe-shaped and are stated here because the
test checks them where they can actually fire:

1. **The PTC arm registers exactly one tool.** `run_program(code: str) -> str`, and
   nothing else (spec invariant 1). TRL renders every registered tool as a schema in
   the system prompt, so registering a typed `execute_sql` tool *alongside*
   `run_program` would quietly build the typed-tool-calling comparator instead of PTC
   -- the exact axis this project measures. The SQL tool reaches the model as a catalog
   entry INSIDE the program plus prompt text, never as a second schema.
2. **The cap lives on the channel, not on one arm's parser.** `MAX_ROWS` and
   `over_cap_message` are imported, not re-spelled, and the bash arm reaches sqlite
   through a wrapper that enforces both. Raw `sqlite3 <db> "<query>"` is an *uncapped*
   channel, which is an information asymmetry in bash's favour -- defect 5 inverted --
   so the wrapper exists to remove it, and its body is the brief's own command form.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from ptc.runtime import SAFE_BUILTINS, Catalog, ProgramRejected
from ptc.sqlite_safety import protect_connection
from ptc.sql_runtime import (
    MAX_ROWS,
    PRIMITIVE_REASONS,
    SQL_PRIMITIVES,
    UNREACHABLE_IN_SANDBOX,
    over_cap_message,
    rows_from_cursor,
)

__all__ = [
    "TaskView",
    "adapt_task",
    "schema_text",
    "make_execute_sql",
    "wrapper_script",
    "install_wrapper",
    "run_bash_sql",
    "SQL_TOOL",
    "SHARED_PROMPT",
    "BASH_CHANNEL",
    "PTC_CHANNEL",
    "prompt_for",
    "Capability",
    "CAPABILITIES",
    "DECLARED_ASYMMETRIES",
    "HarnessBackend",
    "PTC_V1",
    "ArmPair",
    "build_sql_arms",
    "SECOND_HARNESS_REQUIREMENTS",
]

SQL_TOOL = "execute_sql"
"""The name the SQL action carries on BOTH arms.

The PTC arm registers it as a catalog entry callable from inside the program; the bash
arm's wrapper script is installed under the same name on PATH. One name because the
prompt text is shared (`SHARED_PROMPT`) and only the channel paragraph differs -- an
arm told its action is called something else is an arm reading different prompt text,
which is a confound on prompt content rather than on channel.
"""

WRAPPER_TIMEOUT = 30.0
"""Seconds one bash-arm query may run.

Deliberately NOT `runtime.TIMEOUT` (5.0): that budget bounds a whole PTC *program*,
which may issue several queries, so handing the bash arm 5s per query would give it a
tighter per-query deadline than PTC and a looser per-action one. 30s matches
`bench.score.execution_accuracy`'s own default, so a query the scorer will run is a
query both arms can run.
"""


# ------------------------------------------------------------------------------------
# The task interface: ONE adapter function.
# ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskView:
    """Everything either arm needs from a task, and nothing else.

    Both arms are built from one of these, so a field the bash arm reads and the PTC
    arm does not cannot exist: there is one struct and `prompt_for` renders it once.
    """

    name: str
    question: str
    db_path: str
    gold_sql: str
    tier: str = "unknown"
    evidence: str = ""
    """BIRD's external-knowledge hint, empty for corpora that ship none. Part of the
    task as BIRD defines it -- the published EX figures are measured WITH it -- so it
    belongs in the shared prompt, identically on both arms."""


def adapt_task(task: Any) -> TaskView:
    """The only coupling between this module and bench task representations.

    Duck-typed on purpose. Importing `bench.task.SqlTask` would make `ptc`
    unimportable wherever `bench` is absent and would pin this module to that
    dataclass's field set; `getattr` against the documented names costs nothing and
    keeps the seam at one function, so a change in `bench` is a change in one body
    here.

    The minimum assumed is `db_path`, `question`, a gold query and a difficulty tier
    (`docs/bench-taskset.md`). `evidence` and `name` are read when present and
    defaulted when not -- a corpus with no hint is a corpus where BOTH arms get no
    hint, which is parity, whereas a crash would be an outage.
    """
    gold = getattr(task, "gold_sql", None) or getattr(task, "query", None) or ""
    db_path = getattr(task, "db_path", None)
    if not db_path:
        raise ValueError(f"task {task!r} has no db_path; both arms need the database")
    return TaskView(
        name=str(getattr(task, "name", None) or getattr(task, "db_id", "")
                 or "unnamed"),
        question=str(getattr(task, "question", "")),
        db_path=str(db_path),
        gold_sql=str(gold),
        tier=str(getattr(task, "tier", None) or "unknown"),
        evidence=str(getattr(task, "evidence", "") or ""),
    )


# ------------------------------------------------------------------------------------
# The shared channel: one read-only, capped SQL action, reached two ways.
# ------------------------------------------------------------------------------------

def connect_readonly(db_path: str) -> sqlite3.Connection:
    """Open the task database read-only and guard SQL-driven external file access.

    `mode=ro` rather than trusting the query text: a channel documented as read-only
    that is enforced by a prompt is enforced by nothing, and a task database mutated by
    one rollout is a task the next rollout answers against different data. The shared
    authorizer additionally denies ATTACH (including VACUUM INTO) and known external
    file/extension functions. The bash wrapper uses `-readonly -safe`. Neither action
    is an OS sandbox or restricts the wider bash shell or ordinary SQLite temporary IO.
    """
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"no sqlite file at {db_path}")
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    return protect_connection(conn)


def schema_text(db_path: str) -> str:
    """The database's DDL, as the identical string handed to BOTH arms.

    Read from `sqlite_master` rather than from the corpus's own description files: the
    DDL is what the database will actually answer against, and it is one string, so
    neither arm can be given a richer account of the schema than the other. That
    richness is the confound `docs/bench-taskset.md` warns about -- a prompt-content
    difference reads as a channel difference in exactly the way defect 5 did.

    Ordered by name so the string is stable across runs; `sqlite_master`'s natural order
    is creation order, which a rebuilt fixture can change.
    """
    conn = connect_readonly(db_path)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
            "ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return "\n\n".join(str(row[0]).strip() for row in rows)


def make_execute_sql(db_path: str,
                     max_rows: int = MAX_ROWS) -> Callable[..., list[dict[str, Any]]]:
    """The PTC arm's SQL action, as a catalog entry callable from inside the program.

    Returns rows as a list of dicts -- `rows_from_cursor`'s shape, with duplicate
    column names suffixed so a two-table join cannot silently lose half its columns.
    The program owns `len`, `sorted`, `max`, `sum`, subscripting and `for`, so this is
    data it can iterate, index, aggregate and compare: the thing the run-1 catalog
    returned a JSON string instead of.

    Keyword-only, matching `harness.py::_bridge` and what the system prompt tells the
    model. A locally registered tool that quietly accepted positionals would teach the
    opposite of the prompt, which is run 1's defect 3 (34 of 54 PTC tool failures).

    A failed query raises `ProgramRejected` carrying sqlite's own message.
    `harness.py` renders that as `rejected: <message>`, so the model reads the same
    text sqlite would have printed on the bash arm's stderr.
    """

    def execute_sql(*, query: str) -> list[dict[str, Any]]:
        conn = connect_readonly(db_path)
        try:
            try:
                cursor = conn.execute(query)
            except sqlite3.Error as exc:
                raise ProgramRejected(f"{type(exc).__name__}: {exc}") from None
            return rows_from_cursor(cursor, max_rows)
        finally:
            conn.close()

    execute_sql.__name__ = SQL_TOOL
    return execute_sql


def _sh_single(value: str) -> str:
    """`value` as a POSIX single-quoted shell word."""
    return "'" + value.replace("'", "'\\''") + "'"


def wrapper_script(db_path: str, max_rows: int = MAX_ROWS) -> str:
    """The bash arm's SQL action, as a POSIX shell script.

    **Why a wrapper and not bare `sqlite3 <db> "<query>"`.** The brief's command form is
    preserved -- it is the last line of this script, verbatim, with sqlite3's own
    `-readonly -safe` and `-list -header` -- but reached bare it is an *uncapped* channel. The
    PTC arm refuses at `MAX_ROWS`; an arm whose observation is instead truncated by a
    context limit it is never told about has more information on some tasks and less on
    others, and neither arm would know it happened. That is defect 5 inverted, so the
    wrapper removes it: same threshold, same refusal text, from `over_cap_message`
    rather than from a second string literal that could drift.

    The cap is checked twice, cheapest-first:

    * `SELECT COUNT(*) FROM (<query>)` is exact and mirrors what
      `rows_from_cursor` does with `fetchmany(max_rows + 1)` -- it decides before the
      rows are delivered. When the query cannot be wrapped as a subquery the probe
      fails and is skipped rather than being treated as a refusal.
    * A line count over the rendered output then catches whatever the probe could not
      wrap. It can refuse *early* on a cell containing a newline, which is a
      conservative divergence rather than a silent truncation, and `-list` output is
      the only thing available to count once the subquery route is gone.

    Trailing semicolons and whitespace are stripped, matching
    `bench.score.extract_sql`, so a prediction the scorer will accept is a query this
    channel will run.
    """
    return "\n".join([
        "#!/bin/sh",
        "# Generated by ptc/sql_arms.py::wrapper_script -- the bash arm's SQL action.",
        "set -u",
        f"DB={_sh_single(str(db_path))}",
        f"MAX={int(max_rows)}",
        f"REFUSAL={_sh_single(over_cap_message(max_rows))}",
        'if [ "$#" -ne 1 ]; then',
        '  echo "usage: ' + SQL_TOOL + ' \\"<SQL query>\\"" >&2',
        "  exit 2",
        "fi",
        "# Matches bench.score.extract_sql, and lets the COUNT probe wrap the query.",
        "Q=$(printf '%s' \"$1\" | sed -e 's/[[:space:];]*$//')",
        'n=$(sqlite3 -readonly -safe "$DB" "SELECT COUNT(*) FROM ($Q)" 2>/dev/null) || n=""',
        'case "$n" in',
        "  '' | *[!0-9]* ) ;;   # not wrappable as a subquery: fall through to the guard",
        '  * ) if [ "$n" -gt "$MAX" ]; then printf \'%s\\n\' "$REFUSAL" >&2; exit 1; fi ;;',
        "esac",
        'out=$(sqlite3 -readonly -safe -list -header "$DB" "$Q" 2>&1) || {',
        "  printf '%s\\n' \"$out\" >&2",
        "  exit 1",
        "}",
        "# One header line, so MAX rows render as MAX + 1 lines.",
        'if [ "$(printf \'%s\\n\' "$out" | wc -l)" -gt "$((MAX + 1))" ]; then',
        "  printf '%s\\n' \"$REFUSAL\" >&2",
        "  exit 1",
        "fi",
        "printf '%s\\n' \"$out\"",
        "",
    ])


def install_wrapper(bindir: str | Path, db_path: str,
                    max_rows: int = MAX_ROWS) -> Path:
    """Write the wrapper into `bindir` under `SQL_TOOL` and make it executable.

    Returns the script path. Put `bindir` on the bash arm's PATH and the arm's action
    is `execute_sql "<query>"` -- the same name the PTC arm's catalog entry carries, so
    `SHARED_PROMPT` can name the action once for both arms.

    **Written to a temporary name and renamed into place.** `write_text` truncates
    first, so a reader that opens the script mid-write runs a partial file: eight
    threads sharing one `bindir` with a parallel differential sweep observed 63 of 480
    calls return empty stdout with exit code 0, which is a divergence manufactured by
    the rig and indistinguishable from a finding. `rename` within a directory is atomic
    on POSIX, so a concurrent reader sees either the old script or the new one and
    never neither.
    """
    bindir = Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / SQL_TOOL
    staging = bindir / f".{SQL_TOOL}.{os.getpid()}.{threading.get_ident()}"
    staging.write_text(wrapper_script(db_path, max_rows))
    staging.chmod(0o755)
    staging.replace(script)
    return script


@dataclass(frozen=True)
class BashResult:
    """One bash-arm action's observation: exactly what the shell handed back."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def observation(self) -> str:
        """What the model reads. stderr included, because that is where the refusal and
        sqlite's error text arrive and an arm that cannot see its own failures is an arm
        with less information, not a tidier one."""
        return "\n".join(part for part in (self.stdout.strip(),
                                           self.stderr.strip()) if part)


def run_bash_sql(db_path: str, query: str, *, bindir: str | Path,
                 max_rows: int = MAX_ROWS,
                 command: str | None = None,
                 timeout: float = WRAPPER_TIMEOUT) -> BashResult:
    """Run one bash-arm action against `db_path`.

    `command` defaults to the single action the prompt describes,
    `execute_sql "<query>"`; pass a full shell line to exercise the arm's wider shell
    affordances (pipes, `sort`, `||`), which is what the capability probes do.

    The wrapper is installed into `bindir` and `bindir` is PREPENDED to PATH rather
    than replacing it: the bash arm's channel is a real shell with its real utilities,
    and handing it a PATH with no `sort` would be a parity test rigged in PTC's favour.
    """
    install_wrapper(bindir, db_path, max_rows)
    if command is None:
        command = f"{SQL_TOOL} {_sh_single(query)}"
    env = dict(os.environ)
    env["PATH"] = f"{Path(bindir)}{os.pathsep}{env.get('PATH', '')}"
    proc = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                          text=True, timeout=timeout, env=env, cwd=str(bindir))
    return BashResult(proc.stdout, proc.stderr, proc.returncode)


# ------------------------------------------------------------------------------------
# Prompt text: one body, two channel paragraphs.
# ------------------------------------------------------------------------------------

SHARED_PROMPT = (
    "You are answering a question against a SQLite database by writing SQL.\n\n"
    "Schema:\n{schema}\n\n"
    "Question: {question}\n"
    "{evidence_block}"
    "You have an action named `{tool}` that runs one read-only SQL query against this "
    "database and gives you its rows. {cap} Rows come back with duplicate column names "
    "suffixed `_2`, `_3` and so on, so a query selecting two columns called `name` "
    "gives you `name` and `name_2` rather than losing one.\n\n"
    "Explore with as many queries as you need, then give your final answer as a single "
    "SQL query in a ```sql fenced block."
)
"""Everything both arms are told, with no mention of how the action is reached.

The channel paragraph is the ONLY per-arm text. `test_sql_arms.py` derives that rather
than trusting it: it renders both prompts, removes the two channel strings, and fails
unless what is left is byte-identical. An arm told more about its own channel, its own
cap, or the task is the confound defect 5 turned out to be, and prose asserting
otherwise is what let it ship.
"""

BASH_CHANNEL = (
    "\n\nTo take an action, run a shell command. The SQL action is the command "
    "`{tool} \"<your query>\"`. Its rows arrive on stdout as `-list -header` text: a "
    "header line of column names, then one line per row, columns separated by `|`. A "
    "failed query prints SQLite's error instead and the command exits non-zero."
)
"""How the bash arm reaches the action: a command, output read as text."""

PTC_CHANNEL = (
    "\n\nTo take an action, write a Python program and submit it with the "
    "`run_program` tool. The SQL action is the catalog function "
    "`{tool}(query=...)`, callable from inside your program. It returns DATA, not "
    "text: a list of dicts, one per row, keyed on column name. Subscript it, iterate "
    "it, and use `len`, `sorted`, `max`, `min`, `sum` and `join(sep=..., parts=...)` "
    "on it directly -- do not try to parse it. Use `print(...)` to report what you "
    "need to see, because the program's printed output is all you get back."
)
"""How the PTC arm reaches the action: a catalog call inside a program, output as data.

The sentence about the return being DATA is the one run 1 could not honestly have
written. `make_execute_sql` is what makes it true."""

_CAP_SENTENCE = (
    "A query returning more than {max_rows} rows is refused with a message telling you "
    "so, rather than truncated, so aggregate in SQL (COUNT, SUM, MAX, GROUP BY) or add "
    "a LIMIT when a result would be large."
)


def prompt_for(view: TaskView, arm: str, *, schema: str | None = None,
               max_rows: int = MAX_ROWS) -> str:
    """The full prompt one arm receives for one task.

    `schema` is read from the database when not supplied, which is the normal path;
    passing it in lets a caller render both arms' prompts against ONE schema string and
    so removes the last way the two could diverge.
    """
    if arm not in ("bash", "ptc"):
        raise ValueError(f"arm must be 'bash' or 'ptc', got {arm!r}")
    if schema is None:
        schema = schema_text(view.db_path)
    body = SHARED_PROMPT.format(
        schema=schema,
        question=view.question,
        # Absent evidence leaves no trace at all. A literal "Evidence: " with nothing
        # after it would be a visible difference between corpora rather than between
        # arms, but it is still text neither arm can use.
        evidence_block=f"Evidence: {view.evidence}\n\n" if view.evidence else "\n",
        tool=SQL_TOOL,
        cap=_CAP_SENTENCE.format(max_rows=max_rows),
    )
    channel = BASH_CHANNEL if arm == "bash" else PTC_CHANNEL
    return body + channel.format(tool=SQL_TOOL)


# ------------------------------------------------------------------------------------
# The probe fixture and the two probe runners.
# ------------------------------------------------------------------------------------

PROBE_SCHEMA = """
CREATE TABLE dept (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE emp (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    dept_id INTEGER NOT NULL REFERENCES dept(id),
    salary  INTEGER
);

INSERT INTO dept (id, name) VALUES (1, 'Sales'), (2, 'Eng'), (3, 'Ops');

INSERT INTO emp (id, name, dept_id, salary) VALUES
    (1, 'Ada',  2, 120),
    (2, 'Bob',  1,  90),
    (3, 'Cy',   2, 110),
    (4, 'Dee',  1,  95),
    (5, 'Eve',  3,  80);
"""
"""The probe database, as DDL built by code at test time.

Deliberately NOT `bench/fixtures/schema.sql`. The parity contract is a property of the
two ARMS and must be checkable wherever `ptc` imports, so this module owns no
dependency on `bench/**` beyond `adapt_task`'s duck typing. Small on purpose, and
shaped for the probes that need it: two joinable tables so `SELECT e.name, d.name`
produces the duplicate-column case, a numeric column so a client-side aggregate is not
the same number as a count, and five employees so a `max_rows` of 2 is a real overflow.
"""

PROBE_DB_ROWS = 5
"""Employees in the probe database. The cap probe's threshold is derived from this
rather than written twice, so adding a row cannot silently stop that probe overflowing.
"""


def build_probe_db(db_path: str | Path) -> Path:
    """Create the probe database by executing `PROBE_SCHEMA`. No binary in the repo."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(PROBE_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return db_path


def sql_catalog(db_path: str, max_rows: int = MAX_ROWS,
                observe: Callable[..., None] | None = None) -> Catalog:
    """The catalog the PTC arm hands a program for a SQL task.

    The ONE place the PTC arm's action space is assembled, so the probes measure the
    real arm rather than a catalog the test built for itself. Three parts and no
    others: the task's SQL action, `sql_runtime.SQL_PRIMITIVES`, and the `print`
    shadow `harness.py` installs under `OBSERVE` to capture output per program.
    """
    tools: dict[str, Callable[..., Any]] = {
        SQL_TOOL: make_execute_sql(db_path, max_rows),
        **SQL_PRIMITIVES,
    }
    if observe is not None:
        # Shadow Python's builtin without importing the harness frameworks.
        tools["print"] = observe
    return Catalog(tools=tools)


@dataclass(frozen=True)
class PtcResult:
    """One PTC-arm action's observation, rendered as `harness.py` renders it."""

    observation: str
    rejected: bool


def run_ptc_program(program: str, db_path: str, *,
                    max_rows: int = MAX_ROWS) -> PtcResult:
    """Run one PTC-arm action and return what the model would read.

    Mirrors `harness.py::_loop`'s three outcomes exactly -- printed output, `rejected:
    <why>`, `error: <Type>: <why>` -- because a probe that reported a rejection as a
    crash would measure this function's error handling rather than the arm's.

    `ptc.runtime.run` is imported here rather than at module scope so that a caller who
    only wants `wrapper_script` or the contract data pays for neither it nor, through
    `sql_catalog`, `ptc.harness`.
    """
    from ptc.runtime import run as run_restricted

    printed: list[str] = []

    def observe(*parts: Any, sep: str = " ", end: str = "\n") -> None:
        printed.append(sep.join(str(part) for part in parts))

    catalog = sql_catalog(db_path, max_rows, observe)
    try:
        run_restricted(program, catalog)
    except ProgramRejected as exc:
        return PtcResult(f"rejected: {exc}", True)
    except Exception as exc:  # the program itself raised
        return PtcResult(f"error: {type(exc).__name__}: {exc}", True)
    return PtcResult("\n".join(printed) or "ok (the program printed nothing)", False)


# ------------------------------------------------------------------------------------
# The parity contract, as data.
# ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Capability:
    """One ability the declared SQL task class needs, with an executable probe per arm.

    This is the unit that makes the parity guard a measurement. `why` says what in the
    task class needs the ability; `bash` and `ptc` are the two probes; `expected` is the
    answer both must produce. The test runs both probes and fails the capability when
    one arm produces the answer and the other does not -- so an arm losing a primitive,
    or gaining one the other lacks, turns red without anyone remembering to update a
    list.

    Note what `expected` is NOT: it is not the raw channel output. bash reads `-list`
    text and PTC reads dicts, and demanding byte-identical observations would be
    demanding the channels be the same channel. The comparison is on the ANSWER each
    arm can reach, which is the thing a task scores on.
    """

    name: str
    why: str
    bash: str
    """A shell line, run with the wrapper on PATH."""
    ptc: str
    """A program, run through `runtime.run` against `sql_catalog`."""
    expected: str
    match: str = "tokens"
    """`tokens` -- whitespace-normalised equality, the default, used wherever the probe
    computes an answer. `contains` -- the expected text appears in the observation, used
    only for the two probes whose subject is a CHANNEL MESSAGE (the over-cap refusal and
    a query error), where the arms wrap the same message in their own framing: sqlite's
    CLI says `Parse error in 5th command line argument:` and the sandbox says
    `rejected: OperationalError:`. The message is the information; the framing is the
    channel."""
    max_rows: int = MAX_ROWS
    """Overridden only by the cap probe, which needs a threshold the fixture overflows."""


_CAP_PROBE_MAX = PROBE_DB_ROWS - 1
"""The cap probe's threshold: one less than the fixture has rows, derived so that
adding a row to `PROBE_SCHEMA` cannot quietly stop the probe overflowing."""


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        name="run_query",
        why="every task in the class begins by running a query and seeing its result.",
        bash='execute_sql "SELECT COUNT(*) FROM emp" | tail -n +2',
        ptc='rows = execute_sql(query="SELECT COUNT(*) FROM emp")\n'
            'print(rows[0]["COUNT(*)"])',
        expected="5",
    ),
    Capability(
        name="row_count",
        why="'how many X' is answerable in SQL, but checking how many rows came back is "
            "how either arm knows whether to narrow a query. An arm that cannot count "
            "its own result is an arm guessing whether it saw everything.",
        bash='execute_sql "SELECT name FROM emp" | tail -n +2 | wc -l',
        ptc='print(len(execute_sql(query="SELECT name FROM emp")))',
        expected="5",
    ),
    Capability(
        name="cell_by_column_name",
        why="reading one named column of one row. The run-1 failure in one line: the "
            "catalog returned a JSON string and the sandbox owned no primitive to "
            "reach a field inside it, while bash read the same bytes with attention.",
        bash='execute_sql "SELECT name, salary FROM emp WHERE id = 1" '
             "| tail -n +2 | cut -d'|' -f1",
        ptc='rows = execute_sql(query="SELECT name, salary FROM emp WHERE id = 1")\n'
            'print(rows[0]["name"])',
        expected="Ada",
    ),
    Capability(
        name="iterate_rows",
        why="visiting every row of a result, which any per-row check needs.",
        bash='execute_sql "SELECT name FROM emp ORDER BY name" | tail -n +2 '
             '| while read -r r; do printf "%s " "$r"; done',
        ptc='for row in execute_sql(query="SELECT name FROM emp ORDER BY name"):\n'
            '    print(row["name"])',
        expected="Ada Bob Cy Dee Eve",
    ),
    Capability(
        name="aggregate_client_side",
        why="summing outside SQL. Reachable in SQL too, and that is the point: an arm "
            "that can only aggregate in SQL has to get the query right first time, "
            "while the other can check its arithmetic against the rows it already has.",
        bash='execute_sql "SELECT salary FROM emp" | tail -n +2 '
             "| awk '{s += $1} END {print s}'",
        ptc='rows = execute_sql(query="SELECT salary FROM emp")\n'
            'print(sum(row["salary"] for row in rows))',
        expected="495",
    ),
    Capability(
        name="compare_and_filter",
        why="keeping the rows that satisfy a predicate the query did not express. The "
            "comparison operators are the half of this that `runtime.ALLOWED_NODES` "
            "has to carry; the filtering is the half the catalog has to.",
        bash='execute_sql "SELECT name, salary FROM emp" | tail -n +2 '
             "| awk -F'|' '$2 > 100 {print $1}' | sort | paste -sd' ' -",
        ptc='rows = execute_sql(query="SELECT name, salary FROM emp")\n'
            'names = sorted([row["name"] for row in rows if row["salary"] > 100])\n'
            'print(join(sep=" ", parts=names))',
        expected="Ada Cy",
    ),
    Capability(
        name="sort_client_side",
        why="ordering by a key the query did not order by. Also the probe that pins the "
            "declared `lambda` asymmetry as a SPELLING difference: the sandbox refuses "
            "`key=lambda r: r['salary']` and accepts the same key written as a def, so "
            "the capability is reachable and only the syntax differs.",
        bash='execute_sql "SELECT name, salary FROM emp" | tail -n +2 '
             "| sort -t'|' -k2 -nr | head -n 1 | cut -d'|' -f1",
        ptc="def by_salary(row):\n"
            '    return row["salary"]\n'
            'rows = execute_sql(query="SELECT name, salary FROM emp")\n'
            'print(sorted(rows, key=by_salary)[-1]["name"])',
        expected="Ada",
    ),
    Capability(
        name="format_multi_value",
        why="'their names separated by single spaces' is the shape four of `ledger`'s "
            "tasks already use. bash formats it with one `tr`; the sandbox needs "
            "`sql_runtime.join`, which is why that primitive exists.",
        bash='execute_sql "SELECT name FROM emp WHERE dept_id = 2 ORDER BY name" '
             "| tail -n +2 | paste -sd' ' -",
        ptc='rows = execute_sql(query="SELECT name FROM emp WHERE dept_id = 2 '
            'ORDER BY name")\n'
            'print(join(sep=" ", parts=[row["name"] for row in rows]))',
        expected="Ada Cy",
    ),
    Capability(
        name="two_queries_one_action",
        why="combining two results without spending a turn between them. This is the "
            "axis the project measures rather than a fault, so it has to be present on "
            "BOTH arms: a bash arm that could only run one query per turn would be a "
            "comparator hobbled in PTC's favour.",
        bash='printf "%s %s" '
             '"$(execute_sql "SELECT COUNT(*) FROM emp" | tail -n +2)" '
             '"$(execute_sql "SELECT COUNT(*) FROM dept" | tail -n +2)"',
        ptc='emps = execute_sql(query="SELECT COUNT(*) FROM emp")\n'
            'depts = execute_sql(query="SELECT COUNT(*) FROM dept")\n'
            'print(emps[0]["COUNT(*)"], depts[0]["COUNT(*)"])',
        expected="5 3",
    ),
    Capability(
        name="duplicate_column_names",
        why="both columns of `SELECT e.name, d.name`, which every two-table join over "
            "similarly-named columns produces. `sqlite3 -list -header` prints "
            "`name|name` and both values; the naive `dict(zip(columns, row))` keeps one "
            "and hands the sandbox a row of length 1. A typed channel that silently "
            "drops half a join is defect 5 in a different costume, so "
            "`dedup_columns` suffixes rather than collapses and this probe is what "
            "holds it there.",
        bash='execute_sql "SELECT e.name, d.name FROM emp e '
             'JOIN dept d ON e.dept_id = d.id WHERE e.id = 1" | tail -n +2 '
             "| tr '|' ' '",
        ptc='rows = execute_sql(query="SELECT e.name, d.name FROM emp e '
            'JOIN dept d ON e.dept_id = d.id WHERE e.id = 1")\n'
            'print(rows[0]["name"], rows[0]["name_2"])',
        expected="Ada Eng",
    ),
    Capability(
        name="over_cap_refusal",
        why="a result past the cap must arrive as the SAME refusal on both arms. An arm "
            "told 'add a LIMIT' while the other is silently truncated has more "
            "information about its own channel, and a model that reads part of a result "
            "and answers confidently is what the cap exists to prevent.",
        bash='execute_sql "SELECT name FROM emp"',
        ptc='print(len(execute_sql(query="SELECT name FROM emp")))',
        expected=over_cap_message(_CAP_PROBE_MAX),
        match="contains",
        max_rows=_CAP_PROBE_MAX,
    ),
    Capability(
        name="query_error_text",
        why="seeing WHY a query failed. Both arms get sqlite's own message, so a wrong "
            "column name costs each of them one action and the same information. Only "
            "recovery within a single action differs, and that is declared.",
        bash='execute_sql "SELECT * FROM missing"',
        ptc='print(execute_sql(query="SELECT * FROM missing"))',
        expected="no such table: missing",
        match="contains",
    ),
)
"""The declared SQL task class, one entry per ability, each with a probe per arm.

Adding a capability means writing BOTH probes, which is the point: a capability one arm
can reach and the other cannot has nowhere to hide in this structure. `test_sql_arms.py`
runs every pair; `docs/harness-parity.md` renders `name` and `why` rather than
restating them."""


@dataclass(frozen=True)
class Asymmetry:
    """One gap between the arms that is known, deliberate and NOT fixed.

    `probe` is a program the sandbox must still reject (or, for
    `expect="partial_loss"`, run in a way that loses output). The probe is the whole
    point: a declared asymmetry whose limit quietly went away leaves
    `docs/harness-parity.md` describing a sandbox that no longer exists, and a declared
    asymmetry nobody probed is indistinguishable from a guess. Either way the test goes
    red and the data gets corrected rather than the prose.
    """

    name: str
    direction: str
    """Which arm the gap favours: `bash`, `ptc`, or `neither`."""
    probe: str
    expect: str = "rejected"
    """`rejected` -- `runtime.validate` must refuse the program. `partial_loss` -- the
    program runs, prints, then fails, and the observation must NOT carry what it
    printed."""

    @property
    def reason(self) -> str:
        """The prose, read from `sql_runtime` where that module owns it.

        One source. An asymmetry declared here and reasoned about there cannot drift,
        and `ASYMMETRY_REASONS` carries only the ones this module itself introduces.
        """
        return UNREACHABLE_IN_SANDBOX.get(self.name) or ASYMMETRY_REASONS[self.name]


ASYMMETRY_REASONS: dict[str, str] = {
    "partial_output_before_failure": (
        "a program that prints and then issues a failing query loses the printed "
        "output: `harness.py::_loop` replaces the observation with the error text, "
        "because a program that raised did not finish and its partial output could be "
        "half a sentence. The bash arm keeps whatever reached stdout before the failing "
        "command. Favours bash, by at most one action's partial observation, and both "
        "arms see the failure itself. Declared rather than fixed: returning partial "
        "output alongside an error would teach the model that a crashed program is a "
        "successful one, which is a worse lesson than one lost print."
    ),
    "error_message_framing": (
        "both arms receive sqlite's own message for a failed query -- `no such table: "
        "missing` -- wrapped in their channel's framing: the CLI prefixes `Parse error "
        "in 5th command line argument:` and the sandbox prefixes `rejected: "
        "OperationalError:`. The information is identical and the probe "
        "`query_error_text` holds it there; only the wrapper text differs, which is "
        "what 'modulo the channel' means. Favours neither."
    ),
}
"""Reasons for the asymmetries this module introduces, as opposed to the sandbox limits
`sql_runtime.UNREACHABLE_IN_SANDBOX` already owns."""


DECLARED_ASYMMETRIES: tuple[Asymmetry, ...] = (
    Asymmetry(
        name="try/except",
        direction="bash",
        probe='try:\n'
              '    rows = execute_sql(query="SELECT * FROM missing")\n'
              'except Exception:\n'
              '    rows = []\n'
              'print(len(rows))',
    ),
    Asymmetry(
        name="lambda",
        direction="bash",
        probe='rows = execute_sql(query="SELECT name, salary FROM emp")\n'
              'print(sorted(rows, key=lambda row: row["salary"])[-1]["name"])',
    ),
    Asymmetry(
        name="str methods",
        direction="bash",
        probe='rows = execute_sql(query="SELECT name FROM emp WHERE id = 1")\n'
              'print(rows[0]["name"].lower())',
    ),
    Asymmetry(
        name="partial_output_before_failure",
        direction="bash",
        probe='print("seen-before-the-failure")\n'
              'execute_sql(query="SELECT * FROM missing")',
        expect="partial_loss",
    ),
    Asymmetry(
        name="error_message_framing",
        direction="neither",
        # Not a limit to probe for rejection: the capability probe `query_error_text`
        # already runs this on both arms and asserts the message reaches each of them.
        # Recorded so the framing difference is declared data rather than something a
        # later reader discovers and mistakes for an information gap.
        probe="",
        expect="covered_by_capability_probe",
    ),
)
"""Every known gap between the arms, with the direction it pushes and a live probe.

The test asserts this set COVERS `sql_runtime.UNREACHABLE_IN_SANDBOX`: a sandbox limit
declared there without a probe here would be a gap nobody measured, which is how five
of run 1's nine harness faults stayed invisible."""


# ------------------------------------------------------------------------------------
# The harness-swap seam.
# ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Budget:
    """The budgets both arms must receive identically.

    Separate from the harness backend because this is the one part of an arm pair that
    is NOT a property of the harness: it is the experiment's, and it must survive a
    harness swap unchanged or the swap becomes the independent variable.

    `max_turns` is here because `compare.py:144` records what happens when it is not.
    `PTCHarnessConfig.max_turns` defaults to 8 and shadows the agent-level budget
    entirely, so a raise to 80 applied to `bash` only -- 11 of 14 PTC rollouts stopped
    at exactly 8 programs while `bash` spent up to 44 turns on the same tier. The turn
    budget had become the independent variable. A backend that cannot honour this
    struct on both arms is a backend that cannot host the comparison.
    """

    max_turns: int = 8
    max_retries: int = 0
    retry_on: tuple[str, ...] = ()
    """Exception names a whole-episode retry covers. Both names in `compare.py:190` are
    needed because the two arms report the SAME transport fault under different type
    names -- PTC owns its HTTP client so a relay timeout is `ProviderError`, while the
    bash arm's bundled runtime raises inside its own subprocess and the rig re-wraps it
    as `HarnessError`. Retryability was deciding the comparison by which arm's code
    owned the socket."""
    rollout_timeout: float = 600.0
    program_timeout: float = 5.0
    """Wall-clock seconds one PTC program may run. The bash arm's per-query equivalent
    is `WRAPPER_TIMEOUT`; they are deliberately different numbers for the reason given
    there, and a backend must preserve both rather than collapse them."""


SECOND_HARNESS_REQUIREMENTS = (
    "arm_ids() returns exactly two ids, and the PTC-side id names the arm whose single "
    "action is a program. A harness with three arms is a different experiment.",
    "model_tools(arm) returns EXACTLY ONE tool for the PTC arm, and that tool is the "
    "program entry point. Returning the SQL tool here converts the comparison into the "
    "typed-tool-calling comparator, which is the axis this project measures.",
    "model_tools(arm) raises NotImplementedError for an arm whose schemas the backend "
    "does not own, rather than inventing them.",
    "catalog(db_path, max_rows, observe) exposes the SQL action INSIDE the program, "
    "returning rows the program owns primitives to iterate, index, compare and format. "
    "Returning an unparseable string is defect 5 and invalidates the run.",
    "run_bash / run_ptc deliver the same refusal text on an over-cap result and the "
    "same database error text, because an arm told why it failed has information the "
    "other lacks.",
    "Every entry in CAPABILITIES passes on both of its arms. The parity test is "
    "parameterised over backends, so a second implementation inherits the whole guard "
    "and does not get a second, weaker test.",
    "It does NOT supply the task, the schema string, the prompt body or the budgets. A "
    "backend that could vary those could vary the comparison.",
)
"""What a second harness must supply for Step 6's swap (H4/H5).

Stated as data rather than prose because `HarnessBackend` is a Protocol: nothing in the
type system makes a conformant implementation a *comparable* one, and the gap between
those two is where run 1's +64.3 pp came from.
"""


class HarnessBackend(Protocol):
    """What a harness implementation must supply to host this arm pair.

    Step 6's cross-harness evaluation (H4/H5) needs a policy trained on one harness to
    be *evaluated* on another, which means the arm pair cannot be welded to
    `ptc.harness.PTCHarness`. Everything specific to a harness is behind this protocol
    and `PTC_V1` is the only implementation; `SECOND_HARNESS_REQUIREMENTS` states what
    a second must do, and the parity test is parameterised over backends so a second
    implementation inherits the whole guard rather than needing a second test.

    Deliberately NOT in here: the task, the schema string, the prompt body and the
    budgets. Those are the experiment's and are identical across harnesses by
    construction -- a backend that could vary them could vary the comparison.
    """

    name: str

    def arm_ids(self) -> tuple[str, str]:
        """`(bash_harness_id, ptc_harness_id)` as the rig resolves them."""
        ...

    def model_tools(self, arm: str) -> list[dict[str, Any]]:
        """The tool SCHEMAS this arm renders into the model's context.

        The PTC arm must return exactly one, `run_program`. This is where spec
        invariant 1 can actually fire: the catalog reaches the model as prompt text and
        a function inside the program, so a typed `execute_sql` schema appearing here
        would mean the arm had silently become the typed-tool-calling comparator.
        """
        ...

    def catalog(self, view: TaskView, max_rows: int,
                observe: Callable[..., None] | None) -> Catalog:
        """The PTC arm's in-program action space for this task."""
        ...

    def run_ptc(self, program: str, view: TaskView, max_rows: int) -> PtcResult:
        """Execute one PTC action and return the observation the model would read."""
        ...

    def run_bash(self, command: str, view: TaskView, max_rows: int,
                 bindir: str | Path) -> BashResult:
        """Execute one bash action and return the observation the model would read."""
        ...


class _PtcV1Backend:
    """The one implementation: `ptc.harness.PTCHarness` against verifiers' bundled bash.

    Thin on purpose. Every method here is a one-liner over something that already
    exists, which is the evidence that the seam did not require a second harness to be
    built -- only for the first one to stop being assumed.
    """

    name = "ptc-v1"

    def arm_ids(self) -> tuple[str, str]:
        return ("bash", "ptc")

    def model_tools(self, arm: str) -> list[dict[str, Any]]:
        if arm == "ptc":
            from ptc.harness import TOOLS

            # The arm's own list, not a copy of it: a test asserting `len(...) == 1`
            # against a literal written here would pass while `harness.TOOLS` grew.
            return list(TOOLS)
        if arm == "bash":
            # Supplied by verifiers' bundled bash harness, not by this repo. Returning
            # `[]` would claim the arm has no tools, which is false; the invariant under
            # test is about the PTC arm's count, and `SECOND_HARNESS_REQUIREMENTS`
            # records that a backend must be able to answer this for its bash arm too.
            raise NotImplementedError(
                "the bash arm's tool schemas come from verifiers' bundled harness; "
                "this backend does not own them"
            )
        raise ValueError(f"arm must be 'bash' or 'ptc', got {arm!r}")

    def catalog(self, view: TaskView, max_rows: int,
                observe: Callable[..., None] | None) -> Catalog:
        return sql_catalog(view.db_path, max_rows, observe)

    def run_ptc(self, program: str, view: TaskView, max_rows: int) -> PtcResult:
        return run_ptc_program(program, view.db_path, max_rows=max_rows)

    def run_bash(self, command: str, view: TaskView, max_rows: int,
                 bindir: str | Path) -> BashResult:
        return run_bash_sql(view.db_path, "", bindir=bindir, max_rows=max_rows,
                            command=command)


PTC_V1: HarnessBackend = _PtcV1Backend()
"""The current harness, as a backend. The default everywhere."""


@dataclass(frozen=True)
class ArmPair:
    """One task, rendered for both arms against one harness backend.

    Constructing this is the whole arm-building API: the schema is read once and handed
    to both prompts, the budgets are one struct shared by both arms, and the backend is
    swappable. There is no path through this module that builds one arm without the
    other, which is the structural answer to two arms drifting apart between runs.
    """

    view: TaskView
    backend: HarnessBackend
    budget: Budget
    schema: str
    bash_prompt: str
    ptc_prompt: str
    max_rows: int = MAX_ROWS

    def prompt(self, arm: str) -> str:
        return self.bash_prompt if arm == "bash" else self.ptc_prompt

    def run(self, arm: str, action: str, *, bindir: str | Path | None = None) -> str:
        """Take one action on one arm and return the observation the model would read.

        One entry point for both arms, so a caller cannot accidentally give one of them
        a different `max_rows` or a different database.
        """
        if arm == "ptc":
            return self.backend.run_ptc(action, self.view, self.max_rows).observation
        if arm == "bash":
            if bindir is None:
                raise ValueError("the bash arm needs a bindir for its wrapper script")
            return self.backend.run_bash(action, self.view, self.max_rows,
                                         bindir).observation
        raise ValueError(f"arm must be 'bash' or 'ptc', got {arm!r}")


def build_sql_arms(task: Any, *, backend: HarnessBackend = PTC_V1,
                   budget: Budget | None = None,
                   max_rows: int = MAX_ROWS) -> ArmPair:
    """Build both arms for one task. The module's entry point.

    `task` is anything `adapt_task` can read -- a `bench.task.SqlTask`, or the minimum
    documented in `docs/bench-taskset.md`. The schema is read ONCE and passed to both
    prompts, so the two cannot be rendered against different reads of the same
    database.
    """
    view = adapt_task(task)
    schema = schema_text(view.db_path)
    return ArmPair(
        view=view,
        backend=backend,
        budget=budget or Budget(),
        schema=schema,
        bash_prompt=prompt_for(view, "bash", schema=schema, max_rows=max_rows),
        ptc_prompt=prompt_for(view, "ptc", schema=schema, max_rows=max_rows),
        max_rows=max_rows,
    )
