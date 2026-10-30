"""Integration tests for the opt-in defect-report channel on the SQL arm pair.

`ptc/sql_qa.py` is the parallel worker's collector; this file owns the proof that
`ptc/sql_arms.py` binds it honestly. Every route here is real: the PTC arm runs
through `runtime.run` against the real catalog, the bash arm runs real `/bin/sh`
against real installed wrapper executables, the scorer is
`bench.score.execution_accuracy` against real SQLite bytes, and the shortcut
fixture reads a real table through both channels. Nothing is mocked.

The shell shortcut marker is declared forgeable by spec: it is public output text
with `agent_output` provenance, never an authenticated call, and this fixture is a
controlled telemetry check -- not a production gold oracle and not a detector for
arbitrary exploitation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.score import execution_accuracy  # noqa: E402
from ptc.runtime import run as run_restricted  # noqa: E402
from ptc.sql_arms import (  # noqa: E402
    BASH_CHANNEL,
    BASH_CHANNEL_REPORTING,
    PTC_CHANNEL,
    PTC_CHANNEL_REPORTING,
    PTC_V1,
    SQL_TOOL,
    build_probe_db,
    build_sql_arms,
    install_wrapper,
    make_execute_sql,
    prompt_for,
    run_bash_sql,
    run_ptc_program,
    sql_catalog,
)
from ptc.sql_qa import (  # noqa: E402  -- parallel worker's collector, fixed API
    REPORT_MARKER,
    REPORT_PROMPT,
    REPORT_TOOL,
    SHORTCUT_MARKER,
    QaChannel,
    ReportRejected,
    report_ack,
)

RECEIPT = "report received (unverified allegation; outcome unchanged)"

FIXTURE_SHORTCUT = "fixture_short_1"


@pytest.fixture()
def rig(tmp_path):
    """One probe database and one fresh wrapper directory per test."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    install_wrapper(bindir, str(db))
    return str(db), bindir


def _view(db: str):
    class _T:
        db_path = db
        question = "How many employees are there?"
        evidence = ""
        gold_sql = "SELECT COUNT(*) FROM emp"
        name = "qa-probe"
        tier = "simple"
    return _T()


