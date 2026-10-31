"""Tests for `bench/prepare.py` -- offline draw freeze and gold-validation supplement.

Spec: `spec/bench-preparation.md`. The numeric contract is T01-T16 there.

Two disciplines carried over from `bench/test_bench.py`:

**Numbers are derived, never written down.** Expected tier counts, eligible sets and
shape counts are recomputed from the loaded corpus or the selector's own output, so a
fixture that changes underneath the tests fails here rather than passing on a stale
literal.

**Injection is scoped.** Gold outcomes are real except where the test is specifically
about fault, drift, admission or isolation behaviour; those wrappers delegate to the
real function for every task they do not inject, so production comparisons stay
exercised. Source drift is simulated against a COPIED source tree, never by editing
repository sources.

`bench.prepare` is imported lazily inside test bodies: a missing module or missing
public name fails the test it belongs to, rather than erroring collection of the
whole file.
"""

from __future__ import annotations

import contextlib
import builtins
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

import bench.loader  # noqa: E402
import bench.score  # noqa: E402
import bench.suite  # noqa: E402
from bench import fixture  # noqa: E402
from bench.loader import load_bird  # noqa: E402
from bench.score import ExResult  # noqa: E402
from bench.suite import select  # noqa: E402
from bench.task import TIERS  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")

# The full committed fixture: 2 simple / 3 moderate / 3 challenging, one fine shape
# per task. Derived in tests from `fixture.records()` where a count is asserted.
FULL = {"simple": 2, "moderate": 3, "challenging": 3}
ONE_EACH = {"simple": 1, "moderate": 1, "challenging": 1}
ASKED = {"simple": 3, "moderate": 3, "challenging": 3}  # over-asks simple by 1

DRAW_DOC_KEYS = {
    "kind", "version", "stage", "measurement", "fixture", "model_calls", "status",
    "usable", "settings", "actual_per_tier", "shortfall_per_tier", "planned",
    "identity",
}
DRAW_SETTINGS_KEYS = {"seed", "per_tier", "granularity", "timeout_s", "max_rows",
                      "comparison"}
IDENTITY_KEYS = {"universe_sha256", "manifest_sha256", "source_sha256", "databases",
                 "runtime"}
RUNTIME_KEYS = {"python_implementation", "python_version", "sqlite_version"}
DB_IDENTITY_KEYS = {"db_id", "sha256", "size_bytes"}
PLANNED_KEYS = {"id", "tier", "db_id", "task_sha256"}
SOURCE_KEYS = {
    "bench/__init__.py", "bench/loader.py", "bench/suite.py", "bench/task.py",
    "bench/shapes.py", "bench/score.py", "bench/prepare.py",
    "ptc/__init__.py", "ptc/runtime.py", "ptc/paired.py", "ptc/metrics.py",
    "ptc/sqlite_safety.py",
}

SUPP_DOC_KEYS = {
    "kind", "version", "stage", "measurement", "fixture", "model_calls", "status",
    "usable", "draw_sha256", "planned_ids", "eligible_ids", "exclusions",
    "settings", "identity_checked", "counts", "shapes",
}
SUPP_SETTINGS_KEYS = {"timeout_s", "max_rows", "comparison"}
EXCLUSION_KEYS = {"id", "status", "category"}
STATUS_CATEGORY = {
    "gold_error": "gold_execution_rejection",
    "gold_timeout": "configured_deadline",
    "gold_truncated": "configured_row_bound",
    "db_missing": "database_availability",
}

# Keys that would leak ExResult detail, corpus text or measurement fields into the
# public documents. Asserted absent at every level of both documents (T11).
FORBIDDEN_KEYS = {
    "detail", "error", "exception", "trace", "message", "reason",
    "score", "solve_rate", "frontier", "reward", "result", "p_value", "delta",
    "question", "evidence", "sql", "gold_sql", "db_path", "rows",
}


# --- helpers -----------------------------------------------------------------------

def _prep():
    """Lazy import so a missing module or missing name fails inside the test body."""
    return importlib.import_module("bench.prepare")


