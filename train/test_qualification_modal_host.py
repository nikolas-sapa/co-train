"""Named numeric tests for train.qualification_modal_host (plan file B).

Finite ordinary pytest tests, no parametrization, no plugins, no processes,
no real SDK, no network. Fake SDK classes carry the exact `__module__` and
`__name__` labels of the real async implementation classes so the host's
structural binding checks are exercised; genuine SDK compatibility is a
separate parent check, not mocked proof here. UNRUN at delivery: the parent
executes and reviews. Test names and numeric criteria come from
docs/core-v159-host-plan.md (including the defect 1-3 revision, tests
22-25, the revision-2 blocker tests 26-30 and the revision-3 binding
test 31) before implementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import pickle
import types

import pytest

from train import native_qualification as native
from train import qualification_engineering_host as engineering
from train import qualification_modal_host as modal_host
from train import qualification_owned_stop as owned_stop
from train.engineering_budget import (
    AncillaryEstimates,
    BudgetTerms,
    GpuWorkload,
    PreparationAccount,
    RateObservation,
    ResourceRates,
    plan_engineering_budget,
)
from train.qualification_image_plan import candidate_recipe, recipe_sha256


_NOW = 1_800_000_000
_APP_ID = "ap-" + "A1b2C3d4E5" * 2 + "F6"
_SANDBOX_ID = "sb-" + "B1c2D3e4F5a6"


@pytest.fixture(autouse=True)
def _reset_one_resource_latch():
    # Test hygiene only: the production latch is process-wide by design.
    yield
    with modal_host._LATCH_LOCK:
        modal_host._ACTIVE_HOST = None


class _FakeClock:
    def __init__(self, start: float) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now


def _request(*, db_root: str = "/synthetic/data") -> native.QualificationRequest:
    return native.QualificationRequest(
        tasks=(), db_root=Path(db_root),
        model_dir=Path("/synthetic/model"), output_dir=Path("/synthetic/output"),
        source_pins=(), database_pins=(),
        runtime_inventory=native.FilePin(Path("/synthetic/inventory.json"), 0, "0" * 64),
        image_digest="synthetic-not-admitted",
        bounds=native.AttemptBounds(
            Decimal("25"), Decimal("0"), Decimal("25"), 1800, 128, 1024, 60,
        ),
    )


def _policy(directory: Path, name: str = "policy.json",
            data: bytes = b"owner-approved-policy\n") -> native.FilePin:
    """REAL private policy file fixture with a matching FilePin (0o600)."""
    path = directory / name
    path.write_bytes(data)
    path.chmod(0o600)
    return native.FilePin(path, len(data), hashlib.sha256(data).hexdigest())


def _issue(*, duration_seconds: int = 1200, preparation_seconds: int = 600,
           expires_in: int = 3600, policy_pin=None, gpu_label="A100",
           request=None):
    recipe = candidate_recipe()
    return engineering.issue_engineering_authorization(
        request=request if request is not None else _request(),
        policy_pin=(
            policy_pin if policy_pin is not None
            else native.FilePin(Path("/synthetic/policy.json"), 128, "a" * 64)
        ),
        terms=BudgetTerms(Decimal("25"), Decimal("5")),
        rates=ResourceRates(
            runtime_context="sandbox",
            gpu=RateObservation(
                Decimal("0.00001"), "USD/gpu-second", "pricing-page", _NOW - 100,
            ),
            cpu=RateObservation(
                Decimal("0.000001"), "USD/physical-core-second", "pricing-page", _NOW - 100,
            ),
            ram=RateObservation(
                Decimal("0.000001"), "USD/GiB-second", "pricing-page", _NOW - 100,
            ),
        ),
        workload=GpuWorkload(1, 4, Decimal("16"), duration_seconds),
        preparation=PreparationAccount(Decimal("1"), Decimal("0.5"), Decimal("2")),
        ancillary=AncillaryEstimates(Decimal("0.5"), Decimal("0.25"), Decimal("1")),
        now_seconds=_NOW,
        expires_at_seconds=_NOW + expires_in,
        preparation_seconds=preparation_seconds,
        image_base_reference=recipe.base_reference,
        image_recipe_sha256=recipe_sha256(recipe),
        gpu_label=gpu_label,
        uploads=(
            ("source", "train/worker.py", 1024, "b" * 64),
            ("wheels", "pkg-1.0.whl", 2048, "c" * 64),
        ),
        setup_argv=("python", "-m", "pip", "install", "--no-index"),
    )


def _fake_sdk(**overrides):
    state = {
        "app_id": _APP_ID,
        "sandbox_id": _SANDBOX_ID,
        "enter_error": None,
        "exit_error": None,
        "stop_error": None,
        "create_error": None,
        "terminate_error": None,
    }
    state.update(overrides)
    calls = {
        "app": [], "app_instances": [], "enter": 0, "exit": 0, "stop": 0,
        "create": [], "terminate": 0, "events": [],
        "from_registry": [], "image_instances": [],
    }

    class App:
        def __init__(self, name=None, *, include_source=True):
            calls["app"].append((name, include_source))
            calls["app_instances"].append(self)
            self.app_id = None

        def run(self, *, detach=False):
            app = self

            class _RunContext:
                async def __aenter__(self):
                    calls["enter"] += 1
                    calls["events"].append("enter")
                    if state["enter_error"] is not None:
                        raise state["enter_error"]
                    app.app_id = state["app_id"]
                    return app

                async def __aexit__(self, *exc_info):
                    calls["exit"] += 1
                    calls["events"].append("exit")
                    if state["exit_error"] is not None:
                        raise state["exit_error"]
                    return False

            return _RunContext()

        async def stop(self):
            calls["stop"] += 1
            calls["events"].append("stop")
            if state["stop_error"] is not None:
                raise state["stop_error"]

    App.__name__ = "_App"
    App.__module__ = "modal.app"

    class SandboxObject:
        @property
        def object_id(self):
            return state["sandbox_id"]

        async def terminate(self):
            calls["terminate"] += 1
            calls["events"].append("terminate")
            if state["terminate_error"] is not None:
                raise state["terminate_error"]

    class Sandbox:
        @staticmethod
        async def create(**kwargs):
            calls["create"].append(kwargs)
            calls["events"].append("create")
            if state["create_error"] is not None:
                raise state["create_error"]
            return SandboxObject()

    Sandbox.__name__ = "_Sandbox"
    Sandbox.__module__ = "modal.sandbox._sandbox"

    class Image:
        @classmethod
        def from_registry(cls, *args, **kwargs):
            calls["from_registry"].append((args, kwargs))
            image = cls()
            calls["image_instances"].append(image)
            return image

    Image.__name__ = "_Image"
    Image.__module__ = "modal._image"
    return types.SimpleNamespace(
        App=App, Sandbox=Sandbox, Image=Image, image=Image(),
        calls=calls, state=state,
    )


class _FakeWatchdog:
    def __init__(self, events: list) -> None:
        self._events = events
        self.finish_calls = 0
        self.report = {
            "status": "local_finished",
            "remote_termination": "UNKNOWN",
            "charged_end": "UNKNOWN",
        }

    def attach(self, events: list) -> None:
        # Share the fake SDK's single ordered event list so cross-mechanism
        # ordering (terminate -> stop -> exit -> finish) is one assertion.
        self._events = events

    def finish(self) -> dict:
        self.finish_calls += 1
        self._events.append("finish")
        return self.report


@pytest.fixture()
def binding(monkeypatch):
    staged: list = []
    armed: list = []
    events: list = []
    controller = _FakeWatchdog(events)

    def fake_stage(**kwargs):
        staged.append(kwargs)
        return "staged-teardown-sentinel"

    def fake_arm(**kwargs):
        armed.append(kwargs)
        return controller

    monkeypatch.setattr(owned_stop.launcher, "stage_trusted_teardown", fake_stage)
    monkeypatch.setattr(owned_stop.watchdog, "arm", fake_arm)
    real = owned_stop.OwnedAppStopBinding(
        interpreter=Path("/synthetic/python"), interpreter_sha256="a" * 64,
        adapter_sha256="b" * 64, source_root=Path("/synthetic/train"),
        sdk_root=Path("/synthetic/sdk"), sdk_pins={"modal/app.py": "c" * 64},
        private_scratch=Path("/synthetic/scratch"),
        environment={"PATH": "/synthetic/bin"}, rpc_seconds=5.0,
        teardown_seconds=1.0, arm_seconds=0.5, ownership_confirmed=True,
    )
    return types.SimpleNamespace(
        binding=real, staged=staged, armed=armed,
        controller=controller, events=events,
    )


def _make_host(tmp_path, binding, *, name="attempt", duration=1200, prep=600,
               clock_start=100.0, sdk=None, gpu="A100", gpu_label="A100",
               cpu=(2.0, 4.0), memory=(8192, 16384), expires_in=3600):
    sdk = sdk if sdk is not None else _fake_sdk()
    binding.controller.attach(sdk.calls["events"])
    # A deterministic per-host policy pin: the claim location is sealed to
    # the exact approved policy FilePin, so distinct hosts need distinct
    # approved pins (distinct owner approvals), never distinct filenames.
    # The claim validates the ACTUAL policy bytes, so each pin gets a REAL
    # private policy file (0o600) whose size and digest match the pin.
    policy_data = f"owner-approved-policy:{name}\n".encode("ascii")
    policy_path = tmp_path / f"policy-{name}.json"
    policy_path.write_bytes(policy_data)
    policy_path.chmod(0o600)
    authorization = _issue(
        duration_seconds=duration, preparation_seconds=prep, expires_in=expires_in,
        policy_pin=native.FilePin(
            policy_path, len(policy_data),
            hashlib.sha256(policy_data).hexdigest(),
        ),
        gpu_label=gpu_label,
    )
    reservation = engineering.claim_attempt_reservation(authorization)
    clock = _FakeClock(clock_start)
    wall = _FakeClock(float(_NOW))
    config = modal_host.ResourceConfig(gpu, cpu, memory)
    host = modal_host.ModalOwnedHost(
        authorization=authorization, reservation=reservation, sdk=sdk,
        resource_config=config, stop_binding=binding.binding,
        evidence_path=tmp_path / f"{name}-evidence.jsonl",
        clock=clock, wall_clock=wall,
    )
    return types.SimpleNamespace(
        host=host, sdk=sdk, authorization=authorization, reservation=reservation,
        clock=clock, wall=wall, config=config,
    )


def _run(coroutine):
    return asyncio.run(coroutine)


def test_default_no_authority_refuses(tmp_path, binding) -> None:
    sdk = _fake_sdk()
    valid = _issue(policy_pin=_policy(tmp_path, name="policy-valid.json"))
    reservation = engineering.claim_attempt_reservation(valid)
    plan = plan_engineering_budget(
        BudgetTerms(Decimal("25"), Decimal("5")),
        ResourceRates(
            runtime_context="sandbox",
            gpu=RateObservation(
                Decimal("0.00001"), "USD/gpu-second", "pricing-page", _NOW - 100,
            ),
            cpu=RateObservation(
                Decimal("0.000001"), "USD/physical-core-second", "pricing-page", _NOW - 100,
            ),
            ram=RateObservation(
                Decimal("0.000001"), "USD/GiB-second", "pricing-page", _NOW - 100,
            ),
        ),
        GpuWorkload(1, 4, Decimal("16"), 1200),
        PreparationAccount(Decimal("1"), Decimal("0.5"), Decimal("2")),
        AncillaryEstimates(Decimal("0.5"), Decimal("0.25"), Decimal("1")),
        _NOW,
    )
    for substitute in (plan, True, {"plan": "approved"}, None):
        with pytest.raises(PermissionError):
            modal_host.ModalOwnedHost(
                authorization=substitute, reservation=reservation, sdk=sdk,
                resource_config=modal_host.ResourceConfig("A100", (2.0, 4.0), (8192, 16384)),
                stop_binding=binding.binding,
                evidence_path=tmp_path / "evidence.jsonl",
                clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
            )
    assert sdk.calls["app"] == []
    assert sdk.calls["create"] == []
    assert sdk.calls["enter"] == 0
    assert sdk.calls["stop"] == 0
    assert sdk.calls["from_registry"] == []


def test_reservation_required_and_unused(tmp_path, binding) -> None:
    sdk = _fake_sdk()
    consumed_auth = _issue(policy_pin=_policy(
        tmp_path, name="policy-consumed.json", data=b"consumed-approval\n",
    ))
    consumed = engineering.claim_attempt_reservation(consumed_auth)
    consumed.consume()
    closed_auth = _issue(policy_pin=_policy(
        tmp_path, name="policy-closed.json", data=b"closed-approval\n",
    ))
    closed = engineering.claim_attempt_reservation(closed_auth)
    closed.close("failed")
    for reservation in (None, "record", consumed, closed):
        with pytest.raises(PermissionError):
            modal_host.ModalOwnedHost(
                authorization=_issue(), reservation=reservation, sdk=sdk,
                resource_config=modal_host.ResourceConfig("A100", (2.0, 4.0), (8192, 16384)),
                stop_binding=binding.binding,
                evidence_path=tmp_path / "evidence.jsonl",
                clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
            )
    assert sdk.calls["app"] == []
    assert sdk.calls["create"] == []
    assert sdk.calls["from_registry"] == []


def test_sdk_class_origin_checked(tmp_path, binding) -> None:
    drifted = (
        ("App", "__module__", "modal.app2"),
        ("Sandbox", "__name__", "_Sandbox2"),
        ("Image", "__module__", "modal.image"),
    )
    assert len(drifted) == 3
    for attribute, label, value in drifted:
        sdk = _fake_sdk()
        setattr(getattr(sdk, attribute), label, value)
        with pytest.raises(ValueError):
            _make_host(tmp_path, binding, name=f"drift-{attribute}", sdk=sdk)
        assert sdk.calls["app"] == []


def test_sdk_coroutine_exports_checked(tmp_path, binding) -> None:
    sdk = _fake_sdk()
    sdk.Sandbox.create = staticmethod(lambda **kwargs: None)
    with pytest.raises(ValueError):
        _make_host(tmp_path, binding, name="plain-create", sdk=sdk)
    sdk = _fake_sdk()
    sdk.App.stop = lambda self: None
    with pytest.raises(ValueError):
        _make_host(tmp_path, binding, name="plain-stop", sdk=sdk)
    assert sdk.calls["app"] == []


def test_cpu_limit_matches_charged_planning(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="cpu-ok")
    assert bundle.host.resource_config.cpu[1] == 4.0
    refusals = ((2.0, 4.5), (2.0, 3.0), (4.0, 2.0), (2, 4), (2.0, 4.0, 6.0))
    assert len(refusals) == 5
    for index, cpu in enumerate(refusals):
        with pytest.raises(ValueError):
            _make_host(tmp_path, binding, name=f"cpu-bad-{index}", cpu=cpu)


def test_memory_limit_matches_charged_planning(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="mem-ok")
    assert bundle.host.resource_config.memory[1] == 16 * 1024 == 16384
    refusals = ((8192, 16385), (8192, 16383), (8192.0, 16384.0), (16384, 8192))
    assert len(refusals) == 4
    for index, memory in enumerate(refusals):
        with pytest.raises(ValueError):
            _make_host(tmp_path, binding, name=f"mem-bad-{index}", memory=memory)


def test_gpu_label_bound_to_authorization(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="gpu-ok")
    assert bundle.host.resource_config.gpu == bundle.authorization.gpu_label == "A100"
    with pytest.raises(ValueError):
        _make_host(tmp_path, binding, name="gpu-bad", gpu="A101")


def test_open_app_real_empty_ephemeral_once(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="open")
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    assert bundle.sdk.calls["app"] == [(None, False)]
    assert bundle.sdk.calls["enter"] == 1
    assert host.app_id == _APP_ID
    assert bundle.reservation.consumed is True
    record = bundle.reservation.record_path.read_bytes()
    assert _APP_ID.encode("ascii") in record
    assert b'"kind":"app"' in record
    with pytest.raises(RuntimeError):
        _run(host.open_app(deadline=host.preparation_deadline))
    assert len(bundle.sdk.calls["app"]) == 1


def test_open_app_ambiguous_refuses_retry(tmp_path, binding) -> None:
    sdk = _fake_sdk(enter_error=RuntimeError("lost response"))
    bundle = _make_host(tmp_path, binding, name="ambiguous", sdk=sdk)
    host = bundle.host
    with pytest.raises(RuntimeError):
        _run(host.open_app(deadline=host.preparation_deadline))
    assert host.open_ambiguous is True
    assert host.app_id is None
    assert bundle.reservation.consumed is True
    with pytest.raises(RuntimeError):
        _run(host.open_app(deadline=host.preparation_deadline))
    assert len(sdk.calls["app"]) == 1


def test_open_app_deadline_bounds(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="bounds-ok", prep=600, clock_start=100.0)
    assert bundle.host.preparation_deadline == 700.0
    _run(bundle.host.open_app(deadline=700.0))
    for index, deadline in enumerate((700.5, 99.0, 100.0)):
        refusal = _make_host(tmp_path, binding, name=f"bounds-bad-{index}")
        with pytest.raises(ValueError):
            _run(refusal.host.open_app(deadline=deadline))
        assert refusal.reservation.consumed is False
        assert refusal.sdk.calls["app"] == []


def test_open_app_requires_valid_authority(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="expired", expires_in=3600)
    bundle.wall.now = float(_NOW + 3601)
    with pytest.raises(PermissionError):
        _run(bundle.host.open_app(deadline=bundle.host.preparation_deadline))
    assert bundle.sdk.calls["app"] == []


def test_one_resource_latch(tmp_path, binding) -> None:
    first = _make_host(tmp_path, binding, name="latch-1")
    _run(first.host.open_app(deadline=first.host.preparation_deadline))
    assert modal_host._ACTIVE_HOST is first.host
    second = _make_host(tmp_path, binding, name="latch-2")
    with pytest.raises(RuntimeError):
        _run(second.host.open_app(deadline=second.host.preparation_deadline))
    assert second.sdk.calls["app"] == []
    _run(first.host.stop_owned(deadline=first.clock.now + 10))
    assert modal_host._ACTIVE_HOST is None
    third = _make_host(tmp_path, binding, name="latch-3")
    _run(third.host.open_app(deadline=third.host.preparation_deadline))
    assert third.host.app_id == _APP_ID
    _run(third.host.stop_owned(deadline=third.clock.now + 10))


def test_begin_gpu_window_1800_end(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="window", duration=1800)
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    end = host.begin_gpu_window()
    assert end == 100.0 + 1800 == 1900.0
    assert end - bundle.clock.now <= 1800
    with pytest.raises(RuntimeError):
        host.begin_gpu_window()


def test_begin_gpu_window_arms_watchdog_before_create(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="arm", duration=1800)
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    end = host.begin_gpu_window()
    assert len(binding.staged) == 1
    assert binding.staged[0]["expected_app_id"] == host.app_id == _APP_ID
    assert binding.staged[0]["expires_at"] - bundle.wall.now <= 1800
    assert len(binding.armed) == 1
    armed = binding.armed[0]
    assert armed["custody"].app_identity is armed["app_identity"]
    assert armed["app_identity"].app_id == _APP_ID
    assert armed["app_id"] == _APP_ID
    assert armed["teardown"] == "staged-teardown-sentinel"
    assert armed["deadline"] == end
    assert armed["evidence_path"] == tmp_path / "arm-evidence.jsonl"
    assert bundle.sdk.calls["create"] == []


def test_begin_gpu_window_requires_open_app(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="unarmed")
    with pytest.raises(RuntimeError):
        bundle.host.begin_gpu_window()
    assert binding.staged == []
    assert binding.armed == []


def test_create_once_exact_kwargs(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="create")
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()  # end = 100 + 1200 = 1300
    sandbox = _run(host.create_once(deadline=1200.0))
    assert len(bundle.sdk.calls["create"]) == 1
    expected_kwargs = {
        "app": bundle.sdk.calls["app_instances"][0],
        "image": host.image,
        "gpu": "A100",
        "cpu": (2.0, 4.0),
        "memory": (8192, 16384),
        "timeout": 1200,
        "block_network": True,
        "secrets": None,
        "network_file_systems": {},
        "volumes": {},
        "encrypted_ports": (),
        "h2_ports": (),
        "unencrypted_ports": (),
        "custom_domain": None,
        "proxy": None,
        "include_oidc_identity_token": False,
        "readiness_probe": None,
        "pty": False,
        "pty_info": None,
        "cidr_allowlist": None,
        "outbound_cidr_allowlist": None,
        "outbound_domain_allowlist": None,
        "_experimental_outbound_policy": None,
        "_experimental_enable_snapshot": False,
        "_experimental_persistent": False,
    }
    assert bundle.sdk.calls["create"][0] == expected_kwargs
    assert 1 <= expected_kwargs["timeout"] <= 1800
    assert host.sandbox_id == _SANDBOX_ID
    assert host.resource is sandbox
    assert bundle.reservation.record_path.read_bytes().count(b'"kind":"sandbox"') == 1


def test_create_once_ambiguous_never_reissues(tmp_path, binding) -> None:
    sdk = _fake_sdk(create_error=RuntimeError("lost response"))
    bundle = _make_host(tmp_path, binding, name="create-lost", sdk=sdk)
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=1200.0))
    assert host.creation_ambiguous is True
    assert host.sandbox_id is None
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=1200.0))
    assert len(sdk.calls["create"]) == 1
    _run(host.stop_owned(deadline=bundle.clock.now + 10))

    sdk = _fake_sdk(sandbox_id="xb-" + "b" * 22)
    bundle = _make_host(tmp_path, binding, name="create-bad-id", sdk=sdk)
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    with pytest.raises(ValueError):
        _run(host.create_once(deadline=1200.0))
    assert host.creation_ambiguous is True
    assert host.sandbox_id is None
    # Defect 2 witness: the real handle survives invalid-ID refusal and the
    # later bounded stop still terminates it.
    assert host.resource is not None
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=1200.0))
    assert len(sdk.calls["create"]) == 1
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert sdk.calls["terminate"] == 1
    assert outcome.sandbox_id is None
    assert outcome.charged_end == "UNKNOWN"


def test_create_requires_armed_window_and_deadline(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="ungated")
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=1200.0))
    assert bundle.sdk.calls["create"] == []
    host.begin_gpu_window()  # end = 1300.0
    for deadline in (1300.5, 100.0, 99.0):
        with pytest.raises(ValueError):
            _run(host.create_once(deadline=deadline))
    assert bundle.sdk.calls["create"] == []


def test_stop_owned_sequence_and_unknown_ends(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="stop")
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    _run(host.create_once(deadline=1200.0))
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert bundle.sdk.calls["events"] == [
        "enter", "create", "terminate", "stop", "exit", "finish",
    ]
    assert bundle.sdk.calls["terminate"] == 1
    assert bundle.sdk.calls["stop"] == 1
    assert bundle.sdk.calls["exit"] == 1
    assert binding.controller.finish_calls == 1
    assert outcome.app_id == _APP_ID
    assert outcome.sandbox_id == _SANDBOX_ID
    assert outcome.sandbox_terminate == "ACK"
    assert outcome.app_stop == "ACK"
    assert outcome.context_closed is True
    assert outcome.error_labels == ()
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"
    assert bundle.reservation.closed is True


def test_stop_owned_fallback_and_failure_labels(tmp_path, binding) -> None:
    sdk = _fake_sdk(
        terminate_error=RuntimeError("terminate lost"),
        stop_error=RuntimeError("stop lost"),
    )
    bundle = _make_host(tmp_path, binding, name="stop-fail", sdk=sdk)
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    _run(host.create_once(deadline=1200.0))
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert outcome.error_labels == ("sandbox_terminate_failed", "app_stop_failed")
    assert outcome.sandbox_terminate == "UNKNOWN"
    assert outcome.app_stop == "UNKNOWN"
    assert outcome.context_closed is True
    assert binding.controller.finish_calls == 1
    assert outcome.watchdog_report == binding.controller.report
    assert outcome.app_id == _APP_ID
    assert outcome.sandbox_id == _SANDBOX_ID
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"
    def _snapshot() -> dict:
        return {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in sdk.calls.items() if key != "events"
        }

    before = _snapshot()
    second = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert second is outcome
    assert _snapshot() == before
    assert binding.controller.finish_calls == 1


def test_require_bindings_refuse_drift(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="bindings")
    host = bundle.host
    request = bundle.authorization.request
    host.require_active(request)
    with pytest.raises(PermissionError):
        host.require_active(_request())  # different object
    object.__setattr__(request, "image_digest", "drifted-digest")
    with pytest.raises(PermissionError):
        host.require_active(request)  # digest drift
    object.__setattr__(request, "image_digest", "synthetic-not-admitted")
    bundle.wall.now = float(_NOW + 3601)
    with pytest.raises(PermissionError):
        host.require_active(request)  # expired authority
    bundle.wall.now = float(_NOW)

    class _DTO:
        def __init__(self, root, key, size, sha256):
            self.root = root
            self.key = key
            self.size = size
            self.sha256 = sha256

    sealed = bundle.authorization.uploads
    host.require_uploads([_DTO(*entry) for entry in sealed])
    drifted = [_DTO(*entry) for entry in sealed]
    drifted[0] = _DTO(sealed[0][0], sealed[0][1], sealed[0][2] + 1, sealed[0][3])
    with pytest.raises(PermissionError):
        host.require_uploads(drifted)
    drifted = [_DTO(*entry) for entry in sealed]
    drifted[1] = _DTO(sealed[1][0], sealed[1][1], sealed[1][2], "d" * 64)
    with pytest.raises(PermissionError):
        host.require_uploads(drifted)
    with pytest.raises(PermissionError):
        host.require_uploads(
            [_DTO(*entry) for entry in sealed] + [_DTO("data", "extra.bin", 1, "e" * 64)],
        )
    with pytest.raises(PermissionError):
        host.require_uploads([_DTO(*sealed[0])])

    class _Broken:
        root = "source"
        key = "train/worker.py"
        size = 1024  # no sha256 attribute

    with pytest.raises(ValueError):
        host.require_uploads([_Broken()])

    argv = bundle.authorization.setup_argv
    host.require_setup_argv(argv)
    host.require_setup_argv(list(argv))
    with pytest.raises(PermissionError):
        host.require_setup_argv(("python3",) + argv[1:])  # 1-token drift
    with pytest.raises(PermissionError):
        host.require_setup_argv(tuple(reversed(argv)))  # reordering
    assert bundle.sdk.calls["app"] == []
    assert bundle.sdk.calls["create"] == []


def test_stop_owned_cleans_after_caller_deadline_exhausted(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="exhausted")
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    _run(host.create_once(deadline=1200.0))
    bundle.clock.now = 5000.0  # far past every ordinary-work deadline
    outcome = _run(host.stop_owned(deadline=4000.0))  # already exhausted
    assert "deadline_exhausted" in outcome.error_labels
    assert bundle.sdk.calls["terminate"] == 1
    assert bundle.sdk.calls["stop"] == 1
    assert bundle.sdk.calls["exit"] == 1
    assert binding.controller.finish_calls == 1
    assert bundle.reservation.closed is True
    assert len(bundle.sdk.calls["create"]) == 1  # no replacement or reissue
    assert outcome.app_id == _APP_ID
    assert outcome.sandbox_id == _SANDBOX_ID
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"


def test_resource_is_retained_sandbox_and_config_sealed(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="resource")
    host = bundle.host
    assert host.resource is None
    assert host.resource_config is bundle.config
    assert host.resource_config.gpu == bundle.authorization.gpu_label
    assert host.resource_config.cpu[1] == bundle.authorization.workload.cpu_cores
    assert (host.resource_config.memory[1]
            == bundle.authorization.workload.ram_gib * 1024 == 16384)
    _run(host.open_app(deadline=host.preparation_deadline))
    assert host.resource is None
    host.begin_gpu_window()
    sandbox = _run(host.create_once(deadline=1200.0))
    assert host.resource is sandbox
    refusals = (
        {"gpu": "A101"},                       # gpu drift, 1 char
        {"cpu": (2.0, 4.5)},                   # cpu limit off by 0.5
        {"memory": (8192, 16385)},             # memory limit off by 1
    )
    assert len(refusals) == 3
    for index, overrides in enumerate(refusals):
        kwargs = {"gpu": "A100", "cpu": (2.0, 4.0), "memory": (8192, 16384)}
        kwargs.update(overrides)
        with pytest.raises(ValueError):
            _make_host(tmp_path, binding, name=f"resource-bad-{index}", **kwargs)


def test_stop_owned_cleans_retained_handles_after_ambiguous_open(tmp_path, binding) -> None:
    sdk = _fake_sdk(
        enter_error=RuntimeError("entry lost"),
        stop_error=RuntimeError("stop refused"),
        exit_error=RuntimeError("context never entered"),
    )
    bundle = _make_host(tmp_path, binding, name="open-fail", sdk=sdk)
    host = bundle.host
    with pytest.raises(RuntimeError):
        _run(host.open_app(deadline=host.preparation_deadline))
    assert host.app_id is None
    assert host.open_ambiguous is True
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    # Defect 2 witness: the retained real handles are still cleaned up.
    assert sdk.calls["stop"] >= 1
    assert sdk.calls["exit"] >= 1
    assert outcome.error_labels == ("app_stop_failed", "context_close_failed")
    assert outcome.app_stop == "UNKNOWN"
    assert outcome.context_closed is False
    assert outcome.sandbox_terminate == "NOT_CREATED"
    assert outcome.app_id is None
    assert bundle.reservation.closed is True
    assert modal_host._ACTIVE_HOST is None
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"


def test_host_not_serializable(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="pickle")
    with pytest.raises(TypeError):
        pickle.dumps(bundle.host)
    with pytest.raises(TypeError):
        bundle.host.__reduce_ex__(4)


def test_sealed_image_constructed_from_frozen_base_only(tmp_path, binding) -> None:
    bundle = _make_host(tmp_path, binding, name="sealed-image")
    base = candidate_recipe().base_reference
    assert base == bundle.authorization.image_base_reference
    # Exactly one base-only lazy construction from the sealed immutable
    # base reference; no layers, mounts, installs or builds are expressible.
    assert bundle.sdk.calls["from_registry"] == [
        ((base,), {
            "secret": None, "setup_dockerfile_commands": [],
            "force_build": False, "add_python": None,
        }),
    ]
    assert bundle.host.image is bundle.sdk.calls["image_instances"][0]
    assert bundle.sdk.calls["app"] == []
    assert bundle.sdk.calls["create"] == []
    assert bundle.sdk.calls["enter"] == 0
    host = bundle.host
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    _run(host.create_once(deadline=1200.0))
    assert bundle.sdk.calls["create"][0]["image"] is bundle.host.image
    assert len(bundle.sdk.calls["from_registry"]) == 1
    _run(host.stop_owned(deadline=bundle.clock.now + 10))


def test_caller_supplied_image_refused_before_allocation(tmp_path, binding) -> None:
    sdk = _fake_sdk()
    authorization = _issue(
        policy_pin=_policy(tmp_path, name="policy-sealed-image.json"),
    )
    reservation = engineering.claim_attempt_reservation(authorization)
    # Even the fake SDK's own Image instance (same class) refuses: the
    # constructor has no image parameter, so the keyword never binds and
    # class sameness proves nothing. Refusal happens before any allocation.
    with pytest.raises(TypeError):
        modal_host.ModalOwnedHost(
            authorization=authorization, reservation=reservation, sdk=sdk,
            image=sdk.image,
            resource_config=modal_host.ResourceConfig("A100", (2.0, 4.0), (8192, 16384)),
            stop_binding=binding.binding,
            evidence_path=tmp_path / "sealed-image-refusal-evidence.jsonl",
            clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
        )
    assert sdk.calls["app"] == []
    assert sdk.calls["create"] == []
    assert sdk.calls["from_registry"] == []
    assert sdk.calls["enter"] == 0
    assert authorization.bound is False


def test_gpu_config_bound_to_sealed_one_gpu_label(tmp_path, binding) -> None:
    bundle = _make_host(
        tmp_path, binding, name="gpu-one", gpu_label="A100:1", gpu="A100:1",
    )
    host = bundle.host
    assert bundle.authorization.gpu_label == "A100:1"
    _run(host.open_app(deadline=host.preparation_deadline))
    host.begin_gpu_window()
    _run(host.create_once(deadline=1200.0))
    assert bundle.sdk.calls["create"][0]["gpu"] == "A100:1"
    _run(host.stop_owned(deadline=bundle.clock.now + 10))
    for index, gpu in enumerate(("A100:8", "A100")):
        sdk = _fake_sdk()
        with pytest.raises(ValueError):
            _make_host(
                tmp_path, binding, name=f"gpu-escape-{index}",
                gpu_label="A100:1", gpu=gpu, sdk=sdk,
            )
        assert sdk.calls["app"] == []
        assert sdk.calls["create"] == []
        assert sdk.calls["from_registry"] == []


def test_arm_ambiguity_retains_controller_and_refuses_rearm_create(
    tmp_path, binding, monkeypatch,
) -> None:
    bundle = _make_host(tmp_path, binding, name="arm-amb")
    host = bundle.host
    retained = _FakeWatchdog(bundle.sdk.calls["events"])
    primary = RuntimeError("primary readiness failure")
    arm_calls: list = []

    class _ArmErrorSim(RuntimeError):
        # Mirrors the real train.qualification_watchdog.ArmError: carries
        # the live .controller and chains the primary cause.
        def __init__(self, controller):
            super().__init__("watchdog readiness unconfirmed")
            self.controller = controller

    def failing_arm(**kwargs):
        arm_calls.append(kwargs)
        raise _ArmErrorSim(retained) from primary

    monkeypatch.setattr(owned_stop.watchdog, "arm", failing_arm)
    _run(host.open_app(deadline=host.preparation_deadline))
    with pytest.raises(RuntimeError) as info:
        host.begin_gpu_window()
    assert info.value.controller is retained
    assert info.value.__cause__ is primary
    assert host.arm_ambiguous is True
    with pytest.raises(RuntimeError):
        host.begin_gpu_window()
    assert len(arm_calls) == 1  # zero rearm after ambiguity
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=bundle.clock.now + 100))
    assert bundle.sdk.calls["create"] == []  # zero create after ambiguity
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert retained.finish_calls == 1  # retained controller finished exactly once
    assert outcome.watchdog_report == retained.report
    assert outcome.app_id == _APP_ID
    assert bundle.reservation.closed is True
    assert modal_host._ACTIVE_HOST is None
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"
    second = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert second is outcome
    assert retained.finish_calls == 1


def test_stage_failure_marks_arm_ambiguous_without_controller(
    tmp_path, binding, monkeypatch,
) -> None:
    bundle = _make_host(tmp_path, binding, name="stage-fail")
    host = bundle.host

    def failing_stage(**kwargs):
        raise OSError("staging ambiguous")

    monkeypatch.setattr(owned_stop.launcher, "stage_trusted_teardown", failing_stage)
    _run(host.open_app(deadline=host.preparation_deadline))
    with pytest.raises(OSError):
        host.begin_gpu_window()
    assert host.arm_ambiguous is True
    assert binding.armed == []
    with pytest.raises(RuntimeError):
        _run(host.create_once(deadline=bundle.clock.now + 100))
    assert bundle.sdk.calls["create"] == []
    outcome = _run(host.stop_owned(deadline=bundle.clock.now + 10))
    assert outcome.watchdog_report is None
    assert binding.controller.finish_calls == 0
    assert outcome.app_id == _APP_ID
    assert bundle.reservation.closed is True
    assert modal_host._ACTIVE_HOST is None
    assert outcome.remote_termination == "UNKNOWN"
    assert outcome.charged_end == "UNKNOWN"


def test_reservation_bound_to_claiming_authorization(tmp_path, binding) -> None:
    sdk = _fake_sdk()
    auth_a = _issue(policy_pin=_policy(
        tmp_path, name="policy-a.json", data=b"approval-a\n",
    ))
    res_a = engineering.claim_attempt_reservation(auth_a)
    auth_b = _issue(
        policy_pin=_policy(tmp_path, name="policy-b.json", data=b"approval-b\n"),
        request=replace(_request(), image_digest="synthetic-not-admitted-b"),
    )
    res_b = engineering.claim_attempt_reservation(auth_b)
    assert res_a.policy_sha256 != res_b.policy_sha256
    assert res_a.request_binding != res_b.request_binding
    assert native._request_binding(_request(db_root="/synthetic/data-b")) == res_a.request_binding
    same_policy_other_request = _issue(
        policy_pin=auth_a.policy_pin, request=auth_b.request,
    )
    # A reissued A: a distinct issuance object carrying the SAME sealed
    # approval identity (same policy pin, same request binding).
    reissued_a = _issue(
        policy_pin=auth_a.policy_pin, request=auth_a.request, expires_in=3500,
    )
    assert reissued_a is not auth_a
    assert reissued_a.policy_pin.sha256 == res_a.policy_sha256
    assert reissued_a.request_binding == res_a.request_binding
    for authorization, reservation in (
        (auth_a, res_b),       # claim under B, host for A
        (reissued_a, res_b),   # claim under B, host for reissued A
        (auth_b, res_a),       # claim under A, host for B
        (same_policy_other_request, res_a),  # same policy, wrong request
    ):
        with pytest.raises(PermissionError):
            modal_host.ModalOwnedHost(
                authorization=authorization, reservation=reservation, sdk=sdk,
                resource_config=modal_host.ResourceConfig(
                    "A100", (2.0, 4.0), (8192, 16384),
                ),
                stop_binding=binding.binding,
                evidence_path=tmp_path / "cross-approval-evidence.jsonl",
                clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
            )
        # Refusal happens BEFORE the image factory, the App and any create.
        assert sdk.calls["from_registry"] == []
        assert sdk.calls["app"] == []
        assert sdk.calls["create"] == []
        assert sdk.calls["enter"] == 0
        assert authorization.bound is False
    # The refused reservations stay unconsumed and open.
    assert res_a.consumed is False and res_b.consumed is False
    assert res_a.closed is False and res_b.closed is False
    # The legitimate pairing constructs: the check can pass, not only fail.
    legitimate = modal_host.ModalOwnedHost(
        authorization=reissued_a, reservation=res_a, sdk=sdk,
        resource_config=modal_host.ResourceConfig("A100", (2.0, 4.0), (8192, 16384)),
        stop_binding=binding.binding,
        evidence_path=tmp_path / "cross-approval-legit-evidence.jsonl",
        clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
    )
    assert len(sdk.calls["from_registry"]) == 1
    assert legitimate.image is sdk.calls["image_instances"][0]


def test_identical_policy_bytes_different_paths_refuse_substitution(
    tmp_path, binding, monkeypatch,
) -> None:
    parent_a, parent_b = tmp_path / "approval-a", tmp_path / "approval-b"
    parent_a.mkdir(mode=0o700)
    parent_b.mkdir(mode=0o700)
    pin_a, pin_b = _policy(parent_a), _policy(parent_b)
    request = _request()
    auth_a = _issue(policy_pin=pin_a, request=request)
    auth_b = _issue(policy_pin=pin_b, request=request)
    assert pin_a.path != pin_b.path
    assert (pin_a.size, pin_a.sha256) == (pin_b.size, pin_b.sha256)
    assert auth_a.request_binding == auth_b.request_binding
    size_drifted = _issue(
        policy_pin=native.FilePin(pin_b.path, pin_b.size + 1, pin_b.sha256),
        request=request,
    )
    res_a = engineering.claim_attempt_reservation(auth_a)
    res_a.consume()  # A's used marker must not be bypassed with unused B.
    res_b = engineering.claim_attempt_reservation(auth_b)
    before_a, before_b = res_a.record_path.read_bytes(), res_b.record_path.read_bytes()
    sdk = _fake_sdk()

    def forbidden_sdk_validation(*args):
        raise AssertionError("cross-policy refusal must precede SDK validation")

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(modal_host, "_require_sdk", forbidden_sdk_validation)
            for presented in (auth_a, size_drifted):
                with pytest.raises(PermissionError, match="different sealed approval"):
                    modal_host.ModalOwnedHost(
                        authorization=presented, reservation=res_b, sdk=sdk,
                        resource_config=modal_host.ResourceConfig(
                            "A100", (2.0, 4.0), (8192, 16384),
                        ),
                        stop_binding=binding.binding,
                        evidence_path=tmp_path / "path-binding-evidence.jsonl",
                        clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
                    )
                assert presented.bound is False
        assert sdk.calls["from_registry"] == []
        assert sdk.calls["app"] == [] and sdk.calls["create"] == []
        assert sdk.calls["enter"] == sdk.calls["stop"] == 0
        assert res_b.consumed is False and res_b.closed is False
        assert auth_a.bound is False and auth_b.bound is False
        assert res_a.record_path.read_bytes() == before_a
        assert res_b.record_path.read_bytes() == before_b
        legitimate = modal_host.ModalOwnedHost(
            authorization=auth_b, reservation=res_b, sdk=sdk,
            resource_config=modal_host.ResourceConfig(
                "A100", (2.0, 4.0), (8192, 16384),
            ),
            stop_binding=binding.binding,
            evidence_path=tmp_path / "path-binding-legit.jsonl",
            clock=_FakeClock(100.0), wall_clock=_FakeClock(float(_NOW)),
        )
        assert legitimate.image is sdk.calls["image_instances"][0]
        assert len(sdk.calls["from_registry"]) == 1
        assert sdk.calls["app"] == [] and sdk.calls["create"] == []
    finally:
        res_a.close("failed")
        res_b.close("failed")


def test_stop_owned_close_failure_does_not_leak_cached_reservation(
    tmp_path, binding, monkeypatch,
) -> None:
    real_open, real_close = os.open, os.close
    active = set()

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        active.add(fd)
        return fd

    def tracked_close(fd):
        real_close(fd)
        active.remove(fd)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    bundle = _make_host(tmp_path, binding, name="stop-close-failure")
    assert len(active) == 1
    prefix = bundle.reservation.record_path.read_bytes()
    sync_calls = []
    writes = []
    real_write = os.write

    def tracked_write(fd, data):
        writes.append(fd)
        return real_write(fd, data)

    def fail_sync(fd):
        sync_calls.append(fd)
        raise OSError("close sync failed")

    monkeypatch.setattr(os, "write", tracked_write)
    monkeypatch.setattr(os, "fsync", fail_sync)
    outcome = _run(bundle.host.stop_owned(deadline=bundle.clock.now + 10))
    assert outcome.error_labels == ("reservation_close_failed",)
    assert outcome.remote_termination == outcome.charged_end == "UNKNOWN"
    assert active == set()
    assert bundle.reservation.closed is True
    assert bundle.reservation.record_path.read_bytes().startswith(prefix)
    assert len(writes) == len(sync_calls) == 1
    second = _run(bundle.host.stop_owned(deadline=bundle.clock.now + 10))
    assert second is outcome
    assert len(writes) == len(sync_calls) == 1
    assert bundle.sdk.calls["app"] == [] and bundle.sdk.calls["create"] == []
    with pytest.raises(RuntimeError):
        bundle.reservation.consume()
