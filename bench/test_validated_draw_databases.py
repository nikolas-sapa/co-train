"""Host projection of retained DB identities, not new provenance authority."""
import dataclasses
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from bench import fixture, prepare
from bench.test_prepare import _freeze, _sentries, _write_corpus
from bench.test_validated_draw import _load


def _api():
    assert hasattr(prepare, "DrawDatabase"), "admitted database record API missing"
    return prepare


def _artifacts(tmp_path, *, excluded_only=False):
    records = fixture.records()
    records[0]["SQL"] = "SELECT * FROM absent_projection_fixture_table"
    if excluded_only:
        records[0]["db_id"] = "excluded-only"
    root = _write_corpus(tmp_path / "corpus", records)
    if excluded_only:
        fixture.build_db(root / "dev_databases/excluded-only/excluded-only.sqlite")
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    draw_sha = _freeze(prepare, root, draw)
    supp_sha = prepare.validate_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha)
    return root, draw, draw_sha, supplement, supp_sha


def _assert_projection(result, expected):
    assert type(result.databases) is tuple
    assert len(result.databases) == len(expected)
    for actual, admitted in zip(result.databases, expected, strict=True):
        assert type(actual) is prepare.DrawDatabase
        assert actual.db_id == admitted["db_id"]
        assert actual.sha256 == admitted["sha256"], "PROJECTED_DB_DIGEST_NOT_ADMITTED"
        assert actual.size_bytes == admitted["size_bytes"]
        assert set(dataclasses.asdict(actual)) == {"db_id", "sha256", "size_bytes"}


@pytest.mark.parametrize("excluded_only", (False, True), ids=("shared", "excluded-only"))
def test_projection_preserves_admitted_digest_and_original_denominator(
        tmp_path, monkeypatch, excluded_only):
    prep = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(
        tmp_path, excluded_only=excluded_only)
    draw_bytes, supp_bytes = draw.read_bytes(), supp.read_bytes()
    document = json.loads(draw_bytes)
    expected = document["identity"]["databases"]
    hashed, publications = [], []
    original_hash = prep._hash_db

    def observed_hash(path):
        hashed.append(Path(path).resolve())
        return original_hash(path)

    def forbidden_publication(*args, **kwargs):
        publications.append(1)
        raise AssertionError("consumer attempted publication")

    monkeypatch.setattr(prep, "_hash_db", observed_hash)
    for name in ("link", "rename", "replace"):
        monkeypatch.setattr(os, name, forbidden_publication)
    with _sentries(monkeypatch, prep) as sentries:
        result = _load(prep, root, draw, supp, draw_sha, supp_sha)
    _assert_projection(result, expected)
    assert len(result.planned) == 8 and len(result.eligible) == 7
    assert len(result.exclusions) == 1
    assert [task.name for task in result.planned] == [
        row["id"] for row in document["planned"]]
    assert result.draw_sha256 == draw_sha and result.supplement_sha256 == supp_sha
    assert (result.timeout_s, result.max_rows, result.comparison) == (
        document["settings"]["timeout_s"], document["settings"]["max_rows"],
        document["settings"]["comparison"])
    assert sentries["loads"] == 2
    assert all(sentries[name] == 0 for name in ("connects", "selects", "golds", "ex"))
    assert not publications
    expected_paths = {
        (root / "dev_databases" / row["db_id"] / (row["db_id"] + ".sqlite")).resolve()
        for row in expected}
    assert Counter(hashed) == Counter({path: 2 for path in expected_paths}), (
        "database projection added hashing beyond two fresh identity passes")
    for task in result.planned:
        assert sum(record.db_id == task.db_id for record in result.databases) == 1
    if excluded_only:
        assert len(result.databases) == 2
        assert "excluded-only" not in {task.db_id for task in result.eligible}
        assert "excluded-only" in {record.db_id for record in result.databases}
    else:
        assert len(result.databases) == 1  # Shared database, not eight duplicates.
    assert draw.read_bytes() == draw_bytes and supp.read_bytes() == supp_bytes


@pytest.mark.parametrize("field", ("db_id", "sha256", "size_bytes"))
def test_projected_database_records_and_container_are_frozen(
        tmp_path, monkeypatch, field):
    prep = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    with _sentries(monkeypatch, prep):
        result = _load(prep, root, draw, supp, draw_sha, supp_sha)
    record, = result.databases
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(record, field, getattr(record, field))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.databases = ()


def test_projection_refuses_current_db_drift_without_adopting_new_digest(
        tmp_path, monkeypatch):
    prep = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    (root / "dev_databases" / fixture.DB_ID / (fixture.DB_ID + ".sqlite")).write_bytes(
        b"changed synthetic database, not adopted as expected identity")
    with _sentries(monkeypatch, prep) as sentries:
        with pytest.raises(prep.PreparationError):
            _load(prep, root, draw, supp, draw_sha, supp_sha)
    assert all(sentries[name] == 0 for name in ("connects", "selects", "golds", "ex"))


def test_repeated_projections_keep_independent_values_and_input_bytes(
        tmp_path, monkeypatch):
    prep = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    original = draw.read_bytes(), supp.read_bytes()
    expected = json.loads(original[0])["identity"]["databases"]
    with _sentries(monkeypatch, prep):
        first = _load(prep, root, draw, supp, draw_sha, supp_sha)
        second = _load(prep, root, draw, supp, draw_sha, supp_sha)
    _assert_projection(first, expected)
    _assert_projection(second, expected)
    assert first.databases == second.databases
    assert first.databases[0] is not second.databases[0]
    expected[0]["sha256"] = "0" * 64  # Local dict, not the retained artifact.
    assert first.databases[0].sha256 != expected[0]["sha256"]
    assert (draw.read_bytes(), supp.read_bytes()) == original
