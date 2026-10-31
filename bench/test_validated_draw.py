"""Tests for `bench.prepare.load_validated_draw` -- the read-only validated-draw consumer.

Spec: `spec/bird-validated-draw.md`.

The same disciplines as `bench/test_prepare.py` apply:

**Fixtures are real publications.** Every test stages a synthetic fixture corpus
through the existing `freeze_draw`/`validate_draw` publishers and consumes the
retained digests they return. Corruption cases rewrite the published bytes and
recompute only the independently retained *fixture* digests so deeper checks are
reached; nothing repins historical or real-corpus evidence.

**Guard spies are installed last.** Fixture preparation legitimately runs SQL;
the consumer must not. `_sentries` wraps the corpus loader, selector, scorer and
`sqlite3.connect` only after the artifacts exist, so consumer-side corpus,
selection, validation or query work is counted.

`bench.prepare` is imported lazily inside test bodies, matching
`test_prepare.py`: a missing `load_validated_draw` fails the test it belongs to,
not collection of the file.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import platform
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

import bench.loader  # noqa: E402
from bench import fixture  # noqa: E402
from bench.loader import load_bird  # noqa: E402
from bench.score import ExResult  # noqa: E402

from bench.test_prepare import (  # noqa: E402
    ASKED,
    FULL,
    ONE_EACH,
    _canonical_bytes,
    _copy_source_tree,
    _db_file,
    _freeze,
    _inject_gold_outcome,
    _mounted_copy,
    _mutate_dev_json,
    _patch_aliases,
    _prep,
    _record,
    _sentries,
    _sha256,
    _write_corpus,
)

_MIB = 1024 * 1024
_OVER_LIMIT = 16 * _MIB + 1


# --- helpers -----------------------------------------------------------------


def _load(prep, root, draw, supp, draw_sha, supp_sha, *, fixture=True):
    """The consumer call under test. `fixture=True` is the explicit opt-in the
    fixture-flagged documents require; refusal cases pass other values."""
    return prep.load_validated_draw(
        root,
        draw,
        supp,
        expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha,
        fixture=fixture,
    )


def _staged_validated(prep, tmp_path, name="corpus", *,
                      bad_sql="SELECT * FROM absent_table_vd"):
    """A real frozen draw plus a real published supplement with exactly one
    gold-error exclusion (record 0's gold names an absent table). Returns
    (root, draw, draw_sha, supp, supp_sha)."""
    root = fixture.materialize(tmp_path / name)
    _mutate_dev_json(root, lambda r: r.__setitem__(0, {**r[0], "SQL": bad_sql}))
    draw = tmp_path / f"{name}-draw.json"
    supp = tmp_path / f"{name}-supp.json"
    draw_sha = _freeze(prep, root, draw)
    supp_sha = prep.validate_draw(root, draw, supp, expected_draw_sha256=draw_sha)
    return root, draw, draw_sha, supp, supp_sha


def _rewrite_canonical(path: Path, doc: dict) -> str:
    """Republish tampered fixture bytes and return the recomputed retained
    digest -- the only digest recomputation the spec allows for corruption."""
    raw = _canonical_bytes(doc)
    path.write_bytes(raw)
    return _sha256(raw)


# --- numeric contract, ordering, immutability ---------------------------------


def test_numeric_contract_ordering_and_immutability(tmp_path, monkeypatch):
    """8 planned / 1 invalid gold / 7 eligible / 1 ordered exclusion. The planned
    denominator stays the original 8; names, order and SqlTask fields survive."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    tasks = load_bird(root)
    by_name = {t.name: t for t in tasks}
    ddoc = json.loads(draw.read_bytes())
    sdoc = json.loads(supp.read_bytes())
    planned_ids = [p["id"] for p in ddoc["planned"]]
    assert len(planned_ids) == len(tasks) == len(fixture.records())
    excluded_id = sdoc["exclusions"][0]["id"]

    with _sentries(monkeypatch, prep) as sen:
        result = _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["connects"] == 0      # the consumer runs no SQL
    assert sen["selects"] == 0       # no redraw
    assert sen["golds"] == 0         # no re-validation
    assert sen["ex"] == 0

    assert type(result.planned) is tuple
    assert type(result.eligible) is tuple
    assert type(result.exclusions) is tuple
    assert [t.name for t in result.planned] == planned_ids
    assert result.planned == tuple(by_name[i] for i in planned_ids)
    assert len(result.planned) == len(planned_ids)  # denominator includes exclusions
    assert [t.name for t in result.eligible] == [
        i for i in planned_ids if i != excluded_id]
    assert len(result.eligible) == len(planned_ids) - 1

    assert len(result.exclusions) == 1
    excl = result.exclusions[0]
    assert dataclasses.is_dataclass(excl)
    assert (excl.id, excl.status, excl.category) == (
        excluded_id, "gold_error", "gold_execution_rejection")

    assert result.draw_sha256 == draw_sha
    assert result.supplement_sha256 == supp_sha
    assert result.fixture is True
    assert result.timeout_s == ddoc["settings"]["timeout_s"]
    assert result.max_rows == ddoc["settings"]["max_rows"]
    assert result.comparison == "set"

    # Host-side tasks keep their existing fields, oracle SQL included.
    assert result.planned[0].gold_sql == by_name[planned_ids[0]].gold_sql
    assert result.planned[0].tier == by_name[planned_ids[0]].tier

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.fixture = False
    with pytest.raises(dataclasses.FrozenInstanceError):
        excl.status = "pred_error"


def test_repeated_loads_equal_and_side_effect_free(tmp_path, monkeypatch):
    """Two loads produce equal frozen results; input bytes stay identical; no
    SQL, selection, gold validation or publication fires."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    draw_bytes, supp_bytes = draw.read_bytes(), supp.read_bytes()
    files_before = {p for p in tmp_path.rglob("*") if p.is_file()}

    publication = []

    def counted(name, fn):
        def inner(*a, **k):
            publication.append(name)
            return fn(*a, **k)
        return inner

    for name in ("link", "rename", "replace"):
        monkeypatch.setattr(os, name, counted(name, getattr(os, name)))

    with _sentries(monkeypatch, prep) as sen:
        first = _load(prep, root, draw, supp, draw_sha, supp_sha)
        second = _load(prep, root, draw, supp, draw_sha, supp_sha)

    assert first == second
    assert sen["connects"] == 0
    assert sen["selects"] == 0
    assert sen["golds"] == 0
    assert sen["ex"] == 0
    assert publication == []
    assert {p for p in tmp_path.rglob("*") if p.is_file()} == files_before
    assert draw.read_bytes() == draw_bytes
    assert supp.read_bytes() == supp_bytes


# --- digest admission ----------------------------------------------------------


@pytest.mark.parametrize("case", [
    "draw-bytes-corrupted", "draw-digest-wrong", "draw-digest-not-hex",
    "supplement-bytes-corrupted", "supplement-digest-wrong",
    "supplement-digest-not-hex",
])
def test_retained_digests_checked_before_parse_or_corpus(
        tmp_path, monkeypatch, case):
    """Corrupted document bytes and every wrong expected digest refuse before
    any JSON parse, corpus access, selection or SQL. Corruptions keep the bytes
    valid canonical JSON so only the retained-digest gate can be the refusal."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)

    if case == "draw-bytes-corrupted":
        raw = draw.read_bytes().replace(b'"bench-preparation"',
                                        b'"bench-xreparation"', 1)
        draw.write_bytes(raw)
    elif case == "draw-digest-wrong":
        draw_sha = "0" * 64
    elif case == "draw-digest-not-hex":
        draw_sha = "not-a-sha256"
    elif case == "supplement-bytes-corrupted":
        raw = supp.read_bytes().replace(b'"gold-validation"',
                                        b'"gold-validatioX"', 1)
        supp.write_bytes(raw)
    elif case == "supplement-digest-wrong":
        supp_sha = "0" * 64
    else:
        supp_sha = "not-a-sha256"

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError, match="digest"):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0
    assert sen["selects"] == 0


