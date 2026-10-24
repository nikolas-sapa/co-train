"""Real filesystem byte-admission tests, never real model/runtime proof."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def api():
    try:
        return importlib.import_module("train.native_model")
    except ModuleNotFoundError as error:
        if error.name == "train.native_model":
            pytest.fail("missing native local-model verifier, expected failure-first RED")
        raise


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def fixture(tmp_path):
    directory = tmp_path / "bundle"
    directory.mkdir()
    files = []
    for name, raw in (("config.json", b"FIXTURE CONFIG"), ("model.safetensors", b"NOT MODEL WEIGHTS")):
        (directory / name).write_bytes(raw)
        files.append({"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    inventory = {"model_id": "fixture/not-a-model", "revision": "a" * 40, "files": files}
    return directory, inventory


def admitted(module, directory, inventory):
    raw = encoded(inventory)
    parsed = module._parse_inventory(raw, hashlib.sha256(raw).hexdigest())
    return module._verify_directory(directory, parsed, hashlib.sha256(raw).hexdigest())


def test_valid_private_files(tmp_path):
    module = api()
    directory, inventory = fixture(tmp_path)
    result = admitted(module, directory, inventory)
    assert result.path == str(directory)
    assert result.model_id == "fixture/not-a-model"
    assert result.revision == "a" * 40
    assert result.files_verified == 2
    assert not hasattr(result, "launch_authorized")
    assert not hasattr(result, "runtime_verified")


@pytest.mark.parametrize("fault", [
    "same_size", "missing", "extra", "root_symlink", "ancestor_symlink",
    "member_symlink", "hardlink", "fifo", "subdirectory",
])
def test_unsafe_directory_refuses(tmp_path, fault):
    module = api()
    directory, inventory = fixture(tmp_path)
    path = directory / "config.json"
    if fault == "same_size":
        raw = path.read_bytes()
        path.write_bytes(b"X" + raw[1:])
    elif fault == "missing":
        path.unlink()
    elif fault == "extra":
        (directory / "unexpected.txt").write_text("extra")
    elif fault in {"root_symlink", "ancestor_symlink"}:
        alias = tmp_path / "alias"
        alias.symlink_to(directory if fault == "root_symlink" else tmp_path, target_is_directory=True)
        directory = alias if fault == "root_symlink" else alias / "bundle"
    elif fault == "member_symlink":
        path.unlink()
        path.symlink_to(directory / "model.safetensors")
    elif fault == "hardlink":
        os.link(path, tmp_path / "second-link")
    elif fault == "fifo":
        path.unlink()
        os.mkfifo(path)
    else:
        (directory / "nested").mkdir()
    with pytest.raises(module.LocalModelError):
        admitted(module, directory, inventory)


@pytest.mark.parametrize("fault", [
    "traversal", "absolute", "duplicate", "duplicate_key", "bool_size",
    "negative_size", "bad_hash", "untrusted_digest", "too_large",
])
def test_inventory_refuses(tmp_path, fault):
    module = api()
    _, inventory = fixture(tmp_path)
    if fault == "traversal":
        inventory["files"][0]["path"] = "../config.json"
    elif fault == "absolute":
        inventory["files"][0]["path"] = "/config.json"
    elif fault == "duplicate":
        inventory["files"].append(dict(inventory["files"][0]))
    elif fault in {"bool_size", "negative_size"}:
        inventory["files"][0]["size"] = True if fault == "bool_size" else -1
    elif fault == "bad_hash":
        inventory["files"][0]["sha256"] = "z" * 64
    raw = encoded(inventory)
    if fault == "duplicate_key":
        raw = raw.replace(b'"model_id":', b'"model_id":"fixture/x","model_id":')
    elif fault == "too_large":
        raw = b" " * (64 * 1024 + 1)
    digest = "0" * 64 if fault == "untrusted_digest" else hashlib.sha256(raw).hexdigest()
    with pytest.raises(module.LocalModelError):
        module._parse_inventory(raw, digest)


def test_public_inventory_is_not_caller_controlled(tmp_path):
    module = api()
    directory, inventory = fixture(tmp_path)
    (directory / "inventory.json").write_bytes(encoded(inventory))
    assert list(inspect.signature(module.verify_local_model).parameters) == ["model_dir", "model_revision"]
    with pytest.raises(module.LocalModelError, match="revision"):
        module.verify_local_model(directory, model_revision=inventory["revision"])
    with pytest.raises(module.LocalModelError, match="inventory|member|file"):
        module.verify_local_model(directory, model_revision=module.MODEL_REVISION)


def test_changed_during_read_refuses(tmp_path, monkeypatch):
    module = api()
    directory, inventory = fixture(tmp_path)
    original = module._stream_sha256
    changed = False

    def changing(stream, size):
        nonlocal changed
        result = original(stream, size)
        if not changed:
            path = directory / "config.json"
            raw = path.read_bytes()
            path.write_bytes(b"Z" + raw[1:])
            changed = True
        return result

    monkeypatch.setattr(module, "_stream_sha256", changing)
    with pytest.raises(module.LocalModelError, match="changed"):
        admitted(module, directory, inventory)


def test_worktree_module_origins():
    module = api()
    expected = Path(__file__).resolve().parent
    assert Path.cwd().resolve() == expected.parent
    assert Path(module.__file__).resolve().parent == expected
    from train import grpo_ptc, guards, native_runtime, native_training
    for imported in (grpo_ptc, guards, native_runtime, native_training):
        assert Path(imported.__file__).resolve().parent == expected


def test_source_inventory_identity():
    module = api()
    raw = Path(module.__file__).with_name("native_model_inventory.json").read_bytes()
    record = module._parse_inventory(raw, module.INVENTORY_SHA256)
    assert record.model_id == "unsloth/Qwen3-0.6B"
    assert record.revision == module.MODEL_REVISION
    assert len(record.files) == 10
    weights = next(row for row in record.files if row.path == "model.safetensors")
    assert weights.size == 1192135096
    assert weights.sha256 == "e2c6471fedf92223e6bd28ac296e720f1ab91cecb531bc91c7cfe03b52daff98"


def test_corruption_refuses_under_optimized_python(tmp_path):
    module = api()
    directory, inventory = fixture(tmp_path)
    path = directory / "config.json"
    path.write_bytes(b"X" * path.stat().st_size)
    raw = encoded(inventory)
    program = """
import sys
from train import native_model
raw = bytes.fromhex(sys.argv[2])
inventory = native_model._parse_inventory(raw, sys.argv[3])
native_model._verify_directory(sys.argv[1], inventory, sys.argv[3])
"""
    result = subprocess.run(
        [sys.executable, "-B", "-O", "-c", program, str(directory), raw.hex(),
         hashlib.sha256(raw).hexdigest()],
        cwd=Path(module.__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode != 0
    assert "LocalModelError: local model content digest mismatch" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


@pytest.mark.parametrize("suffix", ["-bf16", "-bnb-4bit", "-unsloth-bnb-4bit"])
def test_precision_remapping_suffix_refuses(tmp_path, suffix):
    module = api()
    directory, inventory = fixture(tmp_path)
    renamed = directory.with_name("source" + suffix)
    directory.rename(renamed)
    with pytest.raises(module.LocalModelError, match="suffix"):
        admitted(module, renamed, inventory)
