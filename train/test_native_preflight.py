"""Synthetic diagnostics only. Real candidate runtime checks remain UNRUN."""

from __future__ import annotations

import builtins
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import sys
import sysconfig
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PINS = {
    "unsloth": "2026.10.3", "unsloth_zoo": "2026.10.3", "trl": "1.13.0",
    "transformers": "5.17.0", "vllm": "0.23.0", "torch": "2.11.0",
    "accelerate": "1.4.0", "datasets": "4.8.5",
}
FLAGS = (
    "candidate_approved", "dependency_graph_verified", "abi_verified",
    "runtime_verified", "training_verified", "launch_authorized",
)


def api():
    path = Path(__file__).with_name("native_preflight.py")
    assert path.is_file(), "missing private runtime preflight implementation"
    module = importlib.import_module("train.native_preflight")
    assert callable(getattr(module, "_probe_runtime", None)), "missing private probe"
    return module


def admit(*, exercise_kernel):
    assert type(exercise_kernel) is bool


class Candidate(SimpleNamespace):
    @property
    def module(self):
        if self.loaded_api is None:
            module = api()
            self.patch.setattr(module, "_implementation_name", lambda: "cpython")
            self.patch.setattr(module, "_load_frameworks", self.load)
            self.loaded_api = module
        return self.loaded_api


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch):
    real_import = builtins.__import__
    real_module = importlib.import_module
    attempted = []

    def check(name):
        if name.split(".")[0] in {*PINS, "peft", "triton", "modal"}:
            attempted.append(name)
            raise AssertionError("framework import forbidden in model-free tests")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return real_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return real_module(name, *args, **kwargs)

    def reject(*args, **kwargs):
        attempted.append("external")
        raise AssertionError("external execution forbidden in model-free tests")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(subprocess, "Popen", reject)
    yield
    assert attempted == []


@pytest.fixture
def candidate(monkeypatch, tmp_path):
    qualification = importlib.import_module("train.native_qualification")
    versions = {**PINS, "peft": "0.18.0"}
    calls = []
    properties = SimpleNamespace(major=8, minor=0, total_memory=2**30,
                                 multi_processor_count=10)

    class Tensor:
        def __matmul__(self, other):
            calls.append("matmul")
            return self

        def tolist(self):
            return [[2.0, 2.0], [2.0, 2.0]]

    torch = SimpleNamespace(
        __version__=PINS["torch"], float16=object(),
        version=SimpleNamespace(cuda="12.8"),
        cuda=SimpleNamespace(
            is_available=lambda: True, device_count=lambda: 1,
            get_device_properties=lambda index: properties,
            synchronize=lambda index: calls.append("sync"),
        ),
        ones=lambda *args, **kwargs: Tensor(),
    )
    for name, version in PINS.items():
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(__version__=version))
    monkeypatch.setitem(sys.modules, "torch", torch)
    # Fixture-only reviewed representation, not a substituted production pin.
    source = tmp_path.resolve() / "selected.py"
    source.write_text("fixture_value = 1\n", encoding="ascii")
    monkeypatch.setitem(sys.modules, "transformers.trainer",
                        SimpleNamespace(__file__=str(source)))
    monkeypatch.setattr(qualification, "_SELECTED_SOURCES", {
        "transformers.trainer": hashlib.sha256(source.read_bytes()).hexdigest(),
    })
    monkeypatch.setattr(importlib.metadata, "version", versions.get)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(sysconfig, "get_config_var",
                        lambda config_name: "cpython-312-x86_64-linux-gnu")
    monkeypatch.setattr(struct, "calcsize", lambda fmt: 8)
    def load():
        calls.append("load")
        return SimpleNamespace(torch=torch)

    return Candidate(loaded_api=None, patch=monkeypatch, load=load,
                     versions=versions, calls=calls, torch=torch,
                     properties=properties, source=source)


def probe(candidate, **kwargs):
    return candidate.module._probe_runtime(admit=admit, **kwargs)


def test_cold_import_has_no_effects(monkeypatch):
    before = dict(os.environ)
    attempted = []
    monkeypatch.delitem(sys.modules, "train.native_preflight", raising=False)

    def reject(*args, **kwargs):
        attempted.append("observation")
        raise AssertionError("cold import performed observation")

    monkeypatch.setattr(importlib.metadata, "version", reject)
    monkeypatch.setattr(builtins, "open", reject)
    monkeypatch.setattr(Path, "open", reject)
    monkeypatch.setattr(platform, "system", reject)
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("train") and name != "train.native_preflight":
            attempted.append(name)
            raise AssertionError("cold import loaded project implementation")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    api()
    assert attempted == []
    assert dict(os.environ) == before


def test_admission_precedes_observation(monkeypatch):
    module = api()
    calls = []

    def reject(*args, **kwargs):
        calls.append("observe")
        raise AssertionError("observation before admission")

    def denied(*, exercise_kernel):
        raise PermissionError("not admitted")

    monkeypatch.setattr(platform, "system", reject)
    monkeypatch.setattr(importlib.metadata, "version", reject)
    monkeypatch.setattr(module, "_load_frameworks", reject)
    with pytest.raises(PermissionError):
        module._probe_runtime(admit=denied)
    assert calls == []