def test_supplement_digest_checked_before_draw_parse(tmp_path, monkeypatch):
    """A malformed draw whose RETAINED digest matches, paired with a wrong
    supplement digest, must refuse on the supplement digest -- before the draw
    is parsed at all."""
    prep = _prep()
    root, draw, _draw_sha, supp, _supp_sha = _staged_validated(prep, tmp_path)
    broken_raw = b"{this is not valid json"
    draw.write_bytes(broken_raw)
    broken_sha = _sha256(broken_raw)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError, match="supplement"):
            _load(prep, root, draw, supp, broken_sha, "0" * 64)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


# --- strict document admission -------------------------------------------------

_SUPP_MUTATIONS = {
    "extra-key": lambda d: d.__setitem__("bogus", 1),
    "missing-key": lambda d: d.pop("usable"),
    "wrong-kind": lambda d: d.__setitem__("kind", "x"),
    "wrong-version": lambda d: d.__setitem__("version", 2),
    "bool-version": lambda d: d.__setitem__("version", True),
    "wrong-stage": lambda d: d.__setitem__("stage", "draw"),
    "measurement-true": lambda d: d.__setitem__("measurement", True),
    "model_calls-nonzero": lambda d: d.__setitem__("model_calls", 1),
    "model_calls-bool": lambda d: d.__setitem__("model_calls", True),
    "fixture-str": lambda d: d.__setitem__("fixture", "yes"),
    "usable-false": lambda d: d.__setitem__("usable", False),
    "usable-str": lambda d: d.__setitem__("usable", "yes"),
    "status-bogus": lambda d: d.__setitem__("status", "bogus"),
    "status-blocked": lambda d: d.__setitem__("status", "blocked"),
    "identity_checked-false": lambda d: d.__setitem__("identity_checked", False),
    "identity_checked-str": lambda d: d.__setitem__("identity_checked", "yes"),
    "draw-sha-mismatch": lambda d: d.__setitem__("draw_sha256", "0" * 64),
    "draw-sha-nothex": lambda d: d.__setitem__("draw_sha256", "z" * 64),
    "planned-duplicate": lambda d: d.__setitem__(
        "planned_ids", d["planned_ids"] + d["planned_ids"][:1]),
    "planned-reordered": lambda d: d.__setitem__(
        "planned_ids", list(reversed(d["planned_ids"]))),
    "planned-unknown-id": lambda d: d.__setitem__(
        "planned_ids", ["ghost-9999"] + d["planned_ids"][1:]),
    "planned-not-list": lambda d: d.__setitem__("planned_ids", "x"),
    "eligible-reordered": lambda d: d.__setitem__(
        "eligible_ids", list(reversed(d["eligible_ids"]))),
    "eligible-unknown-id": lambda d: d.__setitem__(
        "eligible_ids", d["eligible_ids"] + ["ghost-9999"]),
    "partition-overlap": lambda d: d.__setitem__(
        "eligible_ids", d["eligible_ids"] + [d["exclusions"][0]["id"]]),
    "partition-incomplete": lambda d: d.__setitem__(
        "eligible_ids", d["eligible_ids"][:-1]),
    "exclusion-not-list": lambda d: d.__setitem__("exclusions", {}),
    "exclusion-extra-key": lambda d: d["exclusions"][0].__setitem__("bogus", 1),
    "exclusion-unknown-status": lambda d: d["exclusions"][0].__setitem__(
        "status", "pred_error"),
    "exclusion-wrong-category": lambda d: d["exclusions"][0].__setitem__(
        "category", "configured_deadline"),
    "exclusion-unknown-id": lambda d: d["exclusions"][0].__setitem__(
        "id", "ghost-9999"),
    "exclusion-duplicate": lambda d: d["exclusions"].append(
        dict(d["exclusions"][0])),
    "settings-extra-key": lambda d: d["settings"].__setitem__("bogus", 1),
    "settings-comparison": lambda d: d["settings"].__setitem__(
        "comparison", "multiset"),
    "settings-timeout-str": lambda d: d["settings"].__setitem__(
        "timeout_s", "30.0"),
    "settings-rows-out-of-range": lambda d: d["settings"].__setitem__(
        "max_rows", 500001),
    "counts-planned-wrong": lambda d: d["counts"]["planned"].__setitem__(
        "simple", 99),
    "counts-missing-tier": lambda d: d["counts"]["planned"].pop("simple"),
    "counts-nonint": lambda d: d["counts"]["eligible"].__setitem__(
        "simple", "7"),
    "counts-missing-part": lambda d: d["counts"].pop("excluded"),
    "shapes-fine-wrong": lambda d: d["shapes"]["planned"].__setitem__(
        "fine", 99),
    "shapes-missing-coarse": lambda d: d["shapes"]["planned"].pop("coarse"),
    "shapes-missing-part": lambda d: d["shapes"].pop("eligible"),
}


