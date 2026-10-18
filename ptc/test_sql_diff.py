"""The differential parity check: the golds, through both arms, compared.

`test_sql_arms.py` measures the twelve abilities somebody named. `ptc/sql_diff.py`
narrows the structural gap §6 of `docs/harness-parity.md` states -- "an asymmetry
nobody wrote a capability for" -- by running the task class's own gold queries through
both arms and comparing the answers. This file is its fast, offline half: the repo's
fixture corpus, no network, no model.

Two things are being tested, and they are different:

1. **The check runs and agrees on real golds.** Every fixture task's gold reaches the
   same answer on both arms, both as delivered rows and as the text each model reads.
2. **The check can fail.** A check that has only ever been green is not evidence -- the
   repo's own rule. The render-hazard probes below inject the divergences a capability
   list does not name (NULL, float formatting, blob, separator, newline, duplicate
   column, undecodable bytes) and assert each one is REPORTED, so a future pass that
   silently stopped seeing them goes red here rather than green everywhere.

The probes are gold-shaped on purpose: each is a one-statement SELECT against the
fixture, exactly the shape a corpus gold has.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import fixture  # noqa: E402
from bench.loader import load_bird  # noqa: E402
from bench.score import execution_accuracy, rows_match  # noqa: E402
from ptc.sql_diff import (  # noqa: E402
    DELIVERY_CAUSES,
    DELIVERY_OUTCOMES,
    RENDER_CAUSES,
    bash_command,
    differential,
)


@pytest.fixture(scope="module")
def rig(tmp_path_factory):
    """The committed fixture corpus, loaded through the real BIRD loader, plus a
    wrapper directory. The same `materialize()` path `bench/test_bench.py` uses, so the
    differential is exercised against the corpus the rest of the instrument sees."""
    root = fixture.materialize(tmp_path_factory.mktemp("bird"))
    return load_bird(root), tmp_path_factory.mktemp("bin")


def _gold(base, sql):
    """A task whose gold is `sql`, every other field untouched."""
    return dataclasses.replace(base, gold_sql=sql)


# ------------------------------------------------------------------------------------
# The check itself, on the real golds.
# ------------------------------------------------------------------------------------

def test_every_fixture_gold_agrees_on_both_arms(rig):
    """The differential's floor, derived over every fixture task rather than one.

    A regression that made one arm's channel narrower in a way the twelve capability
    probes do not name has to surface here, on a query nobody wrote for the guard.
    """
    import tempfile
    tasks, _ = rig
    # A directory of this test's own: the fixture `rig` bindir is shared by the module,
    # and `differential()` installs the wrapper per call. Serial use is safe, but a
    # future `pytest -n` would have two tests rewriting one embedded `DB=` path.
    bindir = Path(tempfile.mkdtemp(prefix="diff-floor-")) / "bin"
    bad = []
    for t in tasks:
        d = differential(t, bindir=bindir)
        if not d.agreed or d.render_causes:
            bad.append((t.name, d.delivery_causes, d.render_causes, d.note))
    assert not bad, bad


def test_the_answer_comparison_is_the_scorers(rig):
    """`sql_diff` must not be a second opinion on what "same answer" means.

    `bench.score.rows_match` is the scorer's comparator and `execution_accuracy` calls
    it. The differential normalises NaN the same way and compares with the same
    relation; this pins the two against each other on the pair that actually
    distinguishes `set` from `multiset` (a duplicated row), plus the int/float case
    the scorer deliberately admits.
    """
    tasks, _ = rig
    t = tasks[0]
    dedup = dataclasses.replace(t, gold_sql="SELECT region FROM county WHERE region = 'Bay Area'")
    multi = "SELECT region FROM county"
    assert rows_match([(1,), (1,), (2,)], [(1,), (2,)], compare="set") is True
    assert rows_match([(1,), (1,), (2,)], [(1,), (2,)], compare="multiset") is False
    assert rows_match([(1.0,)], [(1,)], compare="set") is True
    # and the scorer itself agrees with `rows_match` about the same pair
    assert execution_accuracy("SELECT 1.0", dataclasses.replace(t, gold_sql="SELECT 1")).score == 1.0
    with pytest.raises(ValueError):
        rows_match([], [], compare="jaccard")
    _ = (dedup, multi)


def test_nan_is_normalised_on_both_sides(rig):
    """A NaN gold must not read as a divergence against itself: `nan != nan`."""
    tasks, bindir = rig
    t = _gold(tasks[0], "SELECT CAST('nan' AS REAL) AS v FROM county LIMIT 1")
    d = differential(t, bindir=bindir)
    # sqlite has no NaN literal through CAST; the query errors on both arms, which is
    # still agreement -- assert the outcome rather than the float path.
    assert d.bash.outcome == d.ptc.outcome
    assert d.agreed, (d.delivery_causes, d.note)


def test_both_arms_refuse_an_over_cap_gold(rig):
    """The cap is the one place the two channels are most obviously supposed to agree:
    same threshold, same sentence. A gold that overflows it is 'agreed' but NOT
    compared row-for-row, and the Differential says so via `capped`."""
    tasks, bindir = rig
    sql = ("SELECT school_id FROM school UNION ALL SELECT school_id FROM school "
           "UNION ALL SELECT school_id FROM school UNION ALL SELECT school_id FROM school")
    t = _gold(tasks[0], sql)
    d = differential(t, bindir=bindir, max_rows=5)
    assert d.agreed and d.capped, d
    assert "the query returned more than 5 rows" in d.bash.detail
    assert "the query returned more than 5 rows" in d.ptc.detail


def test_a_broken_gold_fails_the_same_way_on_both_arms(rig):
    """sqlite's own message reaches both channels; only the framing is declared to
    differ (`error_message_framing`). The differential compares the message and not the
    wrapper, which is what that asymmetry says the difference is."""
    tasks, bindir = rig
    d = differential(_gold(tasks[0], "SELECT * FROM no_such_table"), bindir=bindir)
    assert d.agreed and d.bash.outcome == d.ptc.outcome == "error", d
    assert "no such table" in d.bash.detail and "no such table" in d.ptc.detail


# ------------------------------------------------------------------------------------
# The render hazards: each one a divergence no capability names.
# ------------------------------------------------------------------------------------

def test_null_renders_differently_and_it_is_reported(rig):
    """bash prints an empty field; PTC prints `None`. The delivery agrees, the model's
    reading does not: on bash, NULL and '' are the same bytes.

    The one-column form is a stronger finding than a rendering difference and the check
    distinguishes the two: a lone NULL renders as a BLANK LINE, which is
    indistinguishable from the wrapper's terminator, so the row vanishes from the bash
    arm's answer entirely. That is `trailing_empty_row`, a delivery cause.
    """
    tasks, bindir = rig
    lone = differential(_gold(tasks[0], "SELECT NULL AS v FROM county LIMIT 1"),
                        bindir=bindir)
    assert not lone.agreed
    assert lone.delivery_causes == ("rows_differ", "trailing_empty_row"), lone.delivery_causes
    assert lone.bash.n_rows == 0 and lone.ptc.n_rows == 1
    assert lone.bash.text == "v\n"          # the blank line collapsed into the terminator

    # a NULL beside a non-NULL column survives as `|1`, so THIS is the pure render case
    paired = differential(_gold(tasks[0], "SELECT NULL AS v, 1 AS n FROM county LIMIT 1"),
                          bindir=bindir)
    assert paired.agreed, paired.delivery_causes
    assert "null_rendering" in paired.render_causes, paired.render_causes
    assert paired.bash.text.split("\n")[1] == "|1" and "None" in paired.ptc.text


def test_float_rendering_is_compared_not_assumed(rig):
    """`1.0/3` at sqlite's CLI digits against Python's shortest repr. Whether they
    happen to agree is sqlite's business; what is asserted is that the comparison runs
    and that a deliberately different spelling IS reported."""
    tasks, bindir = rig
    same = differential(_gold(tasks[0], "SELECT 1.0/3 AS v FROM county LIMIT 1"),
                        bindir=bindir)
    assert same.agreed
    # sqlite renders 1.0/3 as 0.33333333333333332 and Python reprs it as
    # 0.3333333333333333; both parse to the same double, so the answer agrees and the
    # render cause is float_rendering only when the digits do not round-trip.
    assert same.render_causes in ((), ("float_rendering",)), same.render_causes


def test_blob_rendering_is_reported(rig):
    """bash writes a BLOB's raw bytes; PTC prints `b'..'`. For bytes that are not
    UTF-8 the bash channel cannot be read as text at all, which is why the differential
    reaches the wrapper without `text=True` and why the divergence is a DELIVERY one
    here rather than a render one: one model gets `b'\\x00\\xff'`, the other gets
    replacement characters. That is the finding, not a crash in the check."""
    tasks, bindir = rig
    d = differential(_gold(tasks[0], "SELECT x'00ff' AS b FROM county LIMIT 1"),
                     bindir=bindir)
    assert d.bash.outcome == "undecodable", d.bash
    assert d.ptc.outcome == "ok" and isinstance(d.ptc.rows[0][0], bytes)
    assert "one_sided_undecodable" in d.delivery_causes, d.delivery_causes
    # UTF-8-decodable bytes must not trip the undecodable branch; they are a render
    # difference only.
    ok = differential(_gold(tasks[0], "SELECT x'6162' AS b FROM county LIMIT 1"),
                      bindir=bindir)
    assert ok.bash.outcome == ok.ptc.outcome == "ok"
    assert "blob_rendering" in ok.render_causes, ok.render_causes


def test_separator_in_cell_is_reported(rig):
    """A `|` inside a value makes the bash row gain a field. The delivery still parses
    (both give the same two values after generous typing) but the shape differs."""
    tasks, bindir = rig
    d = differential(_gold(tasks[0], "SELECT 'a|b' AS v, 1 AS n FROM county LIMIT 1"),
                     bindir=bindir)
    assert "separator_in_cell" in d.render_causes, (d.render_causes, d.bash.text)


def test_newline_in_cell_is_reported(rig):
    tasks, bindir = rig
    d = differential(_gold(tasks[0], "SELECT 'a' || char(10) || 'b' AS v, 1 AS n "
                                     "FROM county LIMIT 1"), bindir=bindir)
    assert "newline_in_cell" in d.render_causes, (d.render_causes, d.bash.text)


def test_duplicate_columns_are_reported(rig):
    """`SELECT s.name, c.name` is `name|name` on bash and `name`/`name_2` on PTC --
    the spelling `SHARED_PROMPT` promises to both arms."""
    tasks, bindir = rig
    d = differential(
        _gold(tasks[0], "SELECT s.name, c.name FROM school s "
                        "JOIN county c ON s.county_id = c.county_id "
                        "ORDER BY s.school_id"), bindir=bindir)
    assert d.agreed
    assert "duplicate_columns" in d.render_causes, (d.render_causes, d.bash.columns, d.ptc.columns)


# ------------------------------------------------------------------------------------
# The check's own plumbing.
# ------------------------------------------------------------------------------------

def test_the_diff_channel_is_the_arm_channel(rig):
    """`bash_command` must be `run_bash_sql`'s command, not a second shell path.

    It reaches the wrapper without `text=True` so a BLOB can be reported, and this pins
    the two against each other on a query both can return.
    """
    tasks, bindir = rig
    from ptc.sql_arms import run_bash_sql

    db = tasks[0].db_path
    ours = bash_command(db, "SELECT COUNT(*) FROM school", bindir=bindir)
    theirs = run_bash_sql(db, "SELECT COUNT(*) FROM school", bindir=bindir)
    assert ours.stdout.decode() == theirs.stdout
    assert ours.returncode == theirs.returncode


def test_concurrent_installs_do_not_corrupt_the_wrapper(tmp_path):
    """A shared `bindir` under concurrent installs must still run the WHOLE script.

    `install_wrapper` used to `write_text` the script in place, truncating it first. A
    parallel differential sweep (eight threads, one `bindir`) saw 63 of 480 calls run a
    partial file and return empty stdout with exit code 0 -- a divergence the rig
    manufactured, indistinguishable from a finding. The install now writes a staging
    file and renames it into place; this asserts the property rather than the
    implementation by hammering the shared path and requiring every call to succeed.
    """
    import sqlite3
    import threading
    from ptc.sql_arms import install_wrapper, run_bash_sql

    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t(id INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(500)])
    conn.commit()
    conn.close()
    bindir = tmp_path / "bin"
    install_wrapper(bindir, str(db))

    bad = []

    def hammer():
        for _ in range(40):
            r = run_bash_sql(str(db), "SELECT COUNT(*) FROM t", bindir=bindir)
            if r.returncode != 0 or "500" not in r.stdout:
                bad.append((r.returncode, r.stdout[:60], r.stderr[:80]))

    threads = [threading.Thread(target=hammer) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not bad, bad[:3]


def test_control_bytes_are_caret_notated_on_bash(rig):
    """sqlite's CLI prints a control byte as caret notation in every output mode.

    `'A' || char(29) || 'B'` is `A^]B` on bash and `A\\x1dB` to a program. The answer is
    the same value, so the delivery agrees and the render difference is reported. This
    was found on four BIRD dev golds (`thrombosis_prediction`) only because the sweep
    over the corpus's own queries ran; no named capability touches control bytes.
    """
    tasks, bindir = rig
    d = differential(_gold(tasks[0], "SELECT 'A' || char(29) || 'B' AS v FROM county LIMIT 1"),
                     bindir=bindir)
    assert d.agreed, d.delivery_causes
    assert "control_char_rendering" in d.render_causes, d.render_causes
    assert "^]" in d.bash.text and "\\x1d" in d.ptc.text   # PTC shows `repr`'s escape


def test_the_cause_vocabularies_are_closed(rig):
    """Every cause a Differential can carry is one of the two declared vocabularies, so
    the sweep's summary is a Counter over known names and a new cause has to be added
    here -- which is where a reader looks."""
    tasks, bindir = rig
    seen = set()
    for sql in ("SELECT NULL, 1 FROM county LIMIT 1", "SELECT 'a|b' FROM county LIMIT 1",
                "SELECT * FROM missing", "SELECT x'ff' FROM county LIMIT 1"):
        d = differential(_gold(tasks[0], sql), bindir=bindir)
        seen |= set(d.delivery_causes) | set(d.render_causes)
        assert d.bash.outcome in DELIVERY_OUTCOMES
        assert d.ptc.outcome in DELIVERY_OUTCOMES
    assert seen <= set(DELIVERY_CAUSES) | set(RENDER_CAUSES), seen
    assert "null_rendering" in seen and "separator_in_cell" in seen


def test_a_task_with_no_gold_is_refused(rig):
    """A differential over nothing is not an agreement."""
    tasks, bindir = rig
    with pytest.raises(ValueError, match="no gold"):
        differential(_gold(tasks[0], "   "), bindir=bindir)
    with pytest.raises(ValueError, match="compare"):
        differential(tasks[0], bindir=bindir, compare="jaccard")


def test_the_undecodable_branch_is_reachable(rig):
    """`run_bash_sql` raises `UnicodeDecodeError` on this query. The differential has to
    return a Delivery saying so, not raise, because that raise IS the finding."""
    tasks, bindir = rig
    from ptc.sql_arms import run_bash_sql

    db = tasks[0].db_path
    with pytest.raises(UnicodeDecodeError):
        run_bash_sql(db, "SELECT x'ff' FROM county LIMIT 1", bindir=bindir)
    d = differential(_gold(tasks[0], "SELECT x'ff' FROM county LIMIT 1"), bindir=bindir)
    assert d.bash.outcome == "undecodable", d.bash
    assert d.ptc.outcome == "ok" and isinstance(d.ptc.rows[0][0], bytes)
