"""Named numeric tests for train.qualification_owned_stop (plan file C).

Finite ordinary pytest tests, no parametrization, no plugins, no processes,
no SDK, no network, no real staging: the launcher and watchdog delegations
are monkeypatched witnesses, because this binding must delegate to the
existing reviewed mechanisms instead of reimplementing supervision. UNRUN
at delivery: the parent executes and reviews. Test names and numeric
criteria come from docs/core-v159-host-plan.md before implementation.
"""

from __future__ import annotations

import math
from pathlib import Path
import os
import pickle

import pytest

from train import modal_app_stop_launcher
from train import qualification_owned_stop as owned_stop
from train import qualification_watchdog


_APP_ID = "ap-" + "A1b2C3d4E5" * 2 + "F6"
_DEFAULTS = {
    "interpreter": Path("/synthetic/python"),
    "interpreter_sha256": "a" * 64,
    "adapter_sha256": "b" * 64,
    "source_root": Path("/synthetic/train"),
    "sdk_root": Path("/synthetic/sdk"),
    "sdk_pins": {"modal/app.py": "c" * 64},
    "private_scratch": Path("/synthetic/scratch"),
    "environment": {"PATH": "/synthetic/bin"},
    "rpc_seconds": 5.0,
    "teardown_seconds": 1.0,
    "arm_seconds": 0.5,
    "ownership_confirmed": True,
}


def _binding(**overrides) -> owned_stop.OwnedAppStopBinding:
    kwargs = dict(_DEFAULTS)
    kwargs.update(overrides)
    return owned_stop.OwnedAppStopBinding(**kwargs)


