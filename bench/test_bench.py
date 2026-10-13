"""Tests for the `bench` instrument. Offline: the committed fixture is the only corpus.

Two disciplines from the repo, both load-bearing here:

**Numbers are derived, never written down.** `tests/test_defect_ledger.py` is the pattern:
the data is the sole source of truth and the test computes what it asserts. A test that
hardcoded "8 fixture tasks" or "141 simple shapes" would pass against a fixture that had
silently changed, which is the failure mode it exists to catch. The one exception is
marked where it occurs: the shape-equivalence tests state the *property* (two spellings
of one join are one shape) rather than the shape string, because the property is the
claim and the string is an implementation detail.

**A green test proves nothing until it has been seen red.** The mutation evidence for the
scorer and the power report is recorded in `docs/bench-taskset.md`; the mutations were
corrupting a gold query, dropping a shape from the inventory, and widening the scorer's
comparison. Each turned the relevant test red before being reverted.
"""

from __future__ import annotations

import dataclasses
import io
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from bench import fixture  # noqa: E402
from bench.loader import CorpusMissing, load_bird, load_spider  # noqa: E402
from bench.score import (INVALID_STATUSES, execution_accuracy,  # noqa: E402
                         extract_sql, validate_golds)
from bench.shapes import shape, skeleton, tokenize  # noqa: E402
from bench.suite import (DELTAS, RHOS, discordance_from_band,  # noqa: E402
                         inventory, report, select)
from bench.task import TIERS, SqlTask  # noqa: E402


@pytest.fixture(scope="module")
def bird_tasks(tmp_path_factory) -> list[SqlTask]:
    root = fixture.materialize(tmp_path_factory.mktemp("bird"))
    return load_bird(root)


@pytest.fixture(scope="module")
def spider_tasks(tmp_path_factory) -> list[SqlTask]:
    root = fixture.materialize_spider(tmp_path_factory.mktemp("spider"))
    return load_spider(root)


# --- shapes -----------------------------------------------------------------------

def test_tokenizer_erases_literals_and_identifiers():
    """Two queries differing only in a literal or a column name are one skeleton. This
    is what stops `WHERE c = 'CA'` and `WHERE c = 'NY'` becoming two shapes -- the
    replicate trap at the token level."""
    a = tokenize("SELECT name FROM t WHERE county = 'Alameda'")
    b = tokenize("SELECT title FROM t WHERE region = 'Fresno'")
    assert a == b
    assert "LIT" in a and "ID" in a


def test_every_real_bird_gold_tokenizes_without_unknowns(bird_tasks):
    """`UNKNOWN` is the tokenizer's visible failure mode. Any appearance means a
    construct the skeleton silently dropped, which would shrink a shape."""
    for t in bird_tasks:
        assert skeleton(t.gold_sql).unknown == 0, t.name


def test_join_spelling_does_not_split_a_shape():
    """An implicit comma join and an explicit INNER JOIN are the same semantics and must
    be one shape. They were two until the loader normalised comma joins and counted `ON`
    as a predicate: a split here inflates the shape count, which inflates the
    effective-n ceiling -- the flattering direction."""
    explicit = ("SELECT a.n FROM a INNER JOIN b ON a.id = b.id WHERE b.x > 5")
    comma = ("SELECT a.n FROM a, b WHERE a.id = b.id AND b.x > 5")
    assert shape(explicit) == shape(comma)
    assert shape(explicit, "coarse") == shape(comma, "coarse")


def test_join_semantics_does_split_a_shape():
    """LEFT and INNER are different semantics -- not a spelling choice -- so they are
    different shapes. The complement of the test above: a shape definition blind to this
    would collapse genuinely different solution strategies."""
    inner = "SELECT a.n FROM a INNER JOIN b ON a.id = b.id WHERE b.x > 5"
    left = "SELECT a.n FROM a LEFT JOIN b ON a.id = b.id WHERE b.x > 5"
    assert shape(inner) != shape(left)