@pytest.mark.parametrize("case", sorted(_SUPP_MUTATIONS))
def test_supplement_schema_mutation_refuses(tmp_path, monkeypatch, case):
    """Each named mutation of the supplement gets its own refusal. Tampered
    fixture bytes are republished canonically with a recomputed retained digest
    so the semantic check -- not the digest gate -- is what fires."""
    prep = _prep()
    root, draw, draw_sha, supp, _ = _staged_validated(prep, tmp_path)
    doc = json.loads(supp.read_bytes())
    _SUPP_MUTATIONS[case](doc)
    new_sha = _rewrite_canonical(supp, doc)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, new_sha)
    assert sen["connects"] == 0
    assert sen["selects"] == 0
    assert sen["golds"] == 0


@pytest.mark.parametrize("case", ["reordered-plan", "unknown-plan-id", "in-range-row-mismatch"])
def test_supplement_relationship_refuses_after_coherent_partition(tmp_path, monkeypatch, case):
    """Reach cross-document checks without an earlier partition/bounds defect."""
    prep = _prep()
    root, draw, draw_sha, supp, _ = _staged_validated(prep, tmp_path)
    doc = json.loads(supp.read_bytes())
    if case == "in-range-row-mismatch":
        assert doc["settings"]["max_rows"] > 1
        doc["settings"]["max_rows"] = 1
        reason = "settings do not match the draw"
    else:
        if case == "reordered-plan":
            doc["planned_ids"].reverse()
            excluded = {entry["id"] for entry in doc["exclusions"]}
            doc["eligible_ids"] = [name for name in doc["planned_ids"] if name not in excluded]
            order = {name: index for index, name in enumerate(doc["planned_ids"])}
            doc["exclusions"].sort(key=lambda entry: order[entry["id"]])
        else:
            old = doc["planned_ids"][0]
            replacement = "unknown-coherent-plan-id"
            for key in ("planned_ids", "eligible_ids"):
                doc[key] = [replacement if name == old else name for name in doc[key]]
            for entry in doc["exclusions"]:
                if entry["id"] == old:
                    entry["id"] = replacement
        reason = "planned ids do not match the draw"
    new_sha = _rewrite_canonical(supp, doc)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError, match=reason):
            _load(prep, root, draw, supp, draw_sha, new_sha)
    assert sen["loads"] == sen["connects"] == sen["selects"] == sen["golds"] == 0


