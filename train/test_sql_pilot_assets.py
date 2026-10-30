"""TEST_ONLY deterministic local assets. No model or runtime results."""
import dataclasses
import hashlib
import importlib
import json
import sqlite3

import pytest


def api():
    try:
        return importlib.import_module("train.sql_pilot_assets")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_pilot_assets":
            raise
        pytest.fail("sql_pilot_assets implementation missing", pytrace=False)


def prepared(tmp_path):
    module = api()
    target = tmp_path / "assets" / "manifest.json"
    manifest = module.prepare_manifest(target, output_dir=target.parent, run_id="TEST_ONLY")
    return module, target, manifest


def test_twenty_independent_closed_snapshots(tmp_path):
    m, path, manifest = prepared(tmp_path)
    assert m.load_manifest(path) == manifest
    assert [a.partition for a in manifest.assets] == (
        ["development"] * 8 + ["qualification"] * 4 + ["heldout"] * 8
    )
    assert manifest.pair_first == ("B", "L", "L", "B", "B", "L", "L", "B")
    for key in ("case_id", "seed", "task_fingerprint", "db_sha256"):
        assert len({getattr(a, key) for a in manifest.assets}) == 20
    assert len({a.task.question for a in manifest.assets}) == 20
    assert len({a.task.db_id for a in manifest.assets}) == 20
    for asset in manifest.assets:
        with sqlite3.connect("file:" + asset.task.db_path + "?mode=ro", uri=True) as db:
            assert len(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()) == 1
            assert db.execute(asset.task.gold_sql).fetchone()[0] >= 0
        assert asset.ids.run_id == manifest.run_id
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.run_id = "other"


@pytest.mark.parametrize("change", ["version_bool", "extra", "missing", "digest", "duplicate", "utf8", "nan"])
def test_manifest_strict_codec(tmp_path, change):
    m, path, manifest = prepared(tmp_path)
    raw = path.read_bytes()
    value = json.loads(raw)
    if change == "extra":
        value["extra"] = 1
    elif change == "missing":
        del value["payload"]
    elif change == "digest":
        value["sha256"] = "0" * 64
    elif change == "version_bool":
        value["schema_version"] = True
    elif change == "duplicate":
        raw = raw.replace(b'"format":', b'"format":"duplicate","format":', 1)
    elif change == "utf8":
        raw = b"\xff"
    else:
        raw = b'{"x":NaN}'
    if change not in ("duplicate", "utf8", "nan"):
        raw = m.canonical_bytes(value) + b"\n"
    path.write_bytes(raw)
    with pytest.raises((ValueError, TypeError)):
        m.load_manifest(path)


@pytest.mark.parametrize("conflict", ["sidecar", "db_mutation", "hardlink", "symlink"])
def test_snapshot_conflicts_reject_without_deletion(tmp_path, conflict):
    m, path, manifest = prepared(tmp_path)
    from pathlib import Path
    db = Path(manifest.assets[0].task.db_path)
    if conflict == "sidecar":
        sidecar = db.with_name(db.name + "-wal")
        sidecar.write_bytes(b"retain")
    elif conflict == "db_mutation":
        db.chmod(0o600)
        with db.open("ab") as stream:
            stream.write(b"mutation")
    elif conflict == "hardlink":
        (tmp_path / "linked").hardlink_to(db)
    else:
        original = db.with_suffix(".original")
        db.rename(original)
        db.symlink_to(original)
    with pytest.raises((ValueError, TypeError)):
        m.validate_manifest(manifest)
    if conflict == "sidecar":
        assert sidecar.read_bytes() == b"retain"


def test_no_overwrite_and_frozen_bytes(tmp_path):
    m, path, manifest = prepared(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError, FileExistsError)):
        m.prepare_manifest(path, output_dir=path.parent, run_id="TEST_ONLY")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert m.manifest_sha256(manifest) == before


@pytest.mark.parametrize("change", ["pair", "duplicate", "partition", "scope", "fingerprint", "seed_bool", "traversal"])
def test_manifest_contract_mutations(tmp_path, change):
    m, _, manifest = prepared(tmp_path)
    assets = list(manifest.assets)
    with pytest.raises((ValueError, TypeError)):
        if change == "pair":
            altered = dataclasses.replace(manifest, pair_first=("B",) * 8)
        else:
            asset = assets[0]
            if change == "duplicate":
                assets[1] = asset
            elif change == "partition":
                assets[0] = dataclasses.replace(asset, partition="heldout")
            elif change == "scope":
                assets[0] = dataclasses.replace(asset, task=dataclasses.replace(asset.task, shape="wrong"))
            elif change == "fingerprint":
                assets[0] = dataclasses.replace(asset, task_fingerprint="0" * 64)
            elif change == "seed_bool":
                assets[0] = dataclasses.replace(asset, seed=True)
            else:
                assets[0] = dataclasses.replace(asset, task=dataclasses.replace(
                    asset.task, db_path=asset.task.db_path + "/../x"))
            altered = dataclasses.replace(manifest, assets=tuple(assets))
        m.validate_manifest(altered)