def test_nesting_counts_subqueries_not_function_calls():
    """Paren depth alone would count `COUNT(*)` as nesting, which would make almost
    every aggregate query 'nested' and destroy the distinction."""
    assert skeleton("SELECT COUNT(*) FROM t").nest_depth == 0
    assert skeleton("SELECT a FROM t WHERE x > (SELECT AVG(y) FROM u)").nest_depth == 1


def test_coarse_is_never_finer_than_fine(bird_tasks):
    """Granularity has to be monotone: tasks sharing a fine shape must share a coarse
    one. If not, the two ceilings are not bracketing the same quantity and printing them
    as a range is meaningless."""
    by_fine: dict[str, set[str]] = {}
    for t in bird_tasks:
        by_fine.setdefault(t.shape, set()).add(t.coarse_shape)
    assert all(len(v) == 1 for v in by_fine.values())
    assert len({t.coarse_shape for t in bird_tasks}) <= len({t.shape for t in bird_tasks})


def test_shape_rejects_unknown_granularity():
    with pytest.raises(ValueError, match="granularity"):
        shape("SELECT 1", "medium")


# --- loader -----------------------------------------------------------------------

def test_fixture_loads_every_committed_record(bird_tasks):
    """Count derived from the committed JSON, not written here."""
    assert len(bird_tasks) == len(fixture.records())
    assert {t.name for t in bird_tasks} == {
        f"bird-{int(r['question_id']):04d}" for r in fixture.records()}


def test_fixture_covers_distinct_shapes(bird_tasks):
    """The fixture earns its place by exercising one shape per structural family. If two
    fixture tasks collapse to one shape, the selector's stratification is untested."""
    assert len({t.shape for t in bird_tasks}) == len(bird_tasks)


def test_fixture_spans_every_tier(bird_tasks):
    assert {t.tier for t in bird_tasks} == set(TIERS)


def test_bird_tiers_are_annotated_spider_tiers_are_derived(bird_tasks, spider_tasks):
    """The distinction `bench/suite.py:report()` refuses to pool. BIRD ships a human
    `difficulty`; Spider ships none, so its tier is a structural heuristic."""
    assert {t.tier_source for t in bird_tasks} == {"annotated"}
    assert {t.tier_source for t in spider_tasks} == {"derived"}


def test_both_loaders_see_the_same_questions(bird_tasks, spider_tasks):
    """The Spider fixture is the same questions in Spider's record format. Equal gold SQL
    proves the two loaders read the two different key names (`SQL` vs `query`) and the
    two different database directories correctly."""
    assert ([t.gold_sql for t in bird_tasks] == [t.gold_sql for t in spider_tasks])
    assert all(Path(t.db_path).is_file() for t in spider_tasks)


def test_absent_corpus_raises_and_names_the_expected_path(tmp_path):
    """The headline requirement. An empty taskset scores 0/0 on both arms and reads as a
    tie -- run 3d's 23/23 is in this project's history as exactly that."""
    with pytest.raises(CorpusMissing) as exc:
        load_bird(tmp_path / "does-not-exist")
    msg = str(exc.value)
    assert "dev.json" in msg and "dev_databases" in msg
    assert "empty taskset" in msg


def test_manifest_without_databases_raises(tmp_path):
    """A manifest present but the sqlite files absent -- the state the real BIRD archive
    leaves you in before the NESTED `dev_databases.zip` is extracted."""
    root = fixture.materialize(tmp_path / "c")
    db = root / "dev_databases" / fixture.DB_ID / f"{fixture.DB_ID}.sqlite"
    db.unlink()
    with pytest.raises(CorpusMissing, match="NESTED"):
        load_bird(root)


def test_loader_resolves_one_level_of_nesting(tmp_path):
    """`dev.zip` extracts to `dev_20240627/`, so a caller pointing at the extraction
    directory is one level above the corpus."""
    outer = tmp_path / "extracted"
    fixture.materialize(outer / "dev_20240627")
    assert len(load_bird(outer)) == len(fixture.records())