def _canonical_bytes(doc: dict) -> bytes:
    """The exact serialization the spec pins for both published documents."""
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_corpus(root: Path, records: list[dict]) -> Path:
    """A BIRD-layout corpus over the committed fixture schema, with caller records."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "dev.json").write_text(json.dumps(records, indent=1))
    fixture.build_db(
        root / "dev_databases" / fixture.DB_ID / f"{fixture.DB_ID}.sqlite")
    return root


def _record(qid: int, sql: str, tier: str,
            question: str = "q?", evidence: str = "e?",
            db_id: str = fixture.DB_ID) -> dict:
    return {"question_id": qid, "db_id": db_id, "question": question,
            "evidence": evidence, "SQL": sql, "difficulty": tier}


def _mutate_dev_json(root: Path, mutate) -> None:
    recs = json.loads((root / "dev.json").read_text())
    mutate(recs)
    (root / "dev.json").write_text(json.dumps(recs, indent=1))


def _db_file(root: Path) -> Path:
    return root / "dev_databases" / fixture.DB_ID / f"{fixture.DB_ID}.sqlite"


_PT_DEFAULT = object()


def _freeze(prep, root: Path, out: Path, *, seed: int = 0, per_tier=_PT_DEFAULT,
            fixture: bool = True, **kw):
    """Call `freeze_draw` with the test defaults. Arguments pass through verbatim --
    a `per_tier=None` or `fixture=None` case must reach the implementation so its own
    type check does the rejecting."""
    if per_tier is _PT_DEFAULT:
        per_tier = dict(FULL)
    return prep.freeze_draw(root, out, seed=seed, per_tier=per_tier,
                            fixture=fixture, **kw)


def _validate(prep, root: Path, draw: Path, supp: Path, sha: str):
    return prep.validate_draw(root, draw, supp, expected_draw_sha256=sha)


def _staged_draw(prep, tmp_path: Path, name: str = "corpus", **kw):
    """A real frozen draw. Returns (corpus_root, draw_path, draw_sha256)."""
    root = fixture.materialize(tmp_path / name)
    draw = tmp_path / f"{name}-draw.json"
    sha = _freeze(prep, root, draw, **kw)
    return root, draw, sha


def _tier_counts(ids, tasks):
    by_name = {t.name: t for t in tasks}
    return dict(Counter(by_name[i].tier for i in ids))


def _shape_counts(ids, tasks):
    by_name = {t.name: t for t in tasks}
    got = [by_name[i] for i in ids]
    return {"fine": len({t.shape for t in got}),
            "coarse": len({t.coarse_shape for t in got})}


def _walk_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_keys(v)


def _patch_aliases(monkeypatch, prep, real, replacement):
    """Also wrap any name `bench.prepare` bound to the same function object, whatever
    spelling the import used, so sentries/injection fire at the real call site."""
    for name, obj in list(vars(prep).items()):
        if obj is real:
            monkeypatch.setattr(prep, name, replacement)


@contextlib.contextmanager
def _sentries(monkeypatch, prep):
    """Call counters at the real call sites: corpus loads, selector calls, gold
    validation, scorer calls and sqlite connections."""
    sen = Counter()
    real_connect = sqlite3.connect

    def counted(key, fn):
        def inner(*a, **k):
            sen[key] += 1
            return fn(*a, **k)
        return inner

    for module, name, key in (
            (bench.loader, "load_bird", "loads"),
            (bench.suite, "select", "selects"),
            (bench.score, "validate_golds", "golds"),
            (bench.score, "execution_accuracy", "ex")):
        real = getattr(module, name)
        monkeypatch.setattr(module, name, counted(key, real))
        _patch_aliases(monkeypatch, prep, real, counted(key, real))

    def connect_spy(*a, **k):
        sen["connects"] += 1
        return real_connect(*a, **k)

    monkeypatch.setattr(sqlite3, "connect", connect_spy)
    yield sen


def _inject_gold_outcome(monkeypatch, prep, override):
    """Wrap the REAL `execution_accuracy`: `override(task)` returns an ExResult to
    substitute for one task; every other task is scored by the real function. Fires
    whether the implementation reaches the scorer directly or via `validate_golds`,
    because `validate_golds` resolves `execution_accuracy` as a module global."""
    real = bench.score.execution_accuracy

    def spy(predicted, task, *a, **k):
        forced = override(task)
        return forced if forced is not None else real(predicted, task, *a, **k)

    monkeypatch.setattr(bench.score, "execution_accuracy", spy)
    _patch_aliases(monkeypatch, prep, real, spy)
    return spy


def _inject_broken_list(monkeypatch, prep, edit):
    """Wrap the REAL `validate_golds`: run it for real, then pass its returned list
    through `edit(tasks, broken)` to doctor the exclusion set the caller sees."""
    real = bench.score.validate_golds

    def spy(tasks, *a, **k):
        return edit(tasks, real(tasks, *a, **k))

    monkeypatch.setattr(bench.score, "validate_golds", spy)
    _patch_aliases(monkeypatch, prep, real, spy)
    return spy


def _race_publication(monkeypatch, final: Path, payload: bytes):
    """Create `final` with foreign bytes the first time any plausible publication
    primitive fires, then delegate. The exclusive link/rename that follows must lose
    to the existing file rather than clobber it."""
    fired = {"done": False}

    def wrap(fn):
        def inner(*a, **k):
            if not fired["done"]:
                fired["done"] = True
                try:
                    final.write_bytes(payload)
                except (FileExistsError, IsADirectoryError):
                    pass
            return fn(*a, **k)
        return inner

    for owner, name in (
            (os, "link"), (os, "rename"), (os, "replace"),
            (os, "fsync"), (os, "open"),
            (Path, "link_to"), (Path, "hardlink_to"),
            (Path, "rename"), (Path, "replace")):
        if hasattr(owner, name):
            monkeypatch.setattr(owner, name, wrap(getattr(owner, name)))


def _fail_directory_open(monkeypatch):
    """Fail only opens of existing directories -- the post-commit directory sync.
    Temp-file opens are file paths and pass through."""
    real_open = os.open

    def fake_open(path, flags=0, *a, **k):
        if isinstance(path, (str, bytes, os.PathLike)) and os.path.isdir(path):
            raise OSError("injected directory-open failure")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", fake_open)


@contextlib.contextmanager
def _mounted_copy(project_root: Path):
    """Import `bench`/`ptc` fresh from a copied tree so tests can drift source files
    that are never touched in the real checkout."""
    saved_path = list(sys.path)
    saved = {k: m for k, m in sys.modules.items()
             if k.split(".")[0] in ("bench", "ptc")}
    for k in list(saved):
        del sys.modules[k]
    sys.path.insert(0, str(project_root))
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for k in list(sys.modules):
            if k.split(".")[0] in ("bench", "ptc"):
                del sys.modules[k]
        sys.modules.update(saved)


def _copy_source_tree(dest: Path) -> Path:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    for pkg in ("bench", "ptc"):
        shutil.copytree(REPO / pkg, dest / pkg, ignore=ignore)
    return dest


def _assert_draw_doc(doc: dict, *, seed: int, per_tier: dict, timeout_s: float,
                     max_rows: int):
    assert set(doc) == DRAW_DOC_KEYS
    assert doc["kind"] == "bench-preparation"
    assert type(doc["version"]) is int and doc["version"] == 1
    assert doc["stage"] == "draw"
    assert doc["measurement"] is False
    assert doc["fixture"] is True
    assert type(doc["model_calls"]) is int and doc["model_calls"] == 0
    assert doc["status"] in ("frozen", "underfilled")
    assert doc["usable"] is False
    assert set(doc["settings"]) == DRAW_SETTINGS_KEYS
    s = doc["settings"]
    assert s["seed"] == seed and s["per_tier"] == per_tier
    assert s["granularity"] == "fine" and s["comparison"] == "set"
    assert s["timeout_s"] == timeout_s and type(s["timeout_s"]) is float
    assert s["max_rows"] == max_rows and type(s["max_rows"]) is int
    assert set(doc["actual_per_tier"]) == set(TIERS)
    assert set(doc["shortfall_per_tier"]) == set(TIERS)
    assert set(doc["identity"]) == IDENTITY_KEYS
    ident = doc["identity"]
    for key in ("universe_sha256", "manifest_sha256"):
        assert SHA256_RE.match(ident[key]), (key, ident[key])
    assert set(ident["source_sha256"]) == SOURCE_KEYS
    for name, digest in ident["source_sha256"].items():
        assert SHA256_RE.match(digest)
        assert digest == _sha256((REPO / name).read_bytes())
    assert set(ident["runtime"]) == RUNTIME_KEYS
    assert isinstance(ident["databases"], list)
    for entry in ident["databases"]:
        assert set(entry) == DB_IDENTITY_KEYS
        assert SHA256_RE.match(entry["sha256"])
        assert type(entry["size_bytes"]) is int
    for entry in doc["planned"]:
        assert set(entry) == PLANNED_KEYS
        assert entry["tier"] in TIERS
        assert SHA256_RE.match(entry["task_sha256"])


def _assert_supp_doc(doc: dict, *, draw_sha: str):
    assert set(doc) == SUPP_DOC_KEYS
    assert doc["kind"] == "bench-preparation"
    assert type(doc["version"]) is int and doc["version"] == 1
    assert doc["stage"] == "gold-validation"
    assert doc["measurement"] is False
    assert doc["fixture"] is True
    assert type(doc["model_calls"]) is int and doc["model_calls"] == 0
    assert doc["draw_sha256"] == draw_sha
    assert doc["identity_checked"] is True
    assert set(doc["settings"]) == SUPP_SETTINGS_KEYS
    assert doc["settings"]["comparison"] == "set"
    assert set(doc["counts"]) == {"planned", "eligible", "excluded"}
    for part in doc["counts"].values():
        assert set(part) == set(TIERS)
        assert all(type(v) is int for v in part.values())
    assert set(doc["shapes"]) == {"planned", "eligible"}
    for part in doc["shapes"].values():
        assert set(part) == {"fine", "coarse"}
        assert all(type(v) is int for v in part.values())
    assert doc["status"] in ("complete", "blocked")
    assert doc["usable"] == (
        doc["status"] == "complete" and len(doc["eligible_ids"]) > 0)
    planned_ids = doc["planned_ids"]
    excl_ids = [e["id"] for e in doc["exclusions"]]
    assert len(set(excl_ids)) == len(excl_ids)
    assert set(excl_ids) <= set(planned_ids)
    assert doc["eligible_ids"] == [i for i in planned_ids if i not in set(excl_ids)]
    for excl in doc["exclusions"]:
        assert set(excl) == EXCLUSION_KEYS
        assert excl["status"] in STATUS_CATEGORY
        assert excl["category"] == STATUS_CATEGORY[excl["status"]]


# --- T01 / T15: argument and document admission contracts ----------------------------

_BAD_ARGS = [
    pytest.param({"seed": None}, id="seed-none"),
    pytest.param({"seed": "0"}, id="seed-str"),
    pytest.param({"seed": 1.5}, id="seed-float"),
    pytest.param({"seed": True}, id="seed-bool"),
    pytest.param({"per_tier": None}, id="per_tier-none"),
    pytest.param({"per_tier": 3}, id="per_tier-int"),
    pytest.param({"per_tier": {"simple": 2, "moderate": 3}}, id="tier-missing"),
    pytest.param({"per_tier": {**FULL, "heavy": 1}}, id="tier-extra"),
    pytest.param({"per_tier": {**FULL, "simple": 0}}, id="count-zero"),
    pytest.param({"per_tier": {**FULL, "simple": -1}}, id="count-negative"),
    pytest.param({"per_tier": {**FULL, "simple": 1.5}}, id="count-fractional"),
    pytest.param({"per_tier": {**FULL, "simple": True}}, id="count-bool"),
    pytest.param({"per_tier": {"simple": 2, "moderate": 3, "challenging": "3"}},
                 id="count-str"),
    pytest.param({"fixture": None}, id="fixture-none"),
    pytest.param({"fixture": 1}, id="fixture-int"),
    pytest.param({"fixture": "yes"}, id="fixture-str"),
]

_BAD_BOUNDS = [
    pytest.param({"timeout_s": 0}, id="timeout-zero"),
    pytest.param({"timeout_s": -1.0}, id="timeout-negative"),
    pytest.param({"timeout_s": 30.0001}, id="timeout-over-cap"),
    pytest.param({"timeout_s": float("nan")}, id="timeout-nan"),
    pytest.param({"timeout_s": float("inf")}, id="timeout-inf"),
    pytest.param({"timeout_s": "30"}, id="timeout-str"),
    pytest.param({"timeout_s": True}, id="timeout-bool"),
    pytest.param({"max_rows": 0}, id="rows-zero"),
    pytest.param({"max_rows": -5}, id="rows-negative"),
    pytest.param({"max_rows": 500001}, id="rows-over-cap"),
    pytest.param({"max_rows": 2.0}, id="rows-float"),
    pytest.param({"max_rows": True}, id="rows-bool"),
    pytest.param({"max_rows": "10"}, id="rows-str"),
    pytest.param({"timeout_s": 0.02, "fixture": False},
                 id="nondefault-timeout-needs-fixture"),
    pytest.param({"max_rows": 2, "fixture": False},
                 id="nondefault-rows-needs-fixture"),
]


@pytest.mark.parametrize("bad", _BAD_ARGS + _BAD_BOUNDS)
def test_t01_t15_argument_contract_rejects_before_any_sql(tmp_path, monkeypatch, bad):
    """Every malformed argument combination is refused; none may reach a database."""
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    out = tmp_path / "draw.json"
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((ValueError, TypeError)):
            _freeze(prep, root, out, **bad)
    assert sen["connects"] == 0
    assert not out.exists()


def test_t01_missing_required_arguments_reject(tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    out = tmp_path / "draw.json"
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((TypeError, ValueError)):
            prep.freeze_draw(root, out)  # no seed, per_tier or fixture at all
    assert sen["connects"] == 0
    assert not out.exists()


def test_t15_default_bounds_are_the_production_values():
    """The production ceiling is 30.0s / 500000 rows / set -- pinned at the signature,
    not merely documented."""
    prep = _prep()
    sig = inspect.signature(prep.freeze_draw)
    assert sig.parameters["timeout_s"].default == 30.0
    assert sig.parameters["max_rows"].default == 500000


def test_t15_integer_timeout_normalizes_to_float(tmp_path):
    """A valid integral timeout is accepted and normalized to float in the document."""
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    out = tmp_path / "draw.json"
    _freeze(prep, root, out, timeout_s=30)
    doc = json.loads(out.read_bytes())
    assert doc["settings"]["timeout_s"] == 30.0
    assert type(doc["settings"]["timeout_s"]) is float


def test_t15_validation_accepts_no_bound_overrides(tmp_path, monkeypatch):
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((TypeError, ValueError)):
            prep.validate_draw(root, draw, tmp_path / "s.json",
                               expected_draw_sha256=sha, timeout_s=0.02)
        with pytest.raises((TypeError, ValueError)):
            prep.validate_draw(root, draw, tmp_path / "s2.json",
                               expected_draw_sha256=sha, max_rows=2)
    assert sen["connects"] == 0


# --- T02: seeded draw equals direct select, order-invariant, single selector call ----

def _orderings(records):
    return [list(records), list(reversed(records)),
            records[1::2] + records[::2]]


def test_t02_frozen_ids_match_direct_select_100_seeds_3_orders(tmp_path):
    """100 seeds x 3 corpus record orders: the frozen plan equals what
    `select(..., granularity="fine")` draws directly, with zero ordering differences."""
    prep = _prep()
    roots = []
    task_orders = []
    for i, ordered in enumerate(_orderings(fixture.records())):
        root = _write_corpus(tmp_path / f"corpus-{i}", ordered)
        roots.append(root)
        task_orders.append(load_bird(root))

    differences = []
    for seed in range(100):
        reference = None
        for order_i, (root, tasks) in enumerate(zip(roots, task_orders)):
            out = tmp_path / f"draw-{seed}-{order_i}.json"
            _freeze(prep, root, out, seed=seed)
            doc = json.loads(out.read_bytes())
            ids = [p["id"] for p in doc["planned"]]
            direct = [t.name for t in select(tasks, dict(FULL), seed=seed,
                                             granularity="fine")]
            if ids != direct or len(set(ids)) != len(ids):
                differences.append((seed, order_i, "vs-direct"))
            if reference is None:
                reference = ids
            elif ids != reference:
                differences.append((seed, order_i, "vs-order"))
    assert differences == [], differences[:10]


# --- T03 / T04: the happy path and the underfilled diagnostic -------------------------

def test_t03_full_draw_freezes_and_validates(tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
    tasks = load_bird(root)
    n_records = len(fixture.records())

    with _sentries(monkeypatch, prep) as sen:
        sha = _freeze(prep, root, draw, seed=11)
    assert sen["loads"] >= 1
    assert sen["selects"] == 1          # the selector is called exactly once
    assert sen["connects"] == 0         # freezing runs no SQL
    assert sen["golds"] == 0            # and no gold validation
    assert SHA256_RE.match(sha)

    raw = draw.read_bytes()
    assert _sha256(raw) == sha
    doc = json.loads(raw)
    assert raw == _canonical_bytes(doc)  # exact canonical bytes, re-serializable
    _assert_draw_doc(doc, seed=11, per_tier=FULL, timeout_s=30.0, max_rows=500000)
    assert doc["status"] == "frozen"

    planned_ids = [p["id"] for p in doc["planned"]]
    assert len(set(planned_ids)) == n_records
    assert _tier_counts(planned_ids, tasks) == FULL
    assert doc["actual_per_tier"] == FULL
    assert doc["shortfall_per_tier"] == {t: 0 for t in TIERS}

    # Manifest and selected-database identities are real digests of the corpus.
    assert doc["identity"]["manifest_sha256"] == _sha256(
        (root / "dev.json").read_bytes())
    selected_dbs = {t.db_id for t in tasks if t.name in set(planned_ids)}
    by_db = {e["db_id"]: e for e in doc["identity"]["databases"]}
    assert set(by_db) == selected_dbs
    for db_id, entry in by_db.items():
        dbf = root / "dev_databases" / db_id / f"{db_id}.sqlite"
        assert entry["sha256"] == _sha256(dbf.read_bytes())
        assert entry["size_bytes"] == len(dbf.read_bytes())
    rt = doc["identity"]["runtime"]
    assert rt["python_implementation"] == platform.python_implementation()
    assert rt["sqlite_version"] == sqlite3.sqlite_version

    with _sentries(monkeypatch, prep) as vsen:
        supp_sha = _validate(prep, root, draw, supp, sha)
    assert vsen["selects"] == 0                      # validation never re-draws
    assert vsen["connects"] == len(planned_ids)      # one read-only conn per task
    assert vsen["ex"] == len(planned_ids)            # every task really scored
    assert SHA256_RE.match(supp_sha)
    supp_raw = supp.read_bytes()
    assert _sha256(supp_raw) == supp_sha
    sdoc = json.loads(supp_raw)
    assert supp_raw == _canonical_bytes(sdoc)
    _assert_supp_doc(sdoc, draw_sha=sha)
    assert sdoc["status"] == "complete"
    assert sdoc["usable"] is True
    assert sdoc["planned_ids"] == planned_ids
    assert sdoc["eligible_ids"] == planned_ids
    assert sdoc["exclusions"] == []
    assert sdoc["counts"]["planned"] == FULL
    assert sdoc["counts"]["eligible"] == FULL
    assert sdoc["counts"]["excluded"] == {t: 0 for t in TIERS}
    assert sdoc["shapes"]["planned"] == _shape_counts(planned_ids, tasks)
    assert sdoc["shapes"]["eligible"] == _shape_counts(planned_ids, tasks)


def test_t04_underfilled_draw_publishes_diagnostic_and_validation_refuses(
        tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    tasks = load_bird(root)
    draw = tmp_path / "draw.json"
    sha = _freeze(prep, root, draw, per_tier=ASKED)

    doc = json.loads(draw.read_bytes())
    _assert_draw_doc(doc, seed=0, per_tier=ASKED, timeout_s=30.0, max_rows=500000)
    assert doc["status"] == "underfilled"
    available = dict(Counter(t.tier for t in tasks))
    want_actual = {t: min(ASKED[t], available[t]) for t in TIERS}
    assert doc["actual_per_tier"] == want_actual
    assert doc["shortfall_per_tier"] == {
        t: ASKED[t] - want_actual[t] for t in TIERS}
    assert doc["shortfall_per_tier"]["simple"] == 1
    assert sum(doc["shortfall_per_tier"].values()) == 1
    assert len(doc["planned"]) == sum(want_actual.values())

    supp = tmp_path / "supp.json"
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(ValueError):
            _validate(prep, root, draw, supp, sha)
    assert sen["connects"] == 0
    assert not supp.exists()


# --- T05: task eligibility gates -------------------------------------------------------

def test_t05_derived_spider_duplicate_or_escaping_tasks_rejected(tmp_path,
                                                               monkeypatch):
    prep = _prep()

    # One derived-tier task inside an otherwise-annotated BIRD corpus.
    root_d = tmp_path / "derived"
    recs = [dict(r) for r in fixture.records()]
    del recs[0]["difficulty"]
    _write_corpus(root_d, recs)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(ValueError):
            _freeze(prep, root_d, tmp_path / "d1.json")
    assert sen["connects"] == 0

    # A Spider-layout corpus: every task comes out tier_source="derived".
    root_s = fixture.materialize_spider(tmp_path / "spider")
    with _sentries(monkeypatch, prep) as sen2:
        with pytest.raises((ValueError, FileNotFoundError)):
            _freeze(prep, root_s, tmp_path / "d2.json")
    assert sen2["connects"] == 0

    # Duplicate names: the loader itself refuses, and that refusal must surface.
    root_dup = tmp_path / "dup"
    dup_recs = [fixture.records()[0], dict(fixture.records()[0])]
    _write_corpus(root_dup, dup_recs)
    with _sentries(monkeypatch, prep) as sen3:
        with pytest.raises(ValueError):
            _freeze(prep, root_dup, tmp_path / "d3.json")
    assert sen3["connects"] == 0

    # A record whose db_id escapes the corpus database directory. The file exists, so
    # the loader builds the task; containment must reject it before any DB work.
    root_e = tmp_path / "escaping"
    _write_corpus(root_e, [_record(0, "SELECT name FROM school", "simple",
                                   db_id="../escape")])
    fixture.build_db(root_e / "escape.sqlite")  # resolves outside dev_databases/
    with _sentries(monkeypatch, prep) as sen4:
        with pytest.raises((ValueError, FileNotFoundError)):
            _freeze(prep, root_e, tmp_path / "d4.json")
    assert sen4["connects"] == 0


# --- T06-T08: real gold-validation outcomes --------------------------------------------

def test_t06_one_real_bad_gold_is_excluded(tmp_path, monkeypatch):
    """One gold naming an absent table: 1 gold_error, 7 eligible, 8 planned -- and no
    prediction-side outcome anywhere in the document."""
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    bad_sql = "SELECT * FROM absent_table_t06"
    _mutate_dev_json(root, lambda r: r.__setitem__(
        0, {**r[0], "SQL": bad_sql}))
    tasks = load_bird(root)
    bad_name = next(t.name for t in tasks if t.gold_sql == bad_sql)

    draw = tmp_path / "draw.json"
    sha = _freeze(prep, root, draw)
    supp = tmp_path / "supp.json"
    with _sentries(monkeypatch, prep) as sen:
        _validate(prep, root, draw, supp, sha)
    assert sen["ex"] == len(tasks)  # every gold really executed
    doc = json.loads(supp.read_bytes())
    _assert_supp_doc(doc, draw_sha=sha)
    assert doc["status"] == "complete"
    assert doc["usable"] is True
    assert len(doc["planned_ids"]) == len(tasks)
    assert len(doc["eligible_ids"]) == len(tasks) - 1
    assert doc["exclusions"] == [
        {"id": bad_name, "status": "gold_error",
         "category": "gold_execution_rejection"}]
    # No policy outcome leaked in: the only statuses present are the gold defect.
    assert {e["status"] for e in doc["exclusions"]} == {"gold_error"}
    expected_excluded = {t: 0 for t in TIERS}
    expected_excluded.update(_tier_counts([bad_name], tasks))
    assert doc["counts"]["excluded"] == expected_excluded


def test_t07_row_cap_boundary_permits_two_truncates_three(tmp_path):
    """`max_rows=2`: a gold returning exactly 2 rows stays eligible; one returning 3
    produces exactly 1 gold_truncated with the configured-row-bound category."""
    prep = _prep()
    recs = [
        _record(0, "SELECT name FROM county WHERE region = 'Bay Area'", "simple"),
        _record(1, "SELECT COUNT(*) FROM school", "moderate"),
        _record(2, "SELECT name FROM county WHERE county_id <= 3", "challenging"),
    ]
    root = _write_corpus(tmp_path / "corpus", recs)
    draw = tmp_path / "draw.json"
    sha = _freeze(prep, root, draw, per_tier=ONE_EACH, max_rows=2)
    supp = tmp_path / "supp.json"
    _validate(prep, root, draw, supp, sha)
    doc = json.loads(supp.read_bytes())
    assert doc["status"] == "complete"
    assert doc["usable"] is True
    assert set(doc["eligible_ids"]) == {"bird-0000", "bird-0001"}
    assert doc["exclusions"] == [
        {"id": "bird-0002", "status": "gold_truncated",
         "category": "configured_row_bound"}]


def test_t08_recursive_gold_times_out_inside_two_seconds(tmp_path):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    recursive = ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) "
                 "SELECT COUNT(*) FROM r")
    _mutate_dev_json(root, lambda r: r.__setitem__(
        5, {**r[5], "SQL": recursive}))
    tasks = load_bird(root)
    slow = next(t.name for t in tasks if t.gold_sql == recursive)

    start = time.monotonic()
    draw = tmp_path / "draw.json"
    sha = _freeze(prep, root, draw, timeout_s=0.02)
    supp = tmp_path / "supp.json"
    _validate(prep, root, draw, supp, sha)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"deadline did not fire: {elapsed:.2f}s"

    doc = json.loads(supp.read_bytes())
    assert doc["exclusions"] == [
        {"id": slow, "status": "gold_timeout", "category": "configured_deadline"}]
    assert len(doc["eligible_ids"]) == len(tasks) - 1


# --- T09 / T10: identity and drift -------------------------------------------------------

def test_t09_wrong_retained_digest_rejects_before_corpus_or_sql(tmp_path,
                                                               monkeypatch):
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    supp = tmp_path / "supp.json"
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((ValueError, TypeError)):
            _validate(prep, root, draw, supp, "0" * 64)
    assert sen["loads"] == 0
    assert sen["connects"] == 0
    assert not supp.exists()

    # Same bytes, wrong-case hex: the retained digest is an exact string, not a hash
    # family. Still refused before any corpus work.
    with _sentries(monkeypatch, prep) as sen2:
        with pytest.raises((ValueError, TypeError)):
            _validate(prep, root, draw, tmp_path / "s2.json", sha.upper())
    assert sen2["loads"] == 0
    assert sen2["connects"] == 0


def test_t09_absent_draw_file_rejects(tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((FileNotFoundError, ValueError)):
            _validate(prep, root, tmp_path / "missing.json",
                      tmp_path / "s.json", "0" * 64)
    assert sen["connects"] == 0


@pytest.mark.parametrize("drift", ["manifest", "database", "settings"])
def test_t09_post_freeze_drift_rejects(tmp_path, monkeypatch, drift):
    """Changing the manifest, a selected database or a frozen setting after the draw
    must make validation refuse, and refuse before any SQL."""
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    supp = tmp_path / "supp.json"

    if drift == "manifest":
        _mutate_dev_json(root, lambda r: r.__setitem__(
            slice(0, 2), [r[1], r[0]]))  # swap two records -> bytes change
    elif drift == "database":
        dbf = _db_file(root)
        dbf.write_bytes(dbf.read_bytes() + b"\x00drift")
    else:
        doc = json.loads(draw.read_bytes())
        doc["settings"]["comparison"] = "multiset"
        raw = _canonical_bytes(doc)
        draw.write_bytes(raw)
        sha = _sha256(raw)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(ValueError):
            _validate(prep, root, draw, supp, sha)
    assert sen["connects"] == 0
    assert not supp.exists()


def test_t09_source_drift_rejects_in_copied_tree(tmp_path):
    """Source drift is simulated against a COPIED source tree: repository sources are
    never edited. The copy's `bench/prepare.py` hashes the copy's files, so editing the
    copy between freeze and validate must make validation refuse."""
    proj = _copy_source_tree(tmp_path / "proj")
    with _mounted_copy(proj):
        prep = importlib.import_module("bench.prepare")
        copy_fixture = importlib.import_module("bench.fixture")
        root = copy_fixture.materialize(tmp_path / "corpus")
        draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
        sha = prep.freeze_draw(root, draw, seed=0, per_tier=dict(FULL), fixture=True)

        score_py = proj / "bench" / "score.py"
        score_py.write_bytes(score_py.read_bytes() + b"\n# source drift\n")

        with pytest.raises(ValueError):
            prep.validate_draw(root, draw, supp, expected_draw_sha256=sha)
        assert not supp.exists()


def test_t10_database_replaced_between_open_and_stat_refuses(tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    database = _db_file(root).resolve()
    output = tmp_path / "draw.json"
    real_open = builtins.open
    replacements = []

    def replaced(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        if (mode == "rb" and isinstance(path, (str, os.PathLike))
                and Path(path) == database and not replacements):
            replacement = database.with_name("replacement.sqlite")
            replacement.write_bytes(database.read_bytes())
            os.replace(replacement, database)
            replacements.append(1)
        return handle

    monkeypatch.setattr(builtins, "open", replaced)
    with _sentries(monkeypatch, prep) as sentries:
        with pytest.raises(prep.PreparationError):
            _freeze(prep, root, output)
    assert replacements == [1]
    assert sentries["connects"] == 0
    assert not output.exists()


@pytest.mark.parametrize("operation", ("freeze", "validate"))
def test_t10_source_change_during_final_reload_refuses(
        tmp_path, monkeypatch, operation):
    project = _copy_source_tree(tmp_path / "project")
    with _mounted_copy(project):
        prep = importlib.import_module("bench.prepare")
        copied_fixture = importlib.import_module("bench.fixture")
        root = copied_fixture.materialize(tmp_path / "corpus")
        draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
        if operation == "validate":
            digest = _freeze(prep, root, draw)
        real_corpus = prep._corpus
        loads = []

        def changed(*args, **kwargs):
            result = real_corpus(*args, **kwargs)
            loads.append(1)
            if len(loads) == 2:
                source = project / "bench" / "score.py"
                source.write_bytes(source.read_bytes() + b"\n# final-load drift\n")
            return result

        monkeypatch.setattr(prep, "_corpus", changed)
        with pytest.raises(prep.PreparationError):
            if operation == "freeze":
                _freeze(prep, root, draw)
            else:
                _validate(prep, root, draw, supplement, digest)
        assert len(loads) == 2
        assert not (draw if operation == "freeze" else supplement).exists()


@pytest.mark.parametrize("drift", ["manifest", "database", "wal"])
def test_t10_drift_during_validation_blocks_publication(tmp_path, monkeypatch,
                                                        drift):
    """Drift that lands BETWEEN the pre-validation identity check and the
    post-validation recheck must still block publication. The mutation fires on the
    second real scorer call, so earlier tasks were genuinely validated first."""
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    supp = tmp_path / "supp.json"
    dbf = _db_file(root)

    def mutate_once():
        if drift == "manifest":
            recs = fixture.records()
            _mutate_dev_json(root, lambda r: r.append(
                dict(recs[0], question_id=99)))
        elif drift == "database":
            dbf.write_bytes(dbf.read_bytes() + b"\x00drift")
        else:
            Path(str(dbf) + "-wal").write_bytes(b"")

    calls = {"n": 0}
    real_ex = bench.score.execution_accuracy

    def mutating(predicted, task, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            mutate_once()
        return real_ex(predicted, task, *a, **k)

    monkeypatch.setattr(bench.score, "execution_accuracy", mutating)
    _patch_aliases(monkeypatch, prep, real_ex, mutating)

    with pytest.raises((ValueError, RuntimeError, OSError)):
        _validate(prep, root, draw, supp, sha)
    assert calls["n"] >= 2        # real scoring ran before the drift landed
    assert not supp.exists()


def test_t10_sidecar_rejected_before_validation(tmp_path, monkeypatch):
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    dbf = _db_file(root)
    Path(str(dbf) + "-wal").write_bytes(b"")
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((ValueError, RuntimeError)):
            _validate(prep, root, draw, tmp_path / "s.json", sha)
    assert sen["connects"] == 0


def test_t10_sidecar_rejected_before_freeze(tmp_path, monkeypatch):
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    dbf = _db_file(root)
    Path(str(dbf) + "-shm").write_bytes(b"")
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises((ValueError, RuntimeError)):
            _freeze(prep, root, tmp_path / "draw.json")
    assert sen["connects"] == 0


# --- T11: serialization hygiene ---------------------------------------------------------

def test_t11_no_sentinels_paths_or_error_details_in_documents(tmp_path):
    prep = _prep()
    sent_question = "SENTINEL_QUESTION_9f3e"
    sent_evidence = "SENTINEL_EVIDENCE_7a1b"
    sent_sql = "SENTINEL_SQL_c4d2"
    sent_table = "sentinel_error_table_e8f9"
    sent_dir = "SENTINEL_PATH_d3c9"

    recs = [
        _record(0, f"SELECT '{sent_sql}'", "simple",
                question=sent_question, evidence=sent_evidence),
        _record(1, "SELECT COUNT(*) FROM school", "moderate"),
        _record(2, f"SELECT * FROM {sent_table}", "challenging"),
    ]
    root = _write_corpus(tmp_path / sent_dir / "corpus", recs)
    draw = tmp_path / sent_dir / "draw.json"
    supp = tmp_path / sent_dir / "supp.json"
    sha = _freeze(prep, root, draw, per_tier=ONE_EACH)
    supp_sha = _validate(prep, root, draw, supp, sha)

    sentinels = [sent_question, sent_evidence, sent_sql, sent_table,
                 sent_dir, "no such table", str(tmp_path), str(root)]
    for blob in (draw.read_bytes(), supp.read_bytes()):
        text = blob.decode("utf-8")
        for sentinel in sentinels:
            assert sentinel not in text, sentinel

    sdoc = json.loads(supp.read_bytes())
    assert _sha256(supp.read_bytes()) == supp_sha
    assert sdoc["exclusions"] == [
        {"id": "bird-0002", "status": "gold_error",
         "category": "gold_execution_rejection"}]

    for doc in (json.loads(draw.read_bytes()), sdoc):
        leaked = set(_walk_keys(doc)) & FORBIDDEN_KEYS
        assert leaked == set(), leaked


# --- T12 / T13: publication atomicity -----------------------------------------------------

@pytest.mark.parametrize("which", ["freeze", "validate"])
@pytest.mark.parametrize("scenario", ["existing", "symlink", "race"])
def test_t12_publication_is_exclusive_and_never_clobbers(tmp_path, monkeypatch,
                                                        which, scenario):
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    target = tmp_path / ("draw2.json" if which == "freeze" else "supp.json")
    sentinel = b"SENTINEL-BYTES-PREEXISTING\n"

    if scenario == "existing":
        target.write_bytes(sentinel)
    elif scenario == "symlink":
        backing = tmp_path / "backing.json"
        backing.write_bytes(sentinel)
        target.symlink_to(backing)
    else:
        _race_publication(monkeypatch, target, sentinel)

    def run():
        if which == "freeze":
            return _freeze(prep, root, target, seed=1)
        return _validate(prep, root, draw, target, sha)

    with pytest.raises(FileExistsError):
        run()

    if scenario == "symlink":
        assert target.is_symlink()
        assert (tmp_path / "backing.json").read_bytes() == sentinel
    else:
        assert target.read_bytes() == sentinel


@pytest.mark.parametrize("which", ["freeze", "validate"])
@pytest.mark.parametrize("fault", ["fsync", "unwritable-dir"])
def test_t13_precommit_failure_leaves_no_final(tmp_path, monkeypatch, which, fault):
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    out_dir = tmp_path / "pub"
    out_dir.mkdir()
    target = out_dir / "out.json"

    if fault == "fsync":
        def failing(fd):
            raise OSError("injected fsync failure")
        monkeypatch.setattr(os, "fsync", failing)
    else:
        os.chmod(out_dir, 0o555)

    try:
        def run():
            if which == "freeze":
                return _freeze(prep, root, target, seed=1)
            return _validate(prep, root, draw, target, sha)
        with pytest.raises((OSError, ValueError, RuntimeError)):
            run()
    finally:
        if fault == "unwritable-dir":
            os.chmod(out_dir, 0o755)

    assert not target.exists()


@pytest.mark.parametrize("which", ["freeze", "validate"])
def test_t13_postcommit_dirsync_failure_is_indeterminate(tmp_path, monkeypatch,
                                                        which):
    """Failure after the exclusive commit point: the document exists, parses, and is
    complete -- and the error is `PublicationIndeterminateError`, never silent."""
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    target = tmp_path / ("draw2.json" if which == "freeze" else "supp.json")
    _fail_directory_open(monkeypatch)

    def run():
        if which == "freeze":
            return _freeze(prep, root, target, seed=1)
        return _validate(prep, root, draw, target, sha)

    with pytest.raises(prep.PublicationIndeterminateError):
        run()

    assert target.is_file()
    doc = json.loads(target.read_bytes())   # never partial JSON
    if which == "freeze":
        assert set(doc) == DRAW_DOC_KEYS
    else:
        assert set(doc) == SUPP_DOC_KEYS


# --- T14: isolated interpreter -------------------------------------------------------------

_ISOLATED_CHILD = r"""
import importlib.abc
import json
import sys
from pathlib import Path