def _supp_byte_cases(raw: bytes) -> dict:
    doc = json.loads(raw)
    return {
        "noncanonical": json.dumps(doc, indent=2).encode(),
        "duplicate-key": b'{"usable":true,' + raw[1:],
        "malformed": b"{not json",
        "trailing-byte": raw + b"\x00",
        "not-utf8": b"\xff" + raw,
        "nan-setting": raw.replace(b'"timeout_s":30.0', b'"timeout_s":NaN'),
    }


@pytest.mark.parametrize("case", [
    "noncanonical", "duplicate-key", "malformed", "trailing-byte",
    "not-utf8", "nan-setting",
])
def test_supplement_byte_admission_refuses_before_corpus(
        tmp_path, monkeypatch, case):
    """Noncanonical bytes, duplicate keys, non-finite numbers and malformed
    input refuse before any corpus access. The retained digest is recomputed so
    the byte-level check is what fires."""
    prep = _prep()
    root, draw, draw_sha, supp, _ = _staged_validated(prep, tmp_path)
    raw = _supp_byte_cases(supp.read_bytes())[case]
    supp.write_bytes(raw)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, _sha256(raw))
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def _draw_cases(raw: bytes) -> dict:
    doc = json.loads(raw)
    cases = {
        "noncanonical": json.dumps(doc, indent=2).encode(),
        "duplicate-key": b'{"usable":false,' + raw[1:],
        "malformed": b"{not json",
        "not-utf8": b"\xff" + raw,
    }
    mutations = {
        "extra-key": lambda d: d.__setitem__("bogus", 1),
        "missing-key": lambda d: d.pop("planned"),
        "usable-true": lambda d: d.__setitem__("usable", True),
        "status-bogus": lambda d: d.__setitem__("status", "bogus"),
        "kind-wrong": lambda d: d.__setitem__("kind", "x"),
        "stage-wrong": lambda d: d.__setitem__("stage", "gold-validation"),
        "fixture-str": lambda d: d.__setitem__("fixture", "yes"),
        "version-two": lambda d: d.__setitem__("version", 2),
    }
    for name, mutate in mutations.items():
        d = json.loads(raw)
        mutate(d)
        cases[name] = _canonical_bytes(d)
    return cases