def test_exact_candidate_metadata(candidate):
    report = probe(candidate)
    assert report["installed"]["versions"] == {**PINS, "peft": "0.18.0"}
    assert report["installed"]["unresolved_count"] == 5
    assert report["installed"]["frozen_count"] > 0
    assert report["loaded"]["status"] == "observed"
    assert report["device"]["status"] == "observed"
    assert report["kernel"]["status"] == "UNRUN"
    assert all(report[flag] is False for flag in FLAGS)
    assert candidate.calls == ["load"]


def test_exact_package_mismatch_blocks_loading(candidate):
    for package in PINS:
        candidate.versions[package] = PINS[package] + ".0"
        report = probe(candidate)
        assert f"exact:{package}" in report["issues"]
        assert report["loaded"]["status"] == "UNRUN"
        candidate.versions[package] = PINS[package]
    assert candidate.calls == []


def test_wrong_host_blocks_loading(candidate, monkeypatch):
    mutations = (
        (sys, "version_info", (3, 11, 0)),
        (platform, "system", lambda: "Darwin"),
        (platform, "machine", lambda: "aarch64"),
        (struct, "calcsize", lambda fmt: 4),
        (candidate.module, "_implementation_name", lambda: "pypy"),
        (sysconfig, "get_config_var", lambda config_name: "INVALID_TEST_ABI"),
    )
    for target, name, value in mutations:
        with monkeypatch.context() as patch:
            patch.setattr(target, name, value)
            assert probe(candidate)["host"]["status"] == "blocked"
    assert candidate.calls == []


def test_cpu_only_and_no_cuda(candidate, monkeypatch):
    mutations = (
        (candidate.torch.version, "cuda", None),
        (candidate.torch.cuda, "is_available", lambda: False),
        (candidate.torch.cuda, "device_count", lambda: 0),
        (candidate.torch.cuda, "device_count", lambda: 2),
    )
    for target, name, value in mutations:
        with monkeypatch.context() as patch:
            patch.setattr(target, name, value)
            assert probe(candidate, exercise_kernel=True)["device"]["status"] == "blocked"
    assert "matmul" not in candidate.calls


def test_malformed_device_properties(candidate, monkeypatch):
    for name, value in (("major", True), ("minor", -1),
                        ("total_memory", None), ("multi_processor_count", 2**63)):
        with monkeypatch.context() as patch:
            patch.setattr(candidate.properties, name, value)
            report = probe(candidate, exercise_kernel=True)
            assert report["device"]["status"] == "blocked"
    assert "matmul" not in candidate.calls


def test_loaded_metadata_is_separate(candidate, monkeypatch):
    with monkeypatch.context() as patch:
        patch.delitem(sys.modules, "vllm")
        report = probe(candidate, exercise_kernel=True)
        assert "not_loaded:vllm" in report["issues"]
        assert report["installed"]["status"] == "observed"
    with monkeypatch.context() as patch:
        patch.setattr(candidate.torch, "__version__", "2.10.0")
        report = probe(candidate, exercise_kernel=True)
        assert "loaded_version:torch" in report["issues"]
        assert report["kernel"]["status"] == "UNRUN"


def test_selected_source_drift(candidate):
    candidate.source.write_text("fixture_value = 2\n", encoding="ascii")
    report = probe(candidate, exercise_kernel=True)
    assert report["loaded"]["sources"]["transformers.trainer"] == "drift_or_unreadable"
    assert report["kernel"]["status"] == "UNRUN"
    assert "matmul" not in candidate.calls


def test_kernel_requires_opt_in(candidate):
    assert probe(candidate)["kernel"]["status"] == "UNRUN"
    assert "matmul" not in candidate.calls
    admitted = []

    def owner(*, exercise_kernel):
        admitted.append(exercise_kernel)

    report = candidate.module._probe_runtime(admit=owner, exercise_kernel=True)
    assert admitted == [True]
    assert report["kernel"]["status"] == "observed"
    assert report["kernel"]["scope"] == "single_fp16_2x2_matmul_only"
    assert candidate.calls.count("matmul") == candidate.calls.count("sync") == 1
    assert all(report[flag] is False for flag in FLAGS)


def test_kernel_failure_is_not_readiness(candidate, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("/private/path secret " + "x" * 100000)

    class WrongResult:
        def __matmul__(self, other):
            return self

        def tolist(self):
            return [[0.0, 0.0], [0.0, 0.0]]

    for ones in (broken, lambda *args, **kwargs: WrongResult()):
        with monkeypatch.context() as patch:
            patch.setattr(candidate.torch, "ones", ones)
            report = probe(candidate, exercise_kernel=True)
            assert report["kernel"]["status"] == "failed"
            assert all(report[flag] is False for flag in FLAGS)


def test_diagnostics_are_bounded(candidate, monkeypatch):
    candidate.versions["torch"] = "/private/path secret " + "x" * 100000
    report = probe(candidate)
    encoded = json.dumps(report)
    assert len(encoded.encode("utf-8")) <= 16384
    assert "/private/path" not in encoded and "secret" not in encoded
    candidate.versions["torch"] = PINS["torch"]

    def broken():
        raise RuntimeError("/private/path secret " + "x" * 100000)

    monkeypatch.setattr(candidate.module, "_load_frameworks", broken)
    encoded = json.dumps(probe(candidate))
    assert "framework_inspection_failed" in encoded
    assert len(encoded.encode("utf-8")) <= 16384
    assert "/private/path" not in encoded and "secret" not in encoded