def test_db_paths_are_absolute(bird_tasks):
    """The arms run with an unspecified cwd; a relative path is a corpus that resolves
    differently per arm."""
    assert all(Path(t.db_path).is_absolute() for t in bird_tasks)


def test_derived_tier_is_monotone_in_structure():
    """`_derive_tier`'s stated rule, asserted as a property rather than a table."""
    from bench.loader import _derive_tier
    assert _derive_tier("SELECT a FROM t WHERE x = 1") == "simple"
    assert _derive_tier("SELECT COUNT(*) FROM t") == "moderate"
    assert _derive_tier("SELECT a FROM t WHERE x > (SELECT AVG(y) FROM t)") == "challenging"
    assert _derive_tier("SELECT a FROM t UNION SELECT b FROM u") == "challenging"


def test_bad_tier_is_rejected(bird_tasks):
    with pytest.raises(ValueError, match="tier"):
        dataclasses.replace(bird_tasks[0], tier="trivial")
    with pytest.raises(ValueError, match="tier_source"):
        dataclasses.replace(bird_tasks[0], tier_source="guessed")


# --- scorer -----------------------------------------------------------------------

def test_every_fixture_gold_executes(bird_tasks):
    """Instrument precondition, checked before anything is measured: a task whose gold
    does not run cannot adjudicate a prediction."""
    assert validate_golds(bird_tasks) == []


def test_gold_against_itself_scores_one(bird_tasks):
    """The scorer's floor. Derived over every fixture task, so adding a task that the
    scorer cannot round-trip fails here rather than silently scoring an arm zero."""
    for t in bird_tasks:
        r = execution_accuracy(t.gold_sql, t)
        assert (r.score, r.status, r.valid) == (1.0, "match", True), (t.name, r)


def test_a_different_query_scores_zero(bird_tasks):
    """Cheap, but it is the test that would catch a scorer returning 1.0 unconditionally
    -- which `test_gold_against_itself_scores_one` alone cannot."""
    t = next(x for x in bird_tasks if x.name == "bird-0000")
    r = execution_accuracy("SELECT name FROM school WHERE charter = 0", t)
    assert (r.score, r.status, r.valid) == (0.0, "mismatch", True)


def test_syntax_error_scores_zero_without_raising(bird_tasks):
    r = execution_accuracy("SELECT FROM WHERE haha", bird_tasks[0])
    assert (r.score, r.status, r.valid) == (0.0, "pred_error", True)


def test_missing_column_scores_zero_without_raising(bird_tasks):
    r = execution_accuracy("SELECT no_such_column FROM school", bird_tasks[0])
    assert (r.score, r.valid) == (0.0, True)
    assert r.status == "pred_error"


def test_empty_prediction_scores_zero(bird_tasks):
    r = execution_accuracy("   ", bird_tasks[0])
    assert (r.score, r.status, r.valid) == (0.0, "pred_empty", True)


def test_nonterminating_query_times_out_and_scores_zero(bird_tasks):
    """An unbounded recursive CTE. Without the progress handler this hangs the run; a
    thread-based timeout could not interrupt it."""
    sql = ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) "
           "SELECT COUNT(*) FROM r")
    r = execution_accuracy(sql, bird_tasks[0], timeout_s=0.5)
    assert (r.score, r.status, r.valid) == (0.0, "pred_timeout", True)


def test_oversized_result_is_capped_not_loaded(bird_tasks):
    """A cartesian product must not be fetched into memory. Capped, and the cap is a
    distinct outcome rather than a mismatch, so it is visible in a trace."""
    sql = "SELECT T1.name FROM school AS T1, school AS T2, school AS T3"
    r = execution_accuracy(sql, bird_tasks[0], max_rows=10)
    assert (r.score, r.status, r.valid) == (0.0, "pred_truncated", True)