def _shq(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _report_payload(kind: str, detail: str) -> str:
    return json.dumps({"kind": kind, "detail": detail}, separators=(",", ":"))


def _report_events(qa, arm: str | None = None):
    return [e for e in qa.events
            if e["type"] == "report" and (arm is None or e["arm"] == arm)]


def _shortcut_events(qa, arm: str | None = None):
    return [e for e in qa.events
            if e["type"] == "shortcut" and (arm is None or e["arm"] == arm)]


# ------------------------------------------------------------------------------
# Default path: reporting absent changes nothing.
# ------------------------------------------------------------------------------

def test_default_reporting_is_inert(rig):
    """With no `qa` anywhere: no report names in prompts or catalog, no report
    executable on the default shell's PATH, and no receipt text in observations."""
    db, bindir = rig
    pair = build_sql_arms(_view(db))
    for prompt in (pair.bash_prompt, pair.ptc_prompt):
        assert REPORT_TOOL not in prompt
        assert REPORT_MARKER not in prompt
        assert REPORT_PROMPT not in prompt
        assert "defect" not in prompt

    assert sql_catalog(db).names() == {SQL_TOOL, "join"}
    observed = sql_catalog(db, observe=lambda *a, **k: None).names()
    assert observed == {SQL_TOOL, "join", "print"}

    result = run_bash_sql(db, "SELECT COUNT(*) FROM emp", bindir=bindir)
    assert result.returncode == 0
    assert not (bindir / REPORT_TOOL).exists(), (
        "the default shell must not grow a report executable"
    )
    assert report_ack() not in result.observation
    assert RECEIPT not in result.observation

    ptc = run_ptc_program('print(len(execute_sql(query="SELECT name FROM emp")))',
                          db)
    assert not ptc.rejected and "5" in ptc.observation
    assert RECEIPT not in ptc.observation


def test_qa_prompts_differ_only_by_channel(rig):
    """The report channel's semantics are shared text; only the per-arm route to
    it differs. Same invariant shape as the SQL action's own parity test."""
    db, _ = rig
    view = _view(db)
    bash = prompt_for(view, "bash", reporting=True)
    ptc = prompt_for(view, "ptc", reporting=True)

    assert REPORT_PROMPT in bash and REPORT_PROMPT in ptc
    assert REPORT_TOOL in bash and REPORT_TOOL in ptc

    bash_channel = BASH_CHANNEL.format(tool=SQL_TOOL) + \
        BASH_CHANNEL_REPORTING.format(report=REPORT_TOOL)
    ptc_channel = PTC_CHANNEL.format(tool=SQL_TOOL) + \
        PTC_CHANNEL_REPORTING.format(report=REPORT_TOOL)
    assert bash_channel in bash and ptc_channel in ptc

    assert bash.replace(bash_channel, "") == ptc.replace(ptc_channel, "")


# ------------------------------------------------------------------------------
# The channel itself: real routes, real receipts, real failures preserved.
# ------------------------------------------------------------------------------

def test_both_real_arms_report(rig):
    """Each arm files the same allegation once and reads the same fixed receipt.
    Provenance distinguishes the trusted in-process callback from forgeable shell
    output; neither proves the claim."""
    db, bindir = rig
    qa = QaChannel()
    detail = "the question asks for a count the schema hides"

    ptc = run_ptc_program(
        f'print({REPORT_TOOL}(kind="task_defect", detail={detail!r}))',
        db, qa=qa)
    assert not ptc.rejected, ptc.observation

    bash = run_bash_sql(
        db, "", bindir=bindir, qa=qa,
        command=f"{REPORT_TOOL} {_shq(_report_payload('task_defect', detail))}")
    assert bash.returncode == 0, bash.stderr

    assert report_ack() == RECEIPT
    assert "```" not in RECEIPT
    assert RECEIPT in ptc.observation
    assert RECEIPT in bash.observation

    reports = _report_events(qa)
    assert [(e["arm"], e["kind"], e["detail"]) for e in reports] == [
        ("ptc", "task_defect", detail),
        ("bash", "task_defect", detail),
    ]
    assert all("seq" in e for e in reports)
    provenance = {e["arm"]: e["provenance"] for e in reports}
    assert provenance == {"ptc": "catalog_callback", "bash": "agent_output"}


def test_report_then_sql_error_keeps_allegation_and_error(rig):
    """A report followed by a real SQL failure in the same action preserves both:
    the allegation in the event log and the error in the observation. On the bash
    arm the receipt text and sqlite's message are both in the observation."""
    db, bindir = rig
    qa = QaChannel()

    ptc = run_ptc_program(
        f'print({REPORT_TOOL}(kind="task_defect", detail="allegation"))\n'
        'execute_sql(query="SELECT * FROM missing")', db, qa=qa)
    assert ptc.rejected and "no such table: missing" in ptc.observation
    # The printed receipt is lost with the failed program (declared asymmetry);
    # the recorded allegation is not.
    assert len(_report_events(qa, "ptc")) == 1

    bash = run_bash_sql(
        db, "", bindir=bindir, qa=qa,
        command=f"{REPORT_TOOL} {_shq(_report_payload('task_defect', 'allegation'))}"
                '; execute_sql "SELECT * FROM missing"')
    assert bash.returncode != 0
    assert RECEIPT in bash.observation
    assert "no such table: missing" in bash.observation
    assert len(_report_events(qa, "bash")) == 1


def test_report_then_later_failed_action_retains_it(rig):
    """The allegation survives a LATER action failing too: events are cumulative,
    not per-action."""
    db, bindir = rig
    qa = QaChannel()
    run_ptc_program(f'print({REPORT_TOOL}(kind="other", detail="kept"))',
                    db, qa=qa)
    failed = run_ptc_program('execute_sql(query="SELECT * FROM missing")',
                             db, qa=qa)
    assert failed.rejected and "no such table: missing" in failed.observation
    reports = _report_events(qa)
    assert len(reports) == 1 and reports[0]["detail"] == "kept"

    payload = _report_payload("other", "kept-bash")
    run_bash_sql(db, "", bindir=bindir, qa=qa,
                 command=f"{REPORT_TOOL} {_shq(payload)}")
    failed_bash = run_bash_sql(db, "", bindir=bindir, qa=qa,
                               command='execute_sql "SELECT * FROM missing"')
    assert failed_bash.returncode != 0
    assert "no such table: missing" in failed_bash.observation
    assert len(_report_events(qa, "bash")) == 1


def test_reporting_preserves_scorer_db_and_budgets(rig):
    """Independent `execution_accuracy` on correct and incorrect final SQL is
    identical with and without reporting; the database bytes and the pair's
    budgets are untouched. The scorer is the real one, not a stand-in."""
    db, bindir = rig
    db_bytes_before = hashlib.sha256(Path(db).read_bytes()).hexdigest()
    task = _view(db)

    assert execution_accuracy(task.gold_sql, task).score == 1.0
    assert execution_accuracy("SELECT COUNT(*) FROM dept", task).score == 0.0

    qa = QaChannel()
    run_ptc_program(f'print({REPORT_TOOL}(kind="task_defect", detail="noise"))',
                    db, qa=qa)
    run_bash_sql(db, "", bindir=bindir, qa=qa,
                 command=f"{REPORT_TOOL} "
                         f"{_shq(_report_payload('task_defect', 'noise'))}")

    assert execution_accuracy(task.gold_sql, task).score == 1.0
    assert execution_accuracy("SELECT COUNT(*) FROM dept", task).score == 0.0
    assert hashlib.sha256(Path(db).read_bytes()).hexdigest() == db_bytes_before

    default_pair = build_sql_arms(task)
    qa_pair = build_sql_arms(task, qa=qa)
    assert dataclasses.asdict(default_pair.budget) == \
        dataclasses.asdict(qa_pair.budget)


def test_invalid_reports_are_rejected_not_recorded(rig):
    """A malformed report is a visible refusal: the PTC program reads the same
    `rejected:` shape a refused query produces, the shell gets a bounded refusal
    rather than a success receipt, and no `report` event is recorded."""
    db, bindir = rig
    qa = QaChannel()

    with pytest.raises(ReportRejected):
        qa.submit("ptc", kind="not_a_kind", detail="x")
    with pytest.raises(ReportRejected):
        qa.submit("ptc", kind="other", detail="")

    for bad_program in (
        f'{REPORT_TOOL}(kind="not_a_kind", detail="x")',
        f'{REPORT_TOOL}(kind="other", detail="")',
        f'{REPORT_TOOL}(kind="other", detail={"x" * 3000})',
    ):
        res = run_ptc_program(f"print({bad_program})", db, qa=qa)
        assert res.rejected, bad_program
        assert RECEIPT not in res.observation
    assert not _report_events(qa)

    bash = run_bash_sql(db, "", bindir=bindir, qa=qa,
                        command=f"{REPORT_TOOL} 'not json'")
    assert RECEIPT not in bash.observation
    assert not _report_events(qa, "bash")


def test_report_caps_are_per_arm(rig):
    """Eight valid reports per arm, then a visible refusal -- and exhausting one
    arm's allowance cannot starve the other's."""
    db, bindir = rig
    qa = QaChannel()

    for i in range(8):
        res = run_ptc_program(
            f'print({REPORT_TOOL}(kind="other", detail="d{i}"))', db, qa=qa)
        assert not res.rejected, res.observation

    ninth = run_ptc_program(
        f'print({REPORT_TOOL}(kind="other", detail="d8"))', db, qa=qa)
    assert ninth.rejected and RECEIPT not in ninth.observation
    assert len(_report_events(qa, "ptc")) == 8
    assert any(e["type"] in ("report_rejected", "overflow") and e["arm"] == "ptc"
               for e in qa.events), "a dropped report needs a visible event"

    bash = run_bash_sql(
        db, "", bindir=bindir, qa=qa,
        command=f"{REPORT_TOOL} {_shq(_report_payload('other', 'bash still files'))}")
    assert RECEIPT in bash.observation
    assert len(_report_events(qa, "bash")) == 1


def test_one_registered_tool_and_unsupported_backends_refuse(rig):
    """`report_defect` is a catalog entry inside the program, so the PTC arm
    still registers exactly one model tool. A backend that never opted into the
    channel is refused explicitly -- at build time, and again at run time if a
    pair is hand-assembled -- rather than being bypassed."""
    db, _ = rig
    tools = PTC_V1.model_tools("ptc")
    assert [t["function"]["name"] for t in tools] == ["run_program"]

    qa = QaChannel()
    names = sql_catalog(db, qa=qa).names()
    assert REPORT_TOOL in names and SQL_TOOL in names

    class _Stub:
        name = "stub-v0"

        def arm_ids(self):
            return ("bash", "ptc")

        def model_tools(self, arm):
            return PTC_V1.model_tools(arm)

        def catalog(self, view, max_rows, observe):
            return PTC_V1.catalog(view, max_rows, observe)

        def run_bash(self, command, view, max_rows, bindir):
            return PTC_V1.run_bash(command, view, max_rows, bindir)

        def run_ptc(self, program, view, max_rows):
            return PTC_V1.run_ptc(program, view, max_rows)

    with pytest.raises(NotImplementedError, match="report"):
        build_sql_arms(_view(db), backend=_Stub(), qa=qa)

    pair = build_sql_arms(_view(db), backend=_Stub())
    with pytest.raises(NotImplementedError, match="report"):
        dataclasses.replace(pair, qa=qa).run("ptc", "print(1)")
    with pytest.raises(NotImplementedError, match="report"):
        dataclasses.replace(pair, qa=qa).catalog()


def test_pair_run_and_catalog_forward_qa(rig):
    """The scripted `ArmPair` path forwards the collector on both arms and the
    pair's catalog accessor returns the catalog the arm really runs -- so the
    QA-enabled prompt cannot promise a missing primitive."""
    db, bindir = rig
    qa = QaChannel()
    pair = build_sql_arms(_view(db), qa=qa)

    assert pair.reporting
    assert REPORT_PROMPT in pair.bash_prompt and REPORT_PROMPT in pair.ptc_prompt
    assert REPORT_TOOL in pair.catalog().names()

    obs = pair.run(
        "ptc", f'print({REPORT_TOOL}(kind="environment_defect", detail="d"))')
    assert RECEIPT in obs

    obs = pair.run(
        "bash",
        f"{REPORT_TOOL} {_shq(_report_payload('environment_defect', 'd'))}",
        bindir=bindir)
    assert RECEIPT in obs

    assert {e["arm"] for e in _report_events(qa)} == {"ptc", "bash"}


def test_qa_forwarding_reaches_catalog_and_shell(rig):
    """Intended RED: drop `qa` forwarding at any seam and this goes red --
    `report_defect` becomes an unknown catalog name (`rejected: unknown name
    ...`) and the shell executable is a 127, not a receipt."""
    db, bindir = rig
    qa = QaChannel()

    assert REPORT_TOOL in sql_catalog(db, qa=qa).names()
    res = run_ptc_program(f'{REPORT_TOOL}(kind="other", detail="d")',
                          db, qa=qa)
    assert not res.rejected, res.observation
    assert "unknown name" not in res.observation

    run_bash_sql(db, "", bindir=bindir, qa=qa, command="true")
    assert (bindir / REPORT_TOOL).exists()
    res = run_bash_sql(db, "", bindir=bindir, qa=qa,
                       command=f"{REPORT_TOOL} "
                               f"{_shq(_report_payload('other', 'd'))}")
    assert res.returncode == 0, res.stderr
    assert RECEIPT in res.observation


# ------------------------------------------------------------------------------
# The controlled shortcut fixture: real SQLite through both real routes.
# ------------------------------------------------------------------------------

def test_real_shortcut_fixture(rig):
    """A test-owned catalog callable performs a REAL read of the fixture table
    through the real read-only channel and only then invokes the host's
    `record_shortcut`; a test-owned shell executable does the same read through
    real `sqlite3` and emits the public marker. Each invocation records exactly
    one event; three repeats produce three. Comments and strings that merely
    mention the ID produce zero."""
    db, bindir = rig
    qa = QaChannel(shortcut_ids=(FIXTURE_SHORTCUT,))
    execute_sql = make_execute_sql(db)

    def fixture_answer():
        rows = execute_sql(query="SELECT name FROM emp WHERE id = 1")
        # Trusted host-side record, AFTER the helper's actual read -- this
        # callback is what makes the fixture controlled telemetry rather than
        # output parsing.
        qa.record_shortcut("ptc", FIXTURE_SHORTCUT,
                           provenance="catalog_callback")
        return rows[0]["name"]

    printed: list[str] = []
    catalog = sql_catalog(
        db, observe=lambda *a, **k: printed.append(" ".join(map(str, a))), qa=qa)
    catalog.tools["fixture_answer"] = fixture_answer
    for _ in range(3):
        run_restricted("print(fixture_answer())", catalog)
    assert printed == ["Ada"] * 3

    helper = bindir / "fixture_probe"
    helper.write_text("\n".join([
        "#!/bin/sh",
        "set -eu",
        f"# emits the fixture id ({FIXTURE_SHORTCUT}) only after a real read",
        f'name=$(sqlite3 -readonly -safe {_shq(db)} '
        '"SELECT name FROM emp WHERE id = 1")',
        f'printf \'%s%s\\n\' {_shq(SHORTCUT_MARKER)} {_shq(FIXTURE_SHORTCUT)}',
        'printf \'%s\\n\' "$name"',
        "",
    ]))
    helper.chmod(0o755)
    for _ in range(3):
        res = run_bash_sql(db, "", bindir=bindir, qa=qa, command="fixture_probe")
        assert res.returncode == 0, res.stderr
        assert "Ada" in res.stdout

    ptc_events = _shortcut_events(qa, "ptc")
    bash_events = _shortcut_events(qa, "bash")
    assert len(ptc_events) == 3 and len(bash_events) == 3
    for e in ptc_events:
        assert e["shortcut_id"] == FIXTURE_SHORTCUT
        assert e["provenance"] == "catalog_callback"
    for e in bash_events:
        assert e["shortcut_id"] == FIXTURE_SHORTCUT
        assert e["provenance"] == "agent_output"

    # Mentions of the ID that never emit the marker line record nothing.
    before = len(_shortcut_events(qa))
    run_bash_sql(db, "", bindir=bindir, qa=qa,
                 command=f"echo '# helper id was {FIXTURE_SHORTCUT}'; "
                         f"echo {FIXTURE_SHORTCUT}")
    run_restricted(f'print("{FIXTURE_SHORTCUT}")', catalog)
    run_restricted(f"# {FIXTURE_SHORTCUT}\nprint('done')", catalog)
    assert len(_shortcut_events(qa)) == before


def test_shell_marker_is_forgeable_agent_output(rig):
    """A bare `echo` of the marker line IS a valid marker by design -- the
    provenance field says `agent_output` instead of pretending otherwise. An ID
    outside the caller's allowlist is not recorded as a shortcut."""
    db, bindir = rig
    qa = QaChannel(shortcut_ids=(FIXTURE_SHORTCUT,))

    res = run_bash_sql(db, "", bindir=bindir, qa=qa,
                       command=f"echo {_shq(SHORTCUT_MARKER + FIXTURE_SHORTCUT)}")
    assert res.returncode == 0
    events = _shortcut_events(qa, "bash")
    assert len(events) == 1
    assert events[0]["provenance"] == "agent_output"
    assert events[0]["shortcut_id"] == FIXTURE_SHORTCUT

    run_bash_sql(db, "", bindir=bindir, qa=qa,
                 command=f"echo {_shq(SHORTCUT_MARKER + 'not-allowlisted')}")
    assert not any(e["type"] == "shortcut" and e["shortcut_id"] == "not-allowlisted"
                   for e in qa.events)


def test_export_is_bounded_and_stable(rig):
    """`export()` is a canonical snapshot: stable across calls, parseable, and
    inside the 64 KiB bound."""
    db, _ = rig
    qa = QaChannel()
    run_ptc_program(f'print({REPORT_TOOL}(kind="task_defect", detail="x"))',
                    db, qa=qa)
    blob = qa.export()
    assert isinstance(blob, bytes)
    assert len(blob) <= 65536
    assert blob == qa.export()
    assert isinstance(json.loads(blob), (list, dict))
    assert b"task_defect" in blob


# ------------------------------------------------------------------------------
# The default native closure: the optional module is genuinely optional.
# ------------------------------------------------------------------------------

def test_default_native_import_closure(tmp_path):
    """Stage ONLY the original native files -- no `ptc/sql_qa.py` -- and run the
    reporting-disabled route in a fresh interpreter. If any default path
    imported the optional module eagerly, this fails on `ModuleNotFoundError`."""
    src = Path(__file__).resolve().parent
    pkg = tmp_path / "ptc"
    pkg.mkdir()
    for name in ("__init__.py", "runtime.py", "sqlite_safety.py",
                 "sql_runtime.py", "sql_arms.py"):
        shutil.copy2(src / name, pkg / name)
    assert not (pkg / "sql_qa.py").exists()

    driver = tmp_path / "drive.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "import ptc.sql_arms as arms\n"
        "db = arms.build_probe_db(sys.argv[1])\n"
        "cat = arms.sql_catalog(str(db))\n"
        "assert sorted(cat.names()) == ['execute_sql', 'join'], cat.names()\n"
        'prog = \'print(len(execute_sql(query="SELECT name FROM emp")))\'\n'
        "obs = arms.run_ptc_program(prog, str(db))\n"
        "assert not obs.rejected and '5' in obs.observation, obs.observation\n"
        "import types\n"
        "task = types.SimpleNamespace(db_path=str(db), question='q',\n"
        "                             gold_sql='SELECT 1', name='n')\n"
        "pair = arms.build_sql_arms(task)\n"
        "assert 'report_defect' not in pair.bash_prompt\n"
        "assert 'report_defect' not in pair.ptc_prompt\n"
        "print('NATIVE-CLOSURE-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-B", str(driver), str(tmp_path / "probe.sqlite")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "NATIVE-CLOSURE-OK" in proc.stdout
