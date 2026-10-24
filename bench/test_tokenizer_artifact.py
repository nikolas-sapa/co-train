"""Failure-first contamination-test artifact boundary, not model approval.

Synthetic fixture digests below are frozen independently of the helper. Real
cached identity is separately frozen in the owner-reviewed test-only manifest.
Subprocess guards use stdlib only; no tokenizer dependency is import-or-skipped.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROLS = {
    "test_long_positive_control_is_longer_and_still_canonical",
    "test_v2_control_is_length_matched_to_bird",
}
FIXTURE_BYTES = {
    "tokenizer.json": b"{}\n",
    "tokenizer_config.json": b'{"tokenizer_class":"PreTrainedTokenizerFast"}\n',
}
FIXTURE_DIGESTS = {
    "tokenizer.json": "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356",
    "tokenizer_config.json": "636d02cf43542ffb6c3422731e8fd0af921ecc63e202ffeed1a8b3092c71be6a",
}

# Audit attempts, not successful connections. A swallowed denial still leaves
# evidence and makes the launcher fail. The sensitivity test attempts localhost
# port 9, which is denied BEFORE the syscall, so no service/network is needed.
LAUNCHER = r"""
import json, os, pathlib, socket, sys
cache = pathlib.Path(os.environ["HF_HOME"]).resolve()
events = []
def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        events.append("network:" + event)
        raise RuntimeError("OFFLINE_NETWORK_ATTEMPT:" + event)
    if event in {"open", "os.listdir", "os.scandir"} and args:
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            path = pathlib.Path(os.fsdecode(value)).absolute()
            if path == cache or cache in path.parents:
                events.append("cache:" + str(path))
                raise RuntimeError("TOKENIZER_CACHE_ACCESS:" + str(path))
sys.addaudithook(audit)
original_stat = os.stat
def guarded_stat(path, *args, **kwargs):
    if isinstance(path, (str, bytes, os.PathLike)):
        candidate = pathlib.Path(os.fsdecode(path)).absolute()
        if candidate == cache or cache in candidate.parents:
            events.append("cache:" + str(candidate))
            raise RuntimeError("TOKENIZER_CACHE_ACCESS:" + str(candidate))
    return original_stat(path, *args, **kwargs)
os.stat = guarded_stat
def denied_loader(cls, *args, **kwargs):
    events.append("tokenizer-loader")
    raise RuntimeError("TOKENIZER_LOADER_CALLED")
def profile(frame, event, arg):
    if (event == "call" and frame.f_code.co_name == "from_pretrained"
            and frame.f_code.co_filename.replace("\\", "/").endswith(
                "/transformers/models/auto/tokenization_auto.py")):
        # Raising disables the profile hook. Replace the class entry point too,
        # so the second original control cannot slip past the first denial.
        cls = frame.f_locals["cls"]
        cls.from_pretrained = classmethod(denied_loader)
        denied_loader(cls)
sys.setprofile(profile)
mode, args = json.loads(sys.argv[1])
try:
    if mode == "network-probe":
        try:
            with socket.socket() as connection:
                connection.settimeout(0.1)
                connection.connect(("127.0.0.1", 9))
        except RuntimeError:
            pass
        code = 0
    else:
        import pytest
        code = int(pytest.main(args))
finally:
    sys.setprofile(None)
    print("OFFLINE_EVENTS=" + json.dumps(events), flush=True)
if events:
    sys.exit(86)