@pytest.mark.parametrize("case", [
    "noncanonical", "duplicate-key", "malformed", "not-utf8",
    "extra-key", "missing-key", "usable-true", "status-bogus",
    "kind-wrong", "stage-wrong", "fixture-str", "version-two",
])
def test_draw_admission_refuses(tmp_path, monkeypatch, case):
    """Malformed bytes, noncanonical serialization, unknown/missing keys and
    wrong draw constants (including usable=true -- the draw itself never
    becomes usable) all refuse. The retained draw digest is recomputed so the
    admission check is what fires."""
    prep = _prep()
    root, draw, _, supp, _ = _staged_validated(prep, tmp_path)
    raw = _draw_cases(draw.read_bytes())[case]
    draw.write_bytes(raw)

    # Repoint the supplement at the tampered draw so the relationship check
    # stays satisfied and the named draw defect is the only refusal candidate.
    tampered_sha = _sha256(raw)
    sdoc = json.loads(supp.read_bytes())
    sdoc["draw_sha256"] = tampered_sha
    new_supp_sha = _rewrite_canonical(supp, sdoc)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, tampered_sha, new_supp_sha)
    assert sen["connects"] == 0
    assert sen["selects"] == 0


# --- readiness refusal ----------------------------------------------------------


def test_underfilled_draw_refuses_before_corpus(tmp_path, monkeypatch):
    """An underfilled draw is a diagnostic, never consumable -- even when the
    supplement honestly names it."""
    prep = _prep()
    root, _draw, _sha, supp, _ssha = _staged_validated(prep, tmp_path)
    udraw = tmp_path / "u-draw.json"
    usha = _freeze(prep, root, udraw, per_tier=ASKED)
    sdoc = json.loads(supp.read_bytes())
    sdoc["draw_sha256"] = usha
    usupp_sha = _rewrite_canonical(supp, sdoc)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, udraw, supp, usha, usupp_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def test_blocked_supplement_refuses(tmp_path, monkeypatch):
    """A db_missing outcome blocks the supplement; a blocked supplement is not
    consumable."""
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
    draw_sha = _freeze(prep, root, draw)
    victim = load_bird(root)[0].name
    _inject_gold_outcome(
        monkeypatch, prep,
        lambda task: (ExResult(0.0, "db_missing", False, "injected")
                      if task.name == victim else None))
    supp_sha = prep.validate_draw(root, draw, supp,
                                  expected_draw_sha256=draw_sha)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def test_unusable_empty_supplement_refuses(tmp_path, monkeypatch):
    """A complete supplement with zero eligible tasks is unusable and refuses."""
    prep = _prep()
    root = _write_corpus(tmp_path / "corpus", [
        _record(0, "SELECT * FROM missing_a", "simple"),
        _record(1, "SELECT * FROM missing_b", "moderate"),
        _record(2, "SELECT * FROM missing_c", "challenging"),
    ])
    draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
    draw_sha = _freeze(prep, root, draw, per_tier=ONE_EACH)
    supp_sha = prep.validate_draw(root, draw, supp,
                                  expected_draw_sha256=draw_sha)
    assert json.loads(supp.read_bytes())["usable"] is False

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