def test_write_attempts_are_refused(bird_tasks):
    """Read-only at both layers. The prediction is generated text pointed at a corpus
    file; it must not be able to change it."""
    for sql in ("INSERT INTO school (school_id, name, county_id, charter) "
                "VALUES (99, 'x', 1, 0)",
                "DELETE FROM school",
                "UPDATE school SET name = 'x'",
                "DROP TABLE school",
                "CREATE TABLE evil (a)"):
        r = execution_accuracy(sql, bird_tasks[0])
        assert (r.score, r.status, r.valid) == (0.0, "pred_error", True), sql
    # and the corpus is intact
    assert validate_golds(bird_tasks) == []
    conn = sqlite3.connect(bird_tasks[0].db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM school").fetchone()[0] == 10
    finally:
        conn.close()


def test_second_statement_is_not_executed(bird_tasks):
    """`sqlite3.Connection.execute` runs one statement, so a trailing `DROP` raises
    rather than running. Asserted because it is a security property being relied on,
    not an incidental behaviour."""
    r = execution_accuracy("SELECT 1; DROP TABLE school", bird_tasks[0])
    assert (r.score, r.valid) == (0.0, True)
    conn = sqlite3.connect(bird_tasks[0].db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM school").fetchone()[0] == 10
    finally:
        conn.close()


def test_broken_gold_is_invalid_not_a_zero(bird_tasks):
    """The asymmetry `ptc/paired.py:refuse_voids` exists to refuse. A defective task
    scored 0 credits whichever arm also failed; it has to void instead."""
    broken = dataclasses.replace(bird_tasks[0], gold_sql="SELECT FROM nowhere")
    r = execution_accuracy("SELECT name FROM school", broken)
    assert r.valid is False
    assert r.status in INVALID_STATUSES
    assert validate_golds([broken]) != []


def test_missing_database_is_invalid_not_a_zero(bird_tasks):
    gone = dataclasses.replace(bird_tasks[0], db_path="/nonexistent/x.sqlite")
    r = execution_accuracy("SELECT 1", gone)
    assert (r.status, r.valid) == ("db_missing", False)


def test_row_order_does_not_matter(bird_tasks):
    """BIRD's convention. A correct query that happens to sort differently is correct."""
    t = next(x for x in bird_tasks if x.name == "bird-0000")
    r = execution_accuracy("SELECT name FROM school WHERE charter = 1 ORDER BY name DESC",
                           t)
    assert r.score == 1.0


def test_multiset_and_set_comparison_differ_on_duplicates(bird_tasks):
    """The divergence from official BIRD, pinned by a test so it cannot be changed
    silently. BIRD's published `evaluation.py` compares with `set()`, which scores a
    de-duplicated answer as correct. `set` is the default because leaderboard
    comparability is why this taskset replaced a self-authored one; multiset is the
    stricter sensitivity check."""
    t = dataclasses.replace(
        bird_tasks[0],
        gold_sql="SELECT region FROM county WHERE region = 'Bay Area'")
    dedup = "SELECT DISTINCT region FROM county WHERE region = 'Bay Area'"
    assert execution_accuracy(dedup, t, compare="multiset").score == 0.0
    assert execution_accuracy(dedup, t, compare="set").score == 1.0


def test_scorer_rejects_unknown_comparison(bird_tasks):
    with pytest.raises(ValueError, match="compare"):
        execution_accuracy("SELECT 1", bird_tasks[0], compare="jaccard")


def test_int_and_float_of_equal_value_match(bird_tasks):
    """sqlite's storage-class choice for an integral value is not a wrong answer."""
    t = dataclasses.replace(bird_tasks[0], gold_sql="SELECT 1")
    assert execution_accuracy("SELECT 1.0", t).score == 1.0


def test_extract_sql_unwraps_a_fenced_block():
    """Extraction is the harness's explicit step, not a silent leniency in the metric --
    but it has to happen, or a fenced prediction scores a syntax error and understates
    the model, which looks like a frontier-band problem and is not one."""
    assert extract_sql("here you go:\n```sql\nSELECT 1;\n```\n") == "SELECT 1"
    assert extract_sql("SELECT 1;") == "SELECT 1"
    assert extract_sql("```\nSELECT a FROM t\n```") == "SELECT a FROM t"


def test_scorer_does_not_extract_on_its_own(bird_tasks):
    """The complement: the scorer must NOT silently unwrap, or extraction stops being
    auditable."""
    t = next(x for x in bird_tasks if x.name == "bird-0000")
    fenced = f"```sql\n{t.gold_sql}\n```"
    assert execution_accuracy(fenced, t).status == "pred_error"
    assert execution_accuracy(extract_sql(fenced), t).score == 1.0


# --- selector ---------------------------------------------------------------------

def test_select_is_a_pure_function_of_the_seed(bird_tasks):
    a = [t.name for t in select(bird_tasks, 2, seed=7)]
    b = [t.name for t in select(bird_tasks, 2, seed=7)]
    assert a == b
    assert [t.name for t in select(bird_tasks, 2, seed=8)] != a or len(a) <= 1


def test_select_draws_from_every_requested_tier(bird_tasks):
    """`ledger`'s first selector returned 30 full-scan tasks and zero cheap ones because
    it walked shapes in sorted order. The same hazard is live here -- every `t1 ...`
    shape sorts ahead of every `t2 ...` shape."""
    got = select(bird_tasks, 2, seed=0)
    assert {t.tier for t in got} == set(TIERS)


def test_select_exhausts_shapes_before_taking_replicates(bird_tasks):
    """The replicate trap, committed by the selector instead of by the corpus. Asserted
    over the real fixture: with one task per shape available, no shape may repeat until
    every shape in the tier has been drawn."""
    for tier in TIERS:
        in_tier = [t for t in bird_tasks if t.tier == tier]
        n_shapes = len({t.shape for t in in_tier})
        drawn = [t for t in select(bird_tasks, {tier: n_shapes}, seed=3)]
        assert len(drawn) == n_shapes
        assert len({t.shape for t in drawn}) == n_shapes


def test_select_does_not_silently_cap_an_over_request(bird_tasks):
    """Asking for more than a tier holds draws replicates rather than returning fewer
    and saying nothing -- but it can never exceed the tier's question count."""
    tier = "simple"
    in_tier = [t for t in bird_tasks if t.tier == tier]
    got = select(bird_tasks, {tier: len(in_tier) + 5}, seed=1)
    assert len(got) == len(in_tier)


def test_select_rejects_an_unknown_tier(bird_tasks):
    with pytest.raises(ValueError, match="unknown tier"):
        select(bird_tasks, {"impossible": 3})


def test_select_touches_no_database(bird_tasks):
    """Pure by contract: the selector runs before any sqlite file needs to exist, so a
    suite can be built and signed without the corpus being present."""
    phantom = [dataclasses.replace(t, db_path="/nonexistent/x.sqlite")
               for t in bird_tasks]
    assert len(select(phantom, 1, seed=0)) == len(set(t.tier for t in phantom))


# --- inventory and report ---------------------------------------------------------

def test_inventory_shape_counts_are_the_real_distinct_counts(bird_tasks):
    """Derived both ways and compared. The inventory is what the ceiling is computed
    from, so a miscount there silently moves every number in the report."""
    inv = inventory(bird_tasks, "fine")
    for tier, row in inv.items():
        in_tier = [t for t in bird_tasks if t.tier == tier]
        assert row["questions"] == len(in_tier)
        assert row["shapes"] == len({t.shape for t in in_tier})
        assert row["singletons"] == sum(
            1 for v in Counter(t.shape for t in in_tier).values() if v == 1)
    assert sum(r["questions"] for r in inv.values()) == len(bird_tasks)


def test_inventory_replicates_sum_to_the_question_count(bird_tasks):
    for tier, row in inventory(bird_tasks, "fine").items():
        assert sum(row["replicates"].values()) == row["questions"]


def test_coarse_inventory_never_exceeds_fine(bird_tasks):
    fine, coarse = inventory(bird_tasks, "fine"), inventory(bird_tasks, "coarse")
    for tier in fine:
        assert coarse[tier]["shapes"] <= fine[tier]["shapes"]


def _ceiling_table(text: str, which: str) -> dict[float, list[float]]:
    """Parse the `shapes / rho` block out of a report. Returns `{rho: [per-tier...]}`.

    Parsing rather than substring-matching, because `f"{10:.0f}" in text` is satisfied
    by the `10` inside `100` -- which it was: with the shape count mutated down by one,
    the expected ceiling `10` still matched a `100` elsewhere in the table and this test
    stayed green while the number it checks was wrong.
    """
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.endswith(f"({which} shapes)"))
    rows: dict[float, list[float]] = {}
    for ln in lines[start + 1:start + 1 + len(RHOS)]:
        nums = [float(x) for x in ln.split()]
        rows[nums[0]] = nums[1:]
    return rows


def test_report_prints_the_derived_ceiling_not_a_stored_one(bird_tasks):
    """The power report's own ceiling table, parsed and matched against shape counts
    computed straight from the tasks.

    Both anchors are deliberate. Shape counts are NOT read from `inventory()`: an
    earlier version took them from there and so moved in lockstep with the code under
    test, staying green when `inventory()` was mutated to undercount by one. And the
    table is parsed rather than substring-matched, for the reason in `_ceiling_table`.
    This is the test the 'drop a shape' mutation turns red.
    """
    buf = io.StringIO()
    report(bird_tasks, out=buf)
    text = buf.getvalue()
    tiers_present = [t for t in TIERS if any(x.tier == t for x in bird_tasks)]

    for which, key in (("fine", lambda t: t.shape),
                       ("coarse", lambda t: t.coarse_shape)):
        expected = [len({key(t) for t in bird_tasks if t.tier == tier})
                    for tier in tiers_present]
        table = _ceiling_table(text, which)
        assert sorted(table) == sorted(RHOS)
        for rho, printed in table.items():
            assert printed == pytest.approx(
                [round(e / rho) for e in expected]), (which, rho, expected)

    assert str(len(bird_tasks)) in text
    assert str(len({t.shape for t in bird_tasks})) in text


def test_report_states_the_rho_ceiling_for_each_delta(bird_tasks):
    """`rho_max = shapes / n_required` is the decisive number. Both sides derived
    independently of `inventory()`: `n_required` from the project's own power function,
    shapes straight from the tasks."""
    from ptc.paired import power_pairs
    buf = io.StringIO()
    report(bird_tasks, out=buf)
    text = buf.getvalue()
    disc = discordance_from_band(0.5)
    for delta in DELTAS:
        need = power_pairs(delta, disc)
        if need is None:
            continue
        for tier in TIERS:
            in_tier = [t for t in bird_tasks if t.tier == tier]
            if not in_tier:
                continue
            rho_max = min(len({t.shape for t in in_tier}) / need, 1.0)
            assert f"{rho_max:.3f}" in text, (delta, need, rho_max)


def test_discordance_is_the_independent_disagreement_rate():
    """`2p(1-p)`, asserted as the property. Maximal at p=0.5 and symmetric about it,
    which is why the band floor and the band centre give different requirements."""
    assert discordance_from_band(0.5) == pytest.approx(0.5)
    assert discordance_from_band(0.2) == pytest.approx(discordance_from_band(0.8))
    assert discordance_from_band(0.25) == pytest.approx(0.375)
    assert discordance_from_band(0.5) > discordance_from_band(0.2)


def test_report_refuses_to_pool_annotated_and_derived_tiers(bird_tasks, spider_tasks):
    """BIRD's `difficulty` is a human annotation; Spider's tier is a structural
    heuristic. One table row covering both would report a quantity nobody defined."""
    buf = io.StringIO()
    report(bird_tasks + spider_tasks, out=buf)
    text = buf.getvalue()
    assert "tiers annotated" in text and "tiers derived" in text
    assert text.count("=== ") == 2


def test_report_names_the_question_count_as_not_an_n(bird_tasks):
    """The replicate trap is the thing this instrument exists to avoid, so the report
    has to say so where the question count is printed."""
    buf = io.StringIO()
    report(bird_tasks, out=buf)
    assert "A QUESTION COUNT IS NOT AN n" in buf.getvalue()


def test_the_default_comparison_is_set_and_is_the_leaderboard_one(bird_tasks):
    """Pins the default itself, not just that both modes exist.

    The default was `multiset` until 2026-10-12 and no test noticed the change: every
    comparison test passed `compare=` explicitly, so the one value a caller gets when
    it says nothing was the one value nothing checked. An EX number produced under
    multiset is not comparable to the published sub-1B figures that site this
    project's frontier band, which makes the default a result-affecting choice.
    """
    import inspect
    default = inspect.signature(execution_accuracy).parameters["compare"].default
    assert default == "set", default

    # and the default actually behaves as set, rather than merely being spelled it
    t = bird_tasks[0]
    dedup = f"SELECT DISTINCT * FROM ({t.gold_sql})"
    explicit = execution_accuracy(dedup, t, compare="set").score
    implicit = execution_accuracy(dedup, t).score
    assert implicit == explicit


def test_the_row_ceiling_clears_the_two_large_bird_golds():
    """`MAX_ROWS` must admit the two BIRD dev golds that legitimately return 228,765
    and 278,230 rows in ~1s. At the original 100_000 they were rejected as defective
    tasks, which is the instrument penalising valid work."""
    from bench.score import MAX_ROWS
    assert MAX_ROWS > 278_230


def test_a_nonterminating_gold_times_out_instead_of_hanging(tmp_path, monkeypatch):
    """The gold filter needs a deadline that actually fires.

    The first version of `scalar_answer`'s progress handler closed over a flag nothing
    ever set, so it returned 0 forever and the two BIRD dev golds that never terminate
    hung the entire draw with no output -- a timeout that cannot fire, which is the
    defect class this repo exists to catch, committed while writing the tool.
    """
    import sqlite3
    import time

    from bench import make_probe_prompts as mpp

    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()

    class _Task:
        db_path = str(db)
        # an unbounded recursive CTE: correct SQL, never terminates
        gold_sql = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
                    "SELECT count(*) FROM c")

    monkeypatch.setattr(mpp, "GOLD_TIMEOUT_S", 0.5)
    start = time.monotonic()
    assert mpp.scalar_answer(_Task()) is None
    elapsed = time.monotonic() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s: the deadline did not fire"


def test_a_scalar_gold_is_kept_and_a_wide_one_is_not(tmp_path):
    """The filter's whole job: 1 row x 1 column in, everything else out."""
    import sqlite3

    from bench import make_probe_prompts as mpp

    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?)", [(1, "x"), (2, "y")])
    con.commit()
    con.close()

    def task(sql):
        return type("T", (), {"db_path": str(db), "gold_sql": sql})()

    assert mpp.scalar_answer(task("SELECT count(*) FROM t")) == "2"
    assert mpp.scalar_answer(task("SELECT a, b FROM t LIMIT 1")) is None   # two columns
    assert mpp.scalar_answer(task("SELECT a FROM t")) is None              # two rows
    assert mpp.scalar_answer(task("SELECT nope FROM t")) is None           # broken gold
    assert mpp.scalar_answer(task("SELECT NULL")) is None                  # no answer
