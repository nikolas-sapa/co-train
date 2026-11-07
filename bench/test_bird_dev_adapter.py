"""Synthetic checks of the existing official-layout binding, with no SQL."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections import Counter
from pathlib import Path

import pytest


def _forbidden(*args, **kwargs):
    raise AssertionError("SQL/scorer/selection must not run at this boundary")


@pytest.fixture
def api(monkeypatch):
    loader = importlib.import_module("bench.loader")
    prepare = importlib.import_module("bench.prepare")
    suite = importlib.import_module("bench.suite")
    monkeypatch.setattr(prepare, "validate_golds", _forbidden)
    monkeypatch.setattr(importlib.import_module("sqlite3"), "connect", _forbidden)
    return loader, prepare, suite


def _rows():
    return [
        {
            "question_id": question_id,
            "db_id": "synthetic_db",
            "question": f"PRIVATE_QUESTION_{question_id}",
            "evidence": f"  PRIVATE_EVIDENCE_{question_id}  ",
            "SQL": f"SELECT {question_id} /* PRIVATE_GOLD_{question_id} */",
            "difficulty": tier,
        }
        for question_id, tier in zip(
            (27, 19, 5), ("simple", "moderate", "challenging"))
    ]


def _corpus(tmp_path, rows=None):
    rows = _rows() if rows is None else rows
    root = tmp_path / "corpus"
    root.mkdir()
    for db_id in sorted({row["db_id"] for row in rows}):
        directory = root / "dev_databases" / db_id
        directory.mkdir(parents=True)
        (directory / f"{db_id}.sqlite").write_bytes(b"synthetic hash-only bytes\n")
    (root / "dev.json").write_text(json.dumps(rows), encoding="utf-8")
    return root


def _freeze(prepare, root, tmp_path):
    output = tmp_path / "draw.json"
    digest = prepare.freeze_draw(
        root, output, seed=23,
        per_tier={"simple": 1, "moderate": 1, "challenging": 1},
        fixture=True,
    )
    return output, digest


def _refuse_freeze(prepare, root, tmp_path):
    with pytest.raises(prepare.PreparationError):
        _freeze(prepare, root, tmp_path)
    assert not (tmp_path / "draw.json").exists()


def _rewrite_draw(prepare, path, doc):
    raw = prepare._canonical_bytes(doc)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _refuse_validation(prepare, root, draw, digest, tmp_path):
    output = tmp_path / "supplement.json"
    with pytest.raises(prepare.PreparationError):
        prepare.validate_draw(
            root, draw, output, expected_draw_sha256=digest)
    assert not output.exists()


def test_official_layout_scale(tmp_path, api):
    loader, prepare, _ = api
    tiers = ["simple"] * 925 + ["moderate"] * 464 + ["challenging"] * 145
    rows = [
        {
            "question_id": 2000 - index,
            "db_id": f"synthetic_{index % 11:02d}",
            "question": f"synthetic question {index}",
            "evidence": f"  synthetic evidence {index}  ",
            "SQL": f"SELECT {index}",
            "difficulty": tier,
        }
        for index, tier in enumerate(tiers)
    ]
    root = _corpus(tmp_path, rows)
    raw = (root / "dev.json").read_bytes()
    # The documented one-level extraction layout must bind identically.
    tasks = loader.load_bird(tmp_path)
    assert len(tasks) == len({task.name for task in tasks}) == 1534
    assert len({task.db_id for task in tasks}) == 11
    assert Counter(task.tier for task in tasks) == {
        "simple": 925, "moderate": 464, "challenging": 145,
    }
    for task, row in zip(tasks, rows):
        assert task.name == f"bird-{row['question_id']:04d}"
        assert task.question == row["question"]
        assert task.gold_sql == row["SQL"]
        assert task.evidence == row["evidence"].strip()
        assert task.db_id == row["db_id"]
        assert task.tier == row["difficulty"]
        assert task.source == "bird"
        assert task.tier_source == "annotated"
        assert Path(task.db_path).is_absolute()
    digest, candidates = prepare._corpus(root)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert candidates == tasks
    assert (root / "dev.json").read_bytes() == raw


def test_freeze_reuses_existing_selector(tmp_path, api, monkeypatch):
    loader, prepare, suite = api
    root = _corpus(tmp_path)
    expected = suite.select(
        loader.load_bird(root),
        per_tier={"simple": 1, "moderate": 1, "challenging": 1},
        seed=23, granularity="fine",
    )
    original = prepare.select
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(prepare, "select", counted)
    draw, digest = _freeze(prepare, root, tmp_path)
    doc = json.loads(draw.read_bytes())
    assert calls == [1]
    assert [entry["id"] for entry in doc["planned"]] == [
        task.name for task in expected]
    assert len(doc["planned"]) == 3
    assert doc["identity"]["manifest_sha256"] == hashlib.sha256(
        (root / "dev.json").read_bytes()).hexdigest()
    assert digest == hashlib.sha256(draw.read_bytes()).hexdigest()


def test_duplicate_ids_refuse(tmp_path, api):
    _, prepare, _ = api
    rows = _rows()
    rows[1]["question_id"] = rows[0]["question_id"]
    _refuse_freeze(prepare, _corpus(tmp_path, rows), tmp_path)


def test_bool_id_refuses(tmp_path, api):
    _, prepare, _ = api
    rows = _rows()
    rows[0]["question_id"] = True
    _refuse_freeze(prepare, _corpus(tmp_path, rows), tmp_path)


def test_false_id_refuses(tmp_path, api):
    _, prepare, _ = api
    rows = _rows()
    rows[0]["question_id"] = False
    root = _corpus(tmp_path, rows)
    with pytest.raises(prepare.PreparationError) as caught:
        _freeze(prepare, root, tmp_path)
    assert str(caught.value) == "corpus records rejected"
    assert not (tmp_path / "draw.json").exists()


@pytest.mark.parametrize("question_id", [False, True])
@pytest.mark.parametrize("source,db_dir,sql_key", [
    ("bird", "dev_databases", "SQL"),
    ("spider", "database", "query"),
])
def test_loader_bool_ids_refuse(tmp_path, api, question_id, source, db_dir, sql_key):
    loader, _, _ = api
    rows = _rows()
    rows[0]["question_id"] = question_id
    if sql_key != "SQL":
        for row in rows:
            row[sql_key] = row.pop("SQL")
    with pytest.raises(ValueError) as caught:
        loader._build(rows, tmp_path, db_dir, sql_key, source, source, False)
    assert str(caught.value) == "question_id must not be a boolean"


@pytest.mark.parametrize("source,db_dir,sql_key", [
    ("bird", "dev_databases", "SQL"),
    ("spider", "database", "query"),
])
def test_loader_id_compatibility(tmp_path, api, source, db_dir, sql_key):
    loader, _, _ = api
    rows = _rows()
    rows[0]["question_id"] = 0
    rows[1]["question_id"] = "19"
    rows[2].pop("question_id")
    if sql_key != "SQL":
        for row in rows:
            row[sql_key] = row.pop("SQL")
    tasks = loader._build(rows, tmp_path, db_dir, sql_key, source, source, False)
    assert len(tasks) == 3
    assert [task.name for task in tasks] == [
        f"{source}-0000", f"{source}-0019", f"{source}-0002",
    ]
    for task, row in zip(tasks, rows):
        assert task.question == row["question"]
        assert task.evidence == row["evidence"].strip()
        assert task.gold_sql == row[sql_key]
        assert task.db_id == row["db_id"]
        assert task.db_path == str((
            tmp_path / db_dir / row["db_id"] / f"{row['db_id']}.sqlite").resolve())
        assert task.tier == row["difficulty"]
        assert task.tier_source == "annotated"
        assert task.shape == loader.shape(row[sql_key], "fine")
        assert task.coarse_shape == loader.shape(row[sql_key], "coarse")
        assert task.source == source


def test_unknown_database_refuses(tmp_path, api):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    rows = _rows()
    rows[0]["db_id"] = "unknown_db"
    (root / "dev.json").write_text(json.dumps(rows), encoding="utf-8")
    _refuse_freeze(prepare, root, tmp_path)


def test_unknown_tier_refuses(tmp_path, api):
    _, prepare, _ = api
    rows = _rows()
    rows[0]["difficulty"] = "unknown_tier"
    _refuse_freeze(prepare, _corpus(tmp_path, rows), tmp_path)


def test_missing_database_pin_refuses(tmp_path, api):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    draw, _ = _freeze(prepare, root, tmp_path)
    doc = json.loads(draw.read_bytes())
    assert len(doc["identity"]["databases"]) == 1
    doc["identity"]["databases"] = []
    digest = _rewrite_draw(prepare, draw, doc)
    _refuse_validation(prepare, root, draw, digest, tmp_path)


def test_wrong_source_sha_refuses(tmp_path, api):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    draw, _ = _freeze(prepare, root, tmp_path)
    doc = json.loads(draw.read_bytes())
    sources = doc["identity"]["source_sha256"]
    assert sources["bench/loader.py"] != "0" * 64
    sources["bench/loader.py"] = "0" * 64
    digest = _rewrite_draw(prepare, draw, doc)
    _refuse_validation(prepare, root, draw, digest, tmp_path)


def test_wrong_manifest_sha_refuses(tmp_path, api):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    draw, _ = _freeze(prepare, root, tmp_path)
    doc = json.loads(draw.read_bytes())
    assert doc["identity"]["manifest_sha256"] != "0" * 64
    doc["identity"]["manifest_sha256"] = "0" * 64
    digest = _rewrite_draw(prepare, draw, doc)
    _refuse_validation(prepare, root, draw, digest, tmp_path)


def test_database_symlink_escape_refuses(tmp_path, api):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    db = root / "dev_databases" / "synthetic_db" / "synthetic_db.sqlite"
    outside = tmp_path / "outside.sqlite"
    db.rename(outside)
    db.symlink_to(outside)
    _refuse_freeze(prepare, root, tmp_path)


def test_manifest_mutation_during_load_refuses(tmp_path, api, monkeypatch):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    original = prepare.load_bird
    calls = []

    def mutate(base):
        tasks = original(base)
        calls.append(1)
        manifest = Path(base) / "dev.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        return tasks

    monkeypatch.setattr(prepare, "load_bird", mutate)
    _refuse_freeze(prepare, root, tmp_path)
    assert calls == [1]


def test_database_mutation_between_snapshots_refuses(tmp_path, api, monkeypatch):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    original = prepare._hash_db
    calls = []

    def mutate(path):
        result = original(path)
        calls.append(1)
        if len(calls) == 1:
            path.write_bytes(path.read_bytes() + b"mutation\n")
        return result

    monkeypatch.setattr(prepare, "_hash_db", mutate)
    _refuse_freeze(prepare, root, tmp_path)
    assert len(calls) == 2


def test_draw_keeps_gold_host_private(tmp_path, api):
    loader, prepare, _ = api
    root = _corpus(tmp_path)
    draw, _ = _freeze(prepare, root, tmp_path)
    raw = draw.read_bytes()
    for sentinel in (
        b"PRIVATE_QUESTION", b"PRIVATE_EVIDENCE", b"PRIVATE_GOLD",
        str(root).encode(), b"SELECT ",
    ):
        assert sentinel not in raw
    doc = json.loads(raw)
    assert set(doc) == {
        "kind", "version", "stage", "measurement", "fixture", "model_calls",
        "status", "usable", "settings", "actual_per_tier",
        "shortfall_per_tier", "planned", "identity",
    }
    assert all(set(entry) == {"id", "tier", "db_id", "task_sha256"}
               for entry in doc["planned"])
    assert all(set(entry) == {"db_id", "sha256", "size_bytes"}
               for entry in doc["identity"]["databases"])
    assert doc["measurement"] is False
    assert doc["model_calls"] == 0
    assert doc["usable"] is False
    tasks = loader.load_bird(root)
    assert [task.gold_sql for task in tasks] == [row["SQL"] for row in _rows()]


def test_frozen_resolution_preserves_ordered_denominator(tmp_path, api, monkeypatch):
    loader, prepare, _ = api
    rows = _rows()
    rows[2]["SQL"] = "SELECT nonexistent_column FROM nonexistent_table"
    root = _corpus(tmp_path, rows)
    draw, _ = _freeze(prepare, root, tmp_path)
    planned = json.loads(draw.read_bytes())["planned"]
    tasks = loader.load_bird(root)
    monkeypatch.setattr(prepare, "select", _forbidden)
    resolved = prepare._resolve_planned(planned, list(reversed(tasks)))
    assert len(resolved) == len(planned) == 3
    assert [task.name for task in resolved] == [entry["id"] for entry in planned]
    assert {task.name for task in resolved} == {task.name for task in tasks}
    assert sum(task.gold_sql == rows[2]["SQL"] for task in resolved) == 1


def test_wrong_retained_draw_digest_refuses_before_corpus(
        tmp_path, api, monkeypatch):
    _, prepare, _ = api
    root = _corpus(tmp_path)
    draw, digest = _freeze(prepare, root, tmp_path)
    assert digest != "0" * 64
    monkeypatch.setattr(prepare, "_corpus", _forbidden)
    _refuse_validation(prepare, root, draw, "0" * 64, tmp_path)