@pytest.mark.parametrize("flag", [None, 1, "yes", 1.0])
def test_fixture_argument_requires_exact_bool(tmp_path, monkeypatch, flag):
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha, fixture=flag)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def test_fixture_argument_must_match_documents(tmp_path, monkeypatch):
    """fixture=False against fixture-flagged documents refuses; the opt-in must
    be explicit."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha, fixture=False)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def test_fixture_flags_must_agree_across_documents(tmp_path, monkeypatch):
    """A supplement declaring fixture=false against a fixture=true draw refuses;
    the two documents must agree."""
    prep = _prep()
    root, draw, draw_sha, supp, _ = _staged_validated(prep, tmp_path)
    sdoc = json.loads(supp.read_bytes())
    sdoc["fixture"] = False
    new_sha = _rewrite_canonical(supp, sdoc)

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, new_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0


def test_fixture_false_documents_load(tmp_path, monkeypatch):
    """The flag agreement works both ways: documents frozen and validated with
    fixture=false (production bounds) load under fixture=False."""
    prep = _prep()
    root = fixture.materialize(tmp_path / "corpus")
    _mutate_dev_json(root, lambda r: r.__setitem__(
        0, {**r[0], "SQL": "SELECT * FROM absent_table_vd"}))
    draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
    draw_sha = _freeze(prep, root, draw, fixture=False)
    supp_sha = prep.validate_draw(root, draw, supp,
                                  expected_draw_sha256=draw_sha)

    with _sentries(monkeypatch, prep) as sen:
        result = _load(prep, root, draw, supp, draw_sha, supp_sha,
                       fixture=False)
    assert sen["connects"] == 0
    assert result.fixture is False
    assert len(result.exclusions) == 1


# --- current identity and drift --------------------------------------------------


@pytest.mark.parametrize("drift", [
    "manifest", "task-content", "database", "sidecar-wal", "runtime",
])
def test_current_identity_drift_refuses_before_sql(
        tmp_path, monkeypatch, drift):
    """Independent drift of the manifest, task contents, a selected database,
    sidecar files or runtime identity refuses before any selection or SQL."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)

    if drift == "manifest":
        _mutate_dev_json(root, lambda r: r.__setitem__(
            slice(0, 2), [r[1], r[0]]))
    elif drift == "task-content":
        _mutate_dev_json(root, lambda r: r.__setitem__(
            0, {**r[0], "question": "drifted question"}))
    elif drift == "database":
        dbf = _db_file(root)
        dbf.write_bytes(dbf.read_bytes() + b"\x00drift")
    elif drift == "sidecar-wal":
        Path(str(_db_file(root)) + "-wal").write_bytes(b"")
    else:
        monkeypatch.setattr(platform, "python_version", lambda: "0.0.0-drift")

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["connects"] == 0
    assert sen["selects"] == 0


def test_source_drift_refuses_in_copied_tree(tmp_path):
    """Source drift is simulated against a COPIED source tree, never the real
    checkout. Editing the copy between publication and consumption refuses."""
    proj = _copy_source_tree(tmp_path / "proj")
    with _mounted_copy(proj):
        prep = importlib.import_module("bench.prepare")
        copied_fixture = importlib.import_module("bench.fixture")
        root = copied_fixture.materialize(tmp_path / "corpus")
        draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
        draw_sha = prep.freeze_draw(root, draw, seed=0, per_tier=dict(FULL),
                                    fixture=True)
        supp_sha = prep.validate_draw(root, draw, supp,
                                      expected_draw_sha256=draw_sha)

        score_py = proj / "bench" / "score.py"
        score_py.write_bytes(score_py.read_bytes() + b"\n# source drift\n")

        with pytest.raises(prep.PreparationError):
            prep.load_validated_draw(
                root, draw, supp,
                expected_draw_sha256=draw_sha,
                expected_supplement_sha256=supp_sha,
                fixture=True)


def test_drift_between_identity_passes_refuses(tmp_path, monkeypatch):
    """The consumer rechecks identity after resolution with a FRESH corpus load.
    Drift landing during the second load must still refuse -- and the second
    load must really have happened."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    real = bench.loader.load_bird
    loads = {"n": 0}

    def drifting(root_arg, *a, **k):
        result = real(root_arg, *a, **k)
        loads["n"] += 1
        if loads["n"] == 2:
            _mutate_dev_json(root, lambda r: r.__setitem__(
                0, {**r[0], "evidence": "late drift"}))
        return result

    monkeypatch.setattr(bench.loader, "load_bird", drifting)
    _patch_aliases(monkeypatch, prep, real, drifting)

    with pytest.raises(prep.PreparationError):
        _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert loads["n"] >= 2


# --- bounded input ----------------------------------------------------------------


@pytest.mark.parametrize("which", ["draw", "supplement"])
def test_document_over_sixteen_mib_refuses_before_parse_or_corpus(
        tmp_path, monkeypatch, which):
    """Each document above 16 MiB refuses before parsing or corpus access. The
    retained digest is computed over the oversized bytes so only the size gate
    can be the refusal."""
    prep = _prep()
    root, draw, draw_sha, supp, supp_sha = _staged_validated(prep, tmp_path)
    big = b"0" * _OVER_LIMIT
    big_sha = _sha256(big)

    if which == "draw":
        draw.write_bytes(big)
        draw_sha = big_sha
    else:
        supp.write_bytes(big)
        supp_sha = big_sha

    with _sentries(monkeypatch, prep) as sen:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert sen["loads"] == 0
    assert sen["connects"] == 0
