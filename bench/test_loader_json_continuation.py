"""Continuation regression for `bench/loader.py`'s JSON decoding contract.

Two guarantees, one file:

1. Duplicate DECODED keys in a manifest object are refused. `json.loads` on a raw
   object silently keeps the last value for a repeated key, so a manifest line like
   `{"question_id": 7, "question_id": 8, ...}` -- or the same pair with one key spelled
   `"\\u0071uestion_id"` -- decodes to one key and silently changes task identity,
   question or gold. The loader's contract is to reject ambiguity, not pick a value.
2. Unique-key manifests keep loading verbatim: count, names, question/gold bytes,
   evidence stripping, tier provenance and absolute db paths are unchanged.

Raw JSON text is constructed by hand where duplicates are needed -- `json.dumps` of a
dict cannot emit a repeated key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from bench import fixture  # noqa: E402
from bench.loader import CorpusMissing, load_bird, load_spider  # noqa: E402
from bench.task import TIERS  # noqa: E402

DB_ID = fixture.DB_ID  # "campus" -- fixture schema builds this database.

# (label, loader, manifest sql key, db dir, source, name prefix, dupable fields)
LAYOUTS = [
    ("bird", load_bird, "SQL", "dev_databases", "bird", "bird",
     ["SQL", "question", "db_id", "question_id"]),
    ("spider", load_spider, "query", "database", "spider", "spider",
     ["query", "question", "db_id", "question_id"]),
]

# Conflicting-but-plausible values per field so a baseline pass cannot be attributed
# to an earlier structural failure and a fixed run's error names the decoded key.
DUP_VALUES = {
    "SQL": "\"SELECT name FROM county\"",
    "query": "\"SELECT name FROM county\"",
    "question": "\"conflicting duplicate question\"",
    "db_id": "\"otherdb\"",
    "question_id": "999",
}


def _corpus_root(tmp_path: Path, db_dir: str) -> Path:
    """A loadable layout: `dev.json` beside `<db_dir>/campus/campus.sqlite`."""
    root = tmp_path / "corpus"
    root.mkdir()
    fixture.build_db(root / db_dir / DB_ID / f"{DB_ID}.sqlite")
    return root


def _esc(key: str) -> str:
    """Same decoded key, spelled with the first character as a \\uXXXX escape."""
    return "\\u%04x%s" % (ord(key[0]), key[1:])


def _record_json(sql_key: str, qid: int, question: str, gold: str,
                 extra_pairs: list[str] | None = None,
                 evidence_json: str | None = "\"evidence text\"",
                 difficulty: bool = True) -> str:
    """One record as RAW JSON text so key order and duplicates are literal."""
    pairs = [
        f'"question_id": {qid}',
        f'"db_id": "{DB_ID}"',
        f'"question": {json.dumps(question)}',
        f'"{sql_key}": {json.dumps(gold)}',
    ]
    if evidence_json is not None:
        pairs.append(f'"evidence": {evidence_json}')
    if difficulty:
        pairs.append('"difficulty": "simple"')
    pairs.append('"meta": {"nested": {"unknown": [1, 2]}}')
    pairs += extra_pairs or []
    return "{" + ", ".join(pairs) + "}"


# --- 1. duplicate decoded keys refuse (16 cases) ---------------------------------

@pytest.mark.parametrize(
    "label,loader,sql_key,db_dir,source,prefix,fields", LAYOUTS,
    ids=[l[0] for l in LAYOUTS])
@pytest.mark.parametrize("field_i", range(4), ids=["f0", "f1", "f2", "f3"])
@pytest.mark.parametrize("escaped", [False, True], ids=["literal", "escaped"])
def test_duplicate_decoded_corpus_keys_refuse(
        tmp_path, label, loader, sql_key, db_dir, source, prefix, fields,
        field_i, escaped):
    field = fields[field_i]
    spelling = _esc(field) if escaped else field
    base_values = {
        "question_id": 7,
        "db_id": f'"{DB_ID}"',
        "question": "\"base question\"",
        "SQL": "\"SELECT name FROM school\"",
        "query": "\"SELECT name FROM school\"",
        "evidence": "\"e\"",
        "difficulty": "\"simple\"",
    }
    # First occurrence keeps the base value; the duplicate repeats the DECODED key
    # with a conflicting value, placed after all base pairs.
    pairs = [f'"{k}": {v}' for k, v in base_values.items()]
    pairs.append(f'"{spelling}": {DUP_VALUES[field]}')
    root = _corpus_root(tmp_path, db_dir)
    if field == "db_id":
        other_id = json.loads(DUP_VALUES[field])
        fixture.build_db(root / db_dir / other_id / f"{other_id}.sqlite")
    manifest = "[{" + ", ".join(pairs) + "}]"
    records = json.loads(manifest)
    assert len(records) == 1
    assert records[0][field] == json.loads(DUP_VALUES[field])
    # Admit the last-value-wins control before testing ambiguity, not missing DBs.
    (root / "dev.json").write_text(json.dumps(records))
    _check_tasks(loader(root), records, sql_key, source, prefix, annotated=True)
    (root / "dev.json").write_text(manifest)

    returned_tasks = []
    with pytest.raises(ValueError) as exc:
        returned_tasks.extend(loader(root))
    assert returned_tasks == []
    msg = str(exc.value)
    assert "duplicate" in msg
    assert field in msg  # decoded key named, whether spelled literally or escaped


# --- 2. unique manifests preserve tasks verbatim (4 cases) ------------------------

def _check_tasks(tasks, records, sql_key, source, prefix, annotated):
    assert len(tasks) == len(records)
    for i, (t, r) in enumerate(zip(tasks, records)):
        qid = r.get("question_id", i)
        assert t.name == f"{prefix}-{int(qid):04d}"
        assert t.question == r["question"]
        assert t.gold_sql == r[sql_key]
        assert t.db_id == r["db_id"]
        assert t.evidence == (r.get("evidence") or "").strip()
        assert t.source == source
        if annotated:
            assert t.tier == r["difficulty"]
            assert t.tier_source == "annotated"
        else:
            assert t.tier in TIERS
            assert t.tier_source == "derived"
        assert Path(t.db_path).is_absolute()
        assert Path(t.db_path).is_file()


@pytest.mark.parametrize(
    "label,loader,sql_key,db_dir,source,prefix,fields", LAYOUTS,
    ids=[l[0] for l in LAYOUTS])
@pytest.mark.parametrize("kind", ["fixture", "synthetic"])
def test_unique_fixture_manifest_preserves_tasks(
        tmp_path, label, loader, sql_key, db_dir, source, prefix, fields, kind):
    annotated = source == "bird"
    if kind == "fixture":
        dest = tmp_path / "fresh"
        root = (fixture.materialize(dest) if source == "bird"
                else fixture.materialize_spider(dest))
        records = json.loads((root / "dev.json").read_text())
    else:
        # Broad unique JSON, no schema: whitespace/newlines inside question and gold,
        # escaped non-ASCII, whitespace-only and absent evidence, unknown nested
        # metadata, field names repeated across DISTINCT objects only.
        root = _corpus_root(tmp_path, db_dir)
        records_text = [
            _record_json(sql_key, 10, "  multi\nline question \u00e9tat  ",
                         "SELECT name\n  FROM school\n WHERE charter = 1",
                         evidence_json='"   "', difficulty=annotated),
            _record_json(sql_key, 20, "second question",
                         "SELECT COUNT(*) FROM county", evidence_json=None,
                         difficulty=annotated),
        ]
        (root / "dev.json").write_text("[" + ", ".join(records_text) + "]")
        records = json.loads("[" + ", ".join(records_text) + "]")
    tasks = loader(root)
    _check_tasks(tasks, records, sql_key, source, prefix, annotated)


# --- 3. finite behavior (8 cases) -------------------------------------------------

def _layout(loader, sql_key, db_dir, tmp_path, records_json, make_db=True):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "dev.json").write_text(records_json)
    (root / db_dir).mkdir()
    if make_db:
        fixture.build_db(root / db_dir / DB_ID / f"{DB_ID}.sqlite")
    return root


@pytest.mark.parametrize(
    "label,loader,sql_key,db_dir,source,prefix,fields", LAYOUTS,
    ids=[l[0] for l in LAYOUTS])
@pytest.mark.parametrize("case", ["absent", "missing_db", "empty", "dup_names"])
def test_finite_behaviors(tmp_path, label, loader, sql_key, db_dir, source,
                          prefix, fields, case):
    if case == "absent":
        with pytest.raises(CorpusMissing):
            loader(tmp_path / "does-not-exist")
    elif case == "missing_db":
        rec = _record_json(sql_key, 1, "q", "SELECT 1")
        root = _layout(loader, sql_key, db_dir, tmp_path,
                       "[" + rec + "]", make_db=False)
        with pytest.raises(CorpusMissing):
            loader(root)  # default require_db=True
    elif case == "empty":
        root = _layout(loader, sql_key, db_dir, tmp_path, "[]", make_db=False)
        with pytest.raises(CorpusMissing):
            loader(root, require_db=False)
    else:  # dup_names: distinct records sharing question_id collide on task name
        a = _record_json(sql_key, 7, "question a", "SELECT name FROM school")
        b = _record_json(sql_key, 7, "question b",
                         "SELECT name FROM county", evidence_json=None)
        root = _layout(loader, sql_key, db_dir, tmp_path,
                       "[" + a + ", " + b + "]")
        with pytest.raises(ValueError, match="duplicate"):
            loader(root, require_db=False)