REPO = sys.argv[1]
TMP = Path(sys.argv[2])
sys.path.insert(0, REPO)

BLOCKED = {
    "train", "verifiers", "ledger", "step2", "torch", "transformers", "trl",
    "peft", "datasets", "openai", "anthropic", "litellm", "vllm", "requests",
    "httpx", "urllib3", "socket", "ssl", "http", "urllib", "pip",
}

class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".", 1)[0] in BLOCKED:
            raise ImportError("forbidden import: " + name)
        return None

sys.meta_path.insert(0, _Block())

# The guard must actually fire before it is evidence of anything.
for bad in ("socket", "verifiers", "train", "requests", "openai", "transformers"):
    try:
        __import__(bad)
    except ImportError:
        pass
    else:
        print("GUARD-FAIL", bad)
        sys.exit(3)

from bench import fixture
import bench.prepare as prep

root = fixture.materialize(TMP / "corpus")
draw = TMP / "draw.json"
supp = TMP / "supp.json"
sha = prep.freeze_draw(root, draw, seed=0,
                       per_tier={"simple": 2, "moderate": 3, "challenging": 3},
                       fixture=True)
supp_sha = prep.validate_draw(root, draw, supp, expected_draw_sha256=sha)
doc = json.loads(supp.read_bytes())
assert doc["usable"] is True
assert len(doc["eligible_ids"]) == 8
print("OK")
"""


def test_t14_isolated_interpreter_runs_flow_without_forbidden_imports(tmp_path):
    """A fresh `-I -B` interpreter with train/verifiers/provider/network imports
    blocked must still import `bench.prepare` and run the full fixture flow."""
    _prep()  # fail here, not inside the subprocess, if the module is missing
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _ISOLATED_CHILD,
         str(REPO), str(tmp_path)],
        capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --- T15: strict document admission --------------------------------------------------------

def _doc_mutations(raw: bytes, doc: dict) -> dict:
    cases = {
        "noncanonical-pretty": json.dumps(doc, indent=2).encode(),
        "duplicate-key": b'{"usable":false,' + raw[1:],
        "trailing-byte": raw + b"\n",
        "nan-setting": raw.replace(b'"timeout_s":30.0', b'"timeout_s":NaN'),
        "inf-setting": raw.replace(b'"timeout_s":30.0', b'"timeout_s":1e999'),
    }
    mutations = {
        "unknown-key": lambda d: d.__setitem__("bogus", 1),
        "missing-key": lambda d: d.pop("usable"),
        "missing-identity": lambda d: d.pop("identity"),
        "bool-version": lambda d: d.__setitem__("version", True),
        "float-version": lambda d: d.__setitem__("version", 1.0),
        "wrong-version": lambda d: d.__setitem__("version", 2),
        "wrong-stage": lambda d: d.__setitem__("stage", "gold-validation"),
        "wrong-kind": lambda d: d.__setitem__("kind", "x"),
        "measurement-true": lambda d: d.__setitem__("measurement", True),
        "model_calls-true": lambda d: d.__setitem__("model_calls", True),
        "usable-true": lambda d: d.__setitem__("usable", True),
        "status-bogus": lambda d: d.__setitem__("status", "bogus"),
        "status-underfilled": lambda d: d.__setitem__("status", "underfilled"),
        "granularity-coarse": lambda d: d["settings"].__setitem__(
            "granularity", "coarse"),
        "comparison-multiset": lambda d: d["settings"].__setitem__(
            "comparison", "multiset"),
        "extra-settings-key": lambda d: d["settings"].__setitem__("bogus", 1),
        "ghost-planned-id": lambda d: d["planned"][0].__setitem__(
            "id", "ghost-9999"),
    }
    for name, mutate in mutations.items():
        d = json.loads(raw)
        mutate(d)
        cases[name] = _canonical_bytes(d)
    return cases


@pytest.mark.parametrize("case_name", sorted(set([
    "noncanonical-pretty", "duplicate-key", "trailing-byte", "nan-setting",
    "inf-setting", "unknown-key", "missing-key", "missing-identity",
    "bool-version", "float-version", "wrong-version", "wrong-stage", "wrong-kind",
    "measurement-true", "model_calls-true", "usable-true", "status-bogus",
    "status-underfilled", "granularity-coarse", "comparison-multiset",
    "extra-settings-key", "ghost-planned-id"])))
def test_t15_malformed_draw_documents_reject_before_sql(tmp_path, monkeypatch,
                                                        case_name):
    """Duplicate keys, noncanonical bytes, unknown/missing/wrongly-typed fields and a
    planned id that cannot be re-resolved all refuse before any SQL."""
    prep = _prep()
    root, draw, _ = _staged_draw(prep, tmp_path)
    raw = draw.read_bytes()
    doc = json.loads(raw)
    tampered = _doc_mutations(raw, doc)[case_name]

    bad_draw = tmp_path / f"draw-{case_name}.json"
    bad_draw.write_bytes(tampered)
    bad_sha = _sha256(tampered)
    supp = tmp_path / f"supp-{case_name}.json"
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(ValueError):
            _validate(prep, root, bad_draw, supp, bad_sha)
    assert sen["connects"] == 0
    assert not supp.exists()


def test_t15_nondefault_bounds_require_the_fixture_flag_in_document(tmp_path,
                                                                  monkeypatch):
    """A document claiming fixture=false while carrying non-production bounds is not
    a valid fixture declaration and must be refused."""
    prep = _prep()
    root, draw, _ = _staged_draw(prep, tmp_path, timeout_s=0.02)
    raw = draw.read_bytes()
    doc = json.loads(raw)
    doc["fixture"] = False
    tampered = _canonical_bytes(doc)
    draw.write_bytes(tampered)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(ValueError):
            _validate(prep, root, draw, tmp_path / "s.json", _sha256(tampered))
    assert sen["connects"] == 0


# --- T16: unusable draws, blocked supplements, bad exclusions ------------------------------

def test_t16_zero_eligible_completes_but_is_unusable(tmp_path):
    """A draw whose golds ALL fail still publishes a complete supplement; it is simply
    not usable."""
    prep = _prep()
    recs = [
        _record(0, "SELECT * FROM missing_t16_a", "simple"),
        _record(1, "SELECT * FROM missing_t16_b", "moderate"),
        _record(2, "SELECT * FROM missing_t16_c", "challenging"),
    ]
    root = _write_corpus(tmp_path / "corpus", recs)
    draw = tmp_path / "draw.json"
    sha = _freeze(prep, root, draw, per_tier=ONE_EACH)
    supp = tmp_path / "supp.json"
    _validate(prep, root, draw, supp, sha)
    doc = json.loads(supp.read_bytes())
    _assert_supp_doc(doc, draw_sha=sha)
    assert doc["status"] == "complete"
    assert doc["usable"] is False
    assert doc["eligible_ids"] == []
    assert {e["status"] for e in doc["exclusions"]} == {"gold_error"}
    assert doc["counts"]["excluded"] == {"simple": 1, "moderate": 1,
                                        "challenging": 1}
    assert doc["counts"]["eligible"] == {t: 0 for t in TIERS}


def test_t16_db_missing_blocks_the_supplement(tmp_path, monkeypatch):
    """One injected db_missing outcome: status becomes blocked and usable stays false.
    Injection substitutes exactly one ExResult; every other task is really scored, and
    every post-validation identity is unchanged, which is what makes a blocked
    supplement publishable at all."""
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    tasks = load_bird(root)
    victim = tasks[0].name

    def override(task):
        if task.name == victim:
            return ExResult(0.0, "db_missing", False, "injected db_missing")
        return None

    _inject_gold_outcome(monkeypatch, prep, override)
    supp = tmp_path / "supp.json"
    _validate(prep, root, draw, supp, sha)
    doc = json.loads(supp.read_bytes())
    _assert_supp_doc(doc, draw_sha=sha)
    assert doc["status"] == "blocked"
    assert doc["usable"] is False
    assert doc["exclusions"] == [
        {"id": victim, "status": "db_missing",
         "category": "database_availability"}]
    assert len(doc["eligible_ids"]) == len(tasks) - 1


def test_t16_reversed_real_exclusions_preserve_planned_order(tmp_path, monkeypatch):
    prep = _prep()
    root = _write_corpus(tmp_path / "corpus", [
        _record(0, "SELECT * FROM absent_simple", "simple"),
        _record(1, "SELECT 1", "moderate"),
        _record(2, "SELECT * FROM absent_challenging", "challenging"),
    ])
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    digest = _freeze(prep, root, draw, per_tier=ONE_EACH)
    planned = [entry["id"] for entry in json.loads(draw.read_bytes())["planned"]]
    expected = [planned[0], planned[2]]
    injected = []

    def reverse(tasks, broken):
        result = list(reversed(broken))
        injected.extend(task.name for task, _ in result)
        return result

    _inject_broken_list(monkeypatch, prep, reverse)
    _validate(prep, root, draw, supplement, digest)
    document = json.loads(supplement.read_bytes())
    assert injected == list(reversed(expected))
    assert [entry["id"] for entry in document["exclusions"]] == expected
    assert document["eligible_ids"] == [planned[1]]


@pytest.mark.parametrize("case", ["unexpected_status", "duplicate", "unknown_id",
                                  "mismatched_task", "infrastructure"])
def test_t16_bad_exclusions_or_infrastructure_abort_publication(
        tmp_path, monkeypatch, case):
    """Statuses outside the gold-validation vocabulary, duplicate or unplanned
    exclusion ids, and infrastructure exceptions all abort publication entirely."""
    prep = _prep()
    root, draw, sha = _staged_draw(prep, tmp_path)
    tasks = load_bird(root)
    supp = tmp_path / "supp.json"

    if case == "unexpected_status":
        _inject_gold_outcome(
            monkeypatch, prep,
            lambda task: (ExResult(0.0, "pred_error", False, "injected")
                          if task.name == tasks[0].name else None))
    elif case == "infrastructure":
        real = bench.score.execution_accuracy

        def boom(predicted, task, *a, **k):
            if task.name == tasks[0].name:
                raise RuntimeError("injected infrastructure failure")
            return real(predicted, task, *a, **k)

        monkeypatch.setattr(bench.score, "execution_accuracy", boom)
        _patch_aliases(monkeypatch, prep, real, boom)
    elif case == "duplicate":
        def dup(tasks_, broken):
            victim = tasks_[0]
            return [(victim, ExResult(0.0, "gold_error", False, "")),
                    (victim, ExResult(0.0, "gold_error", False, ""))]
        _inject_broken_list(monkeypatch, prep, dup)
    elif case == "mismatched_task":
        def mismatched(tasks_, broken):
            altered = dataclasses.replace(tasks_[0], question="changed content")
            return [(altered, ExResult(0.0, "gold_error", False, ""))]
        _inject_broken_list(monkeypatch, prep, mismatched)
    else:
        def ghost(tasks_, broken):
            phantom = dataclasses.replace(tasks_[0], name="ghost-9999")
            return [(phantom, ExResult(0.0, "gold_error", False, ""))]
        _inject_broken_list(monkeypatch, prep, ghost)

    with pytest.raises((ValueError, RuntimeError, OSError)):
        _validate(prep, root, draw, supp, sha)
    assert not supp.exists()