sys.exit(code)
"""


def _run(tmp_path, args, *, mode="pytest", timeout=90):
    cache = tmp_path / "hf-home"
    cache.mkdir()
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env.update({
        "HF_HOME": str(cache),
        "HF_HUB_CACHE": str(cache / "hub"),
        "HUGGINGFACE_HUB_CACHE": str(cache / "hub"),
        "TRANSFORMERS_CACHE": str(cache / "transformers"),
        "HF_DATASETS_CACHE": str(cache / "datasets"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    result = subprocess.run(
        [sys.executable, "-c", LAUNCHER, json.dumps([mode, args])],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    assert "OFFLINE_EVENTS=" in output, output
    event_line = next(line for line in result.stdout.splitlines()
                      if line.startswith("OFFLINE_EVENTS="))
    return result.returncode, output, json.loads(event_line.split("=", 1)[1])


def _collected_controls(output):
    return {name for name in CONTROLS
            if f"bench/test_contamination.py::{name}" in output}


def test_default_collection_excludes_tokenizer_integration(tmp_path):
    code, output, events = _run(tmp_path, ["--collect-only", "-q",
                                         "bench/test_contamination.py"])
    assert code == 0, output
    assert events == [], output
    assert _collected_controls(output) == set(), output


def test_explicit_marker_overrides_default_and_keeps_both_controls(tmp_path):
    code, output, events = _run(
        tmp_path, ["--collect-only", "-q", "-m", "tokenizer_integration",
                   "bench/test_contamination.py"])
    assert code == 0, output
    assert events == [], output
    assert _collected_controls(output) == CONTROLS, output


def test_cold_cache_default_contamination_lane(tmp_path):
    # No -m: exercise the real default config and original scientific tests,
    # rather than merely testing a proposed helper that does not exist yet.
    code, output, events = _run(
        tmp_path, ["-q", "-ra", "bench/test_contamination.py"])
    assert events == [], output
    assert code == 0, output


def test_requested_integration_without_path_fails_not_skips(tmp_path):
    code, output, events = _run(
        tmp_path, ["-q", "-ra", "-m", "tokenizer_integration",
                   "bench/test_contamination.py"])
    assert events == [], output
    assert code == 1, output
    assert "TokenizerArtifactError" in output, output
    assert "explicit local artifact directory" in output, output
    assert "2 errors" in output or "2 failed" in output, output
    assert "skipped" not in output.lower(), output


def test_offline_network_detector_fails_even_if_denial_is_swallowed(tmp_path):
    code, output, events = _run(tmp_path, [], mode="network-probe")
    assert code == 86, output
    assert events == ["network:socket.connect"], output


@pytest.fixture
def artifact_api():
    # Import inside fixture: behavioral old-controls failures remain collectable
    # even before the stdlib helper exists. Missing API is separate RED evidence.
    return importlib.import_module("bench.tokenizer_artifact")


@pytest.fixture
def synthetic_artifact(tmp_path):
    path = tmp_path / "synthetic-tokenizer"
    path.mkdir()
    for name, data in FIXTURE_BYTES.items():
        (path / name).write_bytes(data)
    return path


@pytest.mark.parametrize("bad_path", [None, "", "absent", "file"])
def test_missing_path_refuses_before_loader(artifact_api, tmp_path, bad_path):
    path = bad_path
    if bad_path in {"absent", "file"}:
        path = tmp_path / bad_path
        if bad_path == "file":
            path.write_text("not a directory")
    calls = []
    with pytest.raises(artifact_api.TokenizerArtifactError):
        artifact_api.load_tokenizer_artifact(
            path, expected_files=FIXTURE_DIGESTS,
            loader=lambda *a, **kw: calls.append((a, kw)))
    assert calls == []


@pytest.mark.parametrize("filename", sorted(FIXTURE_BYTES))
def test_missing_required_file_refuses_before_loader(
        artifact_api, synthetic_artifact, filename):
    (synthetic_artifact / filename).unlink()
    calls = []
    with pytest.raises(artifact_api.TokenizerArtifactError, match=filename):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=FIXTURE_DIGESTS,
            loader=lambda *a, **kw: calls.append((a, kw)))
    assert calls == []


@pytest.mark.parametrize("filename", sorted(FIXTURE_BYTES))
def test_one_byte_corruption_refuses_before_loader(
        artifact_api, synthetic_artifact, filename):
    path = synthetic_artifact / filename
    data = path.read_bytes()
    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    calls = []
    with pytest.raises(artifact_api.TokenizerArtifactError, match=filename):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=FIXTURE_DIGESTS,
            loader=lambda *a, **kw: calls.append((a, kw)))
    assert calls == []


def test_admitted_loader_is_local_only_without_remote_code(
        artifact_api, synthetic_artifact):
    calls = []
    sentinel = object()

    def loader(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    result = artifact_api.load_tokenizer_artifact(
        synthetic_artifact, expected_files=FIXTURE_DIGESTS, loader=loader)
    assert result is sentinel
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert len(args) == 1
    assert Path(args[0]).resolve() == synthetic_artifact.resolve()
    assert kwargs == {"local_files_only": True, "trust_remote_code": False}


@pytest.mark.parametrize("expected", [
    None, [], {}, {"../tokenizer.json": "a" * 64},
    {"/tokenizer.json": "a" * 64}, {"sub/tokenizer.json": "a" * 64},
    {"sub\\tokenizer.json": "a" * 64}, {".": "a" * 64},
    {"..": "a" * 64}, {"": "a" * 64}, {3: "a" * 64},
    {"tokenizer.json": None}, {"tokenizer.json": "a" * 63},
    {"tokenizer.json": "z" * 64}, {"tokenizer.json": "A" * 64},
])
def test_invalid_manifest_refuses_before_loader(
        artifact_api, synthetic_artifact, expected):
    calls = []
    with pytest.raises(artifact_api.TokenizerArtifactError, match="manifest"):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=expected,
            loader=lambda *a, **kw: calls.append((a, kw)))
    assert calls == []


@pytest.mark.parametrize("path", [42, True, b"bytes", " ", "bad\x00path"])
def test_invalid_path_specification_is_named(artifact_api, path):
    with pytest.raises(artifact_api.TokenizerArtifactError):
        artifact_api.load_tokenizer_artifact(
            path, expected_files=FIXTURE_DIGESTS, loader=lambda *a, **kw: None)


def test_admission_failure_precedes_dependency_import(
        artifact_api, synthetic_artifact, monkeypatch):
    import builtins

    real_import = builtins.__import__
    imports = []

    def forbidden_import(name, *args, **kwargs):
        if name == "transformers":
            imports.append(name)
            raise AssertionError("dependency imported before admission")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbidden_import)
    (synthetic_artifact / "tokenizer.json").write_bytes(b"changed")
    with pytest.raises(artifact_api.TokenizerArtifactError, match="tokenizer.json"):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=FIXTURE_DIGESTS)
    assert imports == []


def test_requested_missing_dependency_is_named_not_skipped(
        artifact_api, synthetic_artifact, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def missing_dependency(name, *args, **kwargs):
        if name == "transformers":
            raise ModuleNotFoundError("controlled absent transformers")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_dependency)
    with pytest.raises(artifact_api.TokenizerArtifactError, match="transformers"):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=FIXTURE_DIGESTS)


@pytest.mark.parametrize("loader", [False, 7, "not callable"])
def test_invalid_loader_is_named(artifact_api, synthetic_artifact, loader):
    with pytest.raises(artifact_api.TokenizerArtifactError, match="loader"):
        artifact_api.load_tokenizer_artifact(
            synthetic_artifact, expected_files=FIXTURE_DIGESTS, loader=loader)


def test_matching_symlink_bytes_are_accepted(
        artifact_api, synthetic_artifact, tmp_path):
    directory = tmp_path / "snapshot"
    directory.mkdir()
    for name in FIXTURE_DIGESTS:
        (directory / name).symlink_to(synthetic_artifact / name)
    calls = []
    artifact_api.load_tokenizer_artifact(
        directory, expected_files=FIXTURE_DIGESTS,
        loader=lambda *a, **kw: calls.append((a, kw)))
    assert len(calls) == 1
