"""Cold/unit contracts only. Parent explicitly invokes the real CPU probe."""

from __future__ import annotations

import ast
import builtins
import importlib
import importlib.util
import inspect
from pathlib import Path

import pytest


MODULE = "train.native_torch_conformance"


def _implementation():
    assert importlib.util.find_spec(MODULE) is not None, (
        "missing real CPU reader probe, intended baseline RED"
    )
    return importlib.import_module(MODULE)


def test_01_cold_import_has_no_framework_or_workspace_effects(monkeypatch, tmp_path):
    source = Path(__file__).with_name("native_torch_conformance.py")
    assert source.is_file(), "missing real CPU reader probe, intended baseline RED"
    spec = importlib.util.spec_from_file_location("_cold_torch_conformance", source)
    assert spec is not None and spec.loader is not None
    api = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "torch", "numpy", "safetensors", "modal", "transformers",
        }, f"framework import during cold import: {name}"
        assert name != "train.native_qualification"
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("cold import wrote workspace")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    spec.loader.exec_module(api)
    assert list(tmp_path.iterdir()) == []
    assert callable(api.run_cpu_conformance)


def test_02_requires_exact_opt_in_before_runtime(monkeypatch, tmp_path):
    api = _implementation()

    def forbidden():
        raise AssertionError("runtime looked up before opt-in")

    monkeypatch.setattr(api, "_runtime", forbidden)
    for index, value in enumerate((False, None, 1, "yes")):
        destination = tmp_path / f"probe-{index}"
        with pytest.raises(ValueError, match="explicit opt_in=True required"):
            api.run_cpu_conformance(destination, opt_in=value)
        assert not destination.exists()


def test_03_destination_admission_precedes_runtime(monkeypatch, tmp_path):
    api = _implementation()

    def forbidden():
        raise AssertionError("runtime looked up before path admission")

    monkeypatch.setattr(api, "_runtime", forbidden)
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("retained")
    link = tmp_path / "link"
    link.symlink_to(existing, target_is_directory=True)
    for destination in (
        Path("relative"), tmp_path / ".." / "traversal", existing, link / "fresh",
    ):
        with pytest.raises(ValueError):
            api.run_cpu_conformance(destination, opt_in=True)
    assert marker.read_text() == "retained"
    assert sorted(path.name for path in existing.iterdir()) == ["keep.txt"]


def test_04_missing_framework_is_failure_not_skip(monkeypatch, tmp_path):
    api = _implementation()
    original_import = importlib.import_module
    attempts = []

    def missing(name, *args, **kwargs):
        if name == "torch":
            attempts.append(name)
            raise ModuleNotFoundError("synthetic unavailable Torch")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", missing)
    destination = tmp_path / "missing-runtime"
    with pytest.raises(RuntimeError, match="requires installed torch, numpy and safetensors"):
        api.run_cpu_conformance(destination, opt_in=True)
    assert attempts == ["torch"]
    assert not destination.exists()


def test_05_serialization_buffer_enforces_fixed_cap():
    api = _implementation()
    assert api.MAX_FILE_BYTES == 65536
    with api._LimitedBuffer() as stream:
        assert stream.write(b"x" * 65536) == 65536
        with pytest.raises(ValueError, match="serialized file exceeds fixed cap"):
            stream.write(b"x")
        assert len(stream.getvalue()) == 65536


def test_06_file_admission_enforces_each_fixed_cap(tmp_path):
    api = _implementation()
    assert (api.MAX_TOTAL_BYTES, api.MAX_FILES) == (524288, 16)
    sizes = {}
    target = tmp_path / "one"
    api._write_bytes(target, b"x" * 65536, sizes)
    with pytest.raises(FileExistsError):
        api._write_bytes(target, b"replacement", sizes)
    assert target.read_bytes() == b"x" * 65536
    for index in range(1, 8):
        api._write_bytes(tmp_path / f"part-{index}", b"x" * 65536, sizes)
    assert sum(sizes.values()) == 524288
    with pytest.raises(ValueError, match="aggregate file cap"):
        api._write_bytes(tmp_path / "overflow", b"x", sizes)
    with pytest.raises(ValueError, match="individual file cap"):
        api._write_bytes(tmp_path / "oversize", b"x" * 65537, {})
    small_sizes = {}
    for index in range(16):
        api._write_bytes(tmp_path / f"small-{index}", b"x", small_sizes)
    with pytest.raises(ValueError, match="file count cap"):
        api._write_bytes(tmp_path / "seventeenth", b"x", small_sizes)
    assert not any((tmp_path / name).exists() for name in (
        "overflow", "oversize", "seventeenth",
    ))


def test_07_refusal_control_requires_expected_failure():
    api = _implementation()

    def correct():
        raise ValueError("exact refusal")

    def wrong_message():
        raise ValueError("unrelated")

    def wrong_type():
        raise RuntimeError("exact refusal")

    api._expect_refusal("control", correct, ValueError, "exact refusal")
    for action in (lambda: None, wrong_message, wrong_type):
        with pytest.raises(AssertionError, match="control"):
            api._expect_refusal("control", action, ValueError, "exact refusal")


def test_08_real_probe_wires_production_readers_without_fallback():
    api = _implementation()
    tree = ast.parse(inspect.getsource(api))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    attributes = {
        node.func.attr for node in calls if isinstance(node.func, ast.Attribute)
    }
    assert {"_load_native_state", "_load_adapter_state", "_equal", "save"} <= attributes
    assert not {"load", "add_safe_globals", "clear_safe_globals"} & attributes
    assert api.MAX_TENSOR_ELEMENTS == 8192
    assert api.MAX_TENSOR_BYTES == 65536
    assert len(api.CASE_NAMES) == len(set(api.CASE_NAMES)) == 12
    assert not any(
        isinstance(node, ast.Call)
        for statement in tree.body
        if not isinstance(statement, (ast.FunctionDef, ast.ClassDef))
        for node in ast.walk(statement)
    ), "no module-level probe launch or other calls"
    probe_source = inspect.getsource(api.run_cpu_conformance)
    assert "weights_only=False" not in inspect.getsource(api)
    assert "_capture_rng" not in probe_source and ".cuda" not in probe_source
    assert "training_verified" in probe_source and "production_admitted" in probe_source