def _stage_witness(monkeypatch):
    calls: list = []
    sentinel = object()

    def fake_stage(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(owned_stop.launcher, "stage_trusted_teardown", fake_stage)
    return calls, sentinel


def _arm_witness(monkeypatch):
    calls: list = []
    sentinel = object()

    def fake_arm(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(owned_stop.watchdog, "arm", fake_arm)
    return calls, sentinel


def test_binding_requires_explicit_ownership_confirmation() -> None:
    for substitute in (False, None, 1, "yes"):
        with pytest.raises(ValueError):
            _binding(ownership_confirmed=substitute)
    assert type(_binding(ownership_confirmed=True)) is owned_stop.OwnedAppStopBinding


def test_binding_path_validation() -> None:
    refusals = (
        {"interpreter": Path("relative/python")},
        {"source_root": Path("relative/train")},
        {"sdk_root": Path("relative/sdk")},
        {"private_scratch": Path("relative/scratch")},
        {"interpreter": "/synthetic/python"},  # non-Path
    )
    assert len(refusals) == 5
    for overrides in refusals:
        with pytest.raises(ValueError):
            _binding(**overrides)


def test_binding_digest_validation() -> None:
    refusals = (
        {"interpreter_sha256": "a" * 63},
        {"interpreter_sha256": "a" * 65},
        {"interpreter_sha256": "A" * 64},
        {"interpreter_sha256": 42},
        {"adapter_sha256": "a" * 63},
    )
    assert len(refusals) == 5
    for overrides in refusals:
        with pytest.raises(ValueError):
            _binding(**overrides)


def test_binding_seconds_bounds() -> None:
    for rpc in (0, -1, 30.5, math.inf, math.nan, "5"):
        with pytest.raises(ValueError):
            _binding(rpc_seconds=rpc)
    assert type(_binding(rpc_seconds=30)) is owned_stop.OwnedAppStopBinding
    for teardown in (0, 31, math.inf):
        with pytest.raises(ValueError):
            _binding(teardown_seconds=teardown)
    assert type(_binding(teardown_seconds=30)) is owned_stop.OwnedAppStopBinding
    for arm in (0, 5.5, math.nan):
        with pytest.raises(ValueError):
            _binding(arm_seconds=arm)
    assert type(_binding(arm_seconds=5)) is owned_stop.OwnedAppStopBinding


def test_binding_pins_and_environment_copied(monkeypatch) -> None:
    pins = {"modal/app.py": "c" * 64}
    environment = {"PATH": "/synthetic/bin"}
    binding = _binding(sdk_pins=pins, environment=environment)
    pins["injected"] = "d" * 64
    environment["INJECTED"] = "1"
    calls, _sentinel = _stage_witness(monkeypatch)
    binding.stage(expected_app_id=_APP_ID, expires_at=1762000000.5)
    assert calls[0]["sdk_pins"] == {"modal/app.py": "c" * 64}
    assert calls[0]["environment"] == {"PATH": "/synthetic/bin"}
    with pytest.raises(ValueError):
        _binding(sdk_pins={})
    with pytest.raises(ValueError):
        _binding(environment={})


def test_binding_not_serializable() -> None:
    binding = _binding()
    with pytest.raises(TypeError):
        pickle.dumps(binding)
    with pytest.raises(TypeError):
        binding.__reduce_ex__(4)


def test_stage_delegates_exact_inputs(monkeypatch) -> None:
    calls, sentinel = _stage_witness(monkeypatch)
    binding = _binding()
    result = binding.stage(expected_app_id=_APP_ID, expires_at=1762000000.5)
    assert result is sentinel
    assert len(calls) == 1
    assert calls[0] == {
        "interpreter": Path("/synthetic/python"),
        "interpreter_sha256": "a" * 64,
        "source_root": Path("/synthetic/train"),
        "adapter_module": Path("/synthetic/train") / "modal_app_stop.py",
        "adapter_sha256": "b" * 64,
        "sdk_root": Path("/synthetic/sdk"),
        "sdk_pins": {"modal/app.py": "c" * 64},
        "private_scratch": Path("/synthetic/scratch"),
        "expected_app_id": _APP_ID,
        "ownership_confirmed": True,
        "explicitly_trusted": True,
        "expires_at": 1762000000.5,
        "rpc_seconds": 5.0,
        "environment": {"PATH": "/synthetic/bin"},
    }


def test_stage_rejects_bad_app_id(monkeypatch) -> None:
    calls, _sentinel = _stage_witness(monkeypatch)
    binding = _binding()
    for app_id in (42, "", None):
        with pytest.raises(ValueError):
            binding.stage(expected_app_id=app_id, expires_at=1762000000.5)
    assert calls == []


def test_stage_rejects_nonfinite_expiry(monkeypatch) -> None:
    calls, _sentinel = _stage_witness(monkeypatch)
    binding = _binding()
    for expires_at in (math.inf, math.nan, "1762000000.5"):
        with pytest.raises(ValueError):
            binding.stage(expected_app_id=_APP_ID, expires_at=expires_at)
    assert calls == []


def test_arm_delegates_exact_inputs(monkeypatch) -> None:
    calls, sentinel = _arm_witness(monkeypatch)
    binding = _binding()
    custody = object()
    app_identity = object()
    teardown = object()
    evidence = Path("/synthetic/evidence.jsonl")
    result = binding.arm(
        custody=custody, app_identity=app_identity, app_id=_APP_ID,
        teardown=teardown, deadline=1234.5, evidence_path=evidence,
    )
    assert result is sentinel
    assert len(calls) == 1
    assert calls[0] == {
        "custody": custody,
        "app_identity": app_identity,
        "app_id": _APP_ID,
        "teardown": teardown,
        "deadline": 1234.5,
        "evidence_path": evidence,
        "teardown_seconds": 1.0,
        "arm_seconds": 0.5,
    }


def test_arm_passes_binding_seconds_not_caller_seconds(monkeypatch) -> None:
    calls, _sentinel = _arm_witness(monkeypatch)
    binding = _binding(teardown_seconds=2.0, arm_seconds=0.25)
    binding.arm(
        custody=object(), app_identity=object(), app_id=_APP_ID,
        teardown=object(), deadline=1234.5,
        evidence_path=Path("/synthetic/evidence.jsonl"),
    )
    assert calls[0]["teardown_seconds"] == 2.0
    assert calls[0]["arm_seconds"] == 0.25
    assert calls[0]["teardown_seconds"] != 1.0  # not the watchdog defaults


def test_no_custom_supervision_surfaces() -> None:
    defined_classes = [
        value for value in vars(owned_stop).values()
        if isinstance(value, type) and value.__module__ == owned_stop.__name__
    ]
    assert defined_classes == [owned_stop.OwnedAppStopBinding]
    binding = _binding()
    forbidden = ("popen", "socket", "thread", "signal", "subprocess", "spawn", "fork")
    for name in dir(binding):
        for word in forbidden:
            assert word not in name.lower()


def test_public_surface_is_staging_and_readonly_isolated_facts() -> None:
    binding = _binding()
    views = {
        "interpreter", "interpreter_sha256", "adapter_sha256", "source_root",
        "sdk_root", "sdk_pins", "private_scratch", "environment",
        "rpc_seconds", "teardown_seconds", "arm_seconds",
    }
    public = {name for name in dir(binding) if not name.startswith("_")}
    assert public == views | {"stage", "arm", "timing_facts"}
    assert {name for name in public if callable(getattr(binding, name))} == {
        "stage", "arm", "timing_facts"}
    for name in views:
        assert isinstance(vars(type(binding))[name], property)
        assert vars(type(binding))[name].fset is None
        with pytest.raises(AttributeError):
            setattr(binding, name, getattr(binding, name))
    for name in ("sdk_pins", "environment"):
        original = getattr(binding, name)
        observed = dict(original)
        original.clear()
        assert getattr(binding, name) == observed


def test_binding_reuses_existing_modules() -> None:
    assert owned_stop.launcher is modal_app_stop_launcher
    assert owned_stop.watchdog is qualification_watchdog


def test_stage_expiry_forwarded_unchanged(monkeypatch) -> None:
    calls, _sentinel = _stage_witness(monkeypatch)
    binding = _binding()
    binding.stage(expected_app_id=_APP_ID, expires_at=1762000000.5)
    assert calls[0]["expires_at"] == 1762000000.5


def test_stage_expected_app_id_forwarded_unchanged(monkeypatch) -> None:
    calls, _sentinel = _stage_witness(monkeypatch)
    binding = _binding()
    binding.stage(expected_app_id=_APP_ID, expires_at=1762000000.5)
    assert calls[0]["expected_app_id"] == _APP_ID


def test_arm_evidence_path_forwarded_unchanged(monkeypatch) -> None:
    calls, _sentinel = _arm_witness(monkeypatch)
    binding = _binding()
    evidence = Path("/synthetic/evidence.jsonl")
    binding.arm(
        custody=object(), app_identity=object(), app_id=_APP_ID,
        teardown=object(), deadline=1234.5, evidence_path=evidence,
    )
    assert calls[0]["evidence_path"] is evidence


def test_arm_identity_forwarded_by_identity(monkeypatch) -> None:
    calls, _sentinel = _arm_witness(monkeypatch)
    binding = _binding()
    custody = object()
    app_identity = object()
    teardown = object()
    binding.arm(
        custody=custody, app_identity=app_identity, app_id=_APP_ID,
        teardown=teardown, deadline=1234.5,
        evidence_path=Path("/synthetic/evidence.jsonl"),
    )
    assert calls[0]["custody"] is custody
    assert calls[0]["app_identity"] is app_identity
    assert calls[0]["teardown"] is teardown


def test_binding_constructor_does_no_file_io(monkeypatch) -> None:
    opened: list = []
    real_open = os.open

    def witness(*args, **kwargs):
        opened.append(args)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(os, "open", witness)
    binding = _binding()  # synthetic nonexistent paths: construction only
    assert type(binding) is owned_stop.OwnedAppStopBinding
    assert opened == []
