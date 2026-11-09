"""Offline tests for the remote full-tensor verification helper.

`unittest.mock` isolates the original complete verifier and the host entry
point's validation/controller/verifier boundaries. The helper's own receipt
binding runs against real temporary files. These are not real tensor or
provider checks. Every case is a finite ordinary assertion, parent-run, UNRUN by the
authoring worker. No plugins, no conftest additions, no subprocesses, no
provider calls, no GPU, no host Torch install.
"""

from __future__ import annotations

import ast
from dataclasses import fields, FrozenInstanceError
from decimal import Decimal
import hashlib
import inspect
import json
from pathlib import Path
from unittest import mock

from train import guards
from train import native_qualification as native
from train import qualification_remote_verification as remote
from train.native_qualification import (
    AttemptBounds,
    FilePin,
    OwnedJobResult,
    QualificationRequest,
)


def _sha(char: str) -> str:
    return char * 64


def _pin(path: Path, *, size: int = 7, char: str = "a") -> FilePin:
    return FilePin(path=path, size=size, sha256=_sha(char))


def _request(output: Path, *, artifact_bytes: int = 1 << 20) -> QualificationRequest:
    # Structural stand-in for the host-validated request; the helper binds
    # whatever exact request the trusted caller supplies.
    db_root = output.parent / "db"
    return QualificationRequest(
        tasks=(),
        db_root=db_root,
        model_dir=output.parent / "model",
        output_dir=output,
        source_pins=(_pin(guards.REPO_ROOT / "train/native_training.py", char="a"),),
        database_pins=(_pin(db_root / "first/first.sqlite", char="b"),),
        runtime_inventory=_pin(
            guards.REPO_ROOT / "qualification/runtime-inventory.json", char="c",
        ),
        image_digest="sha256:" + _sha("d"),
        bounds=AttemptBounds(
            total_ceiling_usd=Decimal("25"),
            prior_usage_usd=Decimal("0"),
            remaining_worst_case_usd=Decimal("0"),
            lifetime_seconds=1800,
            output_bytes_per_phase=1 << 20,
            artifact_bytes=artifact_bytes,
            retention_seconds=60,
        ),
    )


def _observation(phase: int, binding: str, *, drift: bool = False) -> dict:
    return {
        "schema": "native-sql-observation-v1",
        "scope": "engineering_observation_not_qualification",
        "phase": phase,
        "request_sha256": _sha("0") if drift else binding,
        "pid": 4242 + phase,
        "parent_pid": 4242,
        "started_ns": 2 * phase - 1,
        "finished_ns": 2 * phase,
        "updates": 1,
        "generations": 1,
        "rng_restores": phase - 1,
    }


def _export(request: QualificationRequest, *, drift: bool = False) -> Path:
    binding = native._request_binding(request)
    root = request.output_dir
    for phase in (1, 2):
        checkpoint = root / f"checkpoint-{phase}"
        checkpoint.mkdir(parents=True)
        (checkpoint / "trainer_state.json").write_text(
            json.dumps({"global_step": phase, "max_steps": 2}), encoding="ascii",
        )
        (checkpoint / "native-observation.json").write_text(
            json.dumps(_observation(phase, binding, drift=drift)), encoding="ascii",
        )
        (checkpoint / "optimizer.pt").write_bytes(b"optimizer-bytes")
        (checkpoint / "adapter_model.safetensors").write_bytes(b"adapter-bytes")
    return root


def _result(request: QualificationRequest, **overrides: object) -> OwnedJobResult:
    return OwnedJobResult(
        service_handle=overrides.pop("service_handle", object()),
        exported_root=overrides.pop("exported_root", request.output_dir),
        phase_returncodes=overrides.pop("phase_returncodes", (0, 0)),
    )


def _verify(request: QualificationRequest, result: OwnedJobResult):
    checkpoints = (
        request.output_dir / "checkpoint-1", request.output_dir / "checkpoint-2",
    )
    with mock.patch.object(
        native, "_check_exported_artifacts", return_value=checkpoints,
    ) as verifier:
        receipt = remote.verify_remote_exported_artifacts(request, result)
    return receipt, verifier


def _refuses(call, *args) -> None:
    try:
        call(*args)
    except ValueError:
        return
    raise AssertionError("expected refusal did not raise ValueError")


def test_original_verifier_used_exactly_once(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    result = _result(request)
    receipt, verifier = _verify(request, result)
    verifier.assert_called_once_with(request, result)
    assert tuple(binding.checkpoint for binding in receipt.checkpoints) == (
        request.output_dir / "checkpoint-1", request.output_dir / "checkpoint-2",
    )
    assert native._check_exported_artifacts.__module__ == "train.native_qualification"
    assert not hasattr(remote, "_check_exported_artifacts")
    delegations = [
        node for node in ast.walk(ast.parse(inspect.getsource(remote)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_check_exported_artifacts"
    ]
    assert len(delegations) == 1


def test_receipt_binds_request_artifacts_and_phase_result(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    result = _result(request)
    receipt, _ = _verify(request, result)
    assert receipt.request_sha256 == native._request_binding(request)
    assert receipt.phase_returncodes == (0, 0)
    assert receipt.exported_root == request.output_dir
    for binding_row, phase in zip(receipt.checkpoints, (1, 2), strict=True):
        checkpoint = request.output_dir / f"checkpoint-{phase}"
        assert binding_row.members == tuple(
            sorted(path.name for path in checkpoint.iterdir()),
        )
        assert binding_row.observation_sha256 == hashlib.sha256(
            (checkpoint / "native-observation.json").read_bytes(),
        ).hexdigest()
        assert binding_row.trainer_state_sha256 == hashlib.sha256(
            (checkpoint / "trainer_state.json").read_bytes(),
        ).hexdigest()
    total = sum(path.stat().st_size for path in request.output_dir.rglob("*") if path.is_file())
    assert receipt.artifact_bytes == total


def test_receipt_grants_no_authority(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    receipt, _ = _verify(request, _result(request))
    assert receipt.host_tensor_verification is None
    assert receipt.independent_attestation is None
    assert receipt.cloud_approval is None
    assert receipt.charged_end_proof is None
    assert receipt.verification_scope == remote.REMOTE_VERIFICATION_SCOPE
    for label in ("host verification", "independent attestation",
                  "cloud approval", "charged-end proof"):
        assert "not " + label in receipt.verification_scope
    for name in ("host_tensor_verification", "independent_attestation",
                 "cloud_approval", "charged_end_proof"):
        try:
            setattr(receipt, name, object())
        except (AttributeError, FrozenInstanceError):
            continue
        raise AssertionError(f"receipt authority {name} was attachable")
    assert [field.name for field in fields(receipt)] == [
        "request_sha256", "exported_root", "phase_returncodes",
        "checkpoints", "artifact_bytes",
    ]


def test_phase_failure_refuses_without_verifier_call(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    for codes in ((1, 0), (0, 1), (1, 1)):
        with mock.patch.object(native, "_check_exported_artifacts") as verifier:
            _refuses(remote.verify_remote_exported_artifacts,
                     request, _result(request, phase_returncodes=codes))
            verifier.assert_not_called()


def test_non_integer_returncodes_refuse(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    for codes in ((0, False), (0, 0.0), ("0", "0"), (0, None)):
        with mock.patch.object(native, "_check_exported_artifacts") as verifier:
            _refuses(remote.verify_remote_exported_artifacts,
                     request, _result(request, phase_returncodes=codes))
            verifier.assert_not_called()


def test_success_label_result_refuses(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    for result in ({"success": True}, True, None, mock.Mock(name="success-label")):
        with mock.patch.object(native, "_check_exported_artifacts") as verifier:
            _refuses(remote.verify_remote_exported_artifacts, request, result)
            verifier.assert_not_called()


def test_owned_job_result_subclass_refuses(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)

    class _Lookalike(OwnedJobResult):
        pass

    lookalike = _Lookalike(
        service_handle=object(), exported_root=request.output_dir,
        phase_returncodes=(0, 0),
    )
    with mock.patch.object(native, "_check_exported_artifacts") as verifier:
        _refuses(remote.verify_remote_exported_artifacts, request, lookalike)
        verifier.assert_not_called()


def test_path_drift_refuses_before_verifier(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    result = _result(request, exported_root=tmp_path / "elsewhere")
    with mock.patch.object(native, "_check_exported_artifacts") as verifier:
        _refuses(remote.verify_remote_exported_artifacts, request, result)
        verifier.assert_not_called()


def test_verifier_exception_propagates_no_receipt(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    result = _result(request)
    error = RuntimeError("original verifier failed")
    with mock.patch.object(
        native, "_check_exported_artifacts", side_effect=error,
    ) as verifier:
        try:
            remote.verify_remote_exported_artifacts(request, result)
        except RuntimeError as caught:
            assert caught is error
        else:
            raise AssertionError("verifier exception did not propagate")
        verifier.assert_called_once_with(request, result)


def test_binding_drift_refuses(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request, drift=True)
    result = _result(request)
    with mock.patch.object(
        native, "_check_exported_artifacts",
        return_value=(request.output_dir / "checkpoint-1",
                      request.output_dir / "checkpoint-2"),
    ) as verifier:
        _refuses(remote.verify_remote_exported_artifacts, request, result)
        verifier.assert_called_once_with(request, result)


def test_missing_observation_refuses(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    (request.output_dir / "checkpoint-2" / "native-observation.json").unlink()
    result = _result(request)
    with mock.patch.object(
        native, "_check_exported_artifacts",
        return_value=(request.output_dir / "checkpoint-1",
                      request.output_dir / "checkpoint-2"),
    ) as verifier:
        _refuses(remote.verify_remote_exported_artifacts, request, result)
        verifier.assert_called_once()


def test_size_limit_refuse(tmp_path: Path):
    request = _request(tmp_path / "out", artifact_bytes=1)
    _export(request)
    result = _result(request)
    with mock.patch.object(
        native, "_check_exported_artifacts",
        return_value=(request.output_dir / "checkpoint-1",
                      request.output_dir / "checkpoint-2"),
    ) as verifier:
        _refuses(remote.verify_remote_exported_artifacts, request, result)
        verifier.assert_called_once()


def test_checkpoint_members_bound(tmp_path: Path):
    request = _request(tmp_path / "out")
    _export(request)
    receipt, _ = _verify(request, _result(request))
    assert [field.name for field in fields(remote.RemoteCheckpointBinding)] == [
        "checkpoint", "members", "observation_sha256", "trainer_state_sha256",
    ]
    for binding_row, phase in zip(receipt.checkpoints, (1, 2), strict=True):
        assert binding_row.members == tuple(sorted((
            "adapter_model.safetensors", "native-observation.json",
            "optimizer.pt", "trainer_state.json",
        )))
        # Heavy tensor members are membership-bound only: their tensor truth
        # comes from the original verifier, never from a receipt digest.
        assert "optimizer.pt" in binding_row.members
        assert not hasattr(binding_row, "optimizer_sha256")
        assert not hasattr(binding_row, "adapter_sha256")


def test_helper_never_constructs_result_or_handle():
    tree = ast.parse(inspect.getsource(remote))
    for node in ast.walk(tree):
        called = isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Name) and node.func.id == "OwnedJobResult")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "OwnedJobResult")
        )
        assert not called, "helper constructed an OwnedJobResult"
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    for banned in ("subprocess", "socket", "argparse", "http", "urllib",
                   "multiprocessing", "asyncio"):
        assert not any(module.split(".")[0] == banned for module in imports)
    assert "__main__" not in inspect.getsource(remote)


def test_signature_is_narrow():
    signature = inspect.signature(remote.verify_remote_exported_artifacts)
    assert list(signature.parameters) == ["request", "result"]
    assert all(parameter.default is inspect.Parameter.empty
               for parameter in signature.parameters.values())
    assert not any(name in signature.parameters for name in
                   ("approved", "verified", "label", "attested",
                    "cloud_approved", "charged", "proof"))


def test_import_is_side_effect_free_and_host_function_identity_unchanged():
    tree = ast.parse(inspect.getsource(remote))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("train"), \
                "train imports must stay call-time only"
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("train") for alias in node.names), \
                "train imports must stay call-time only"
    assert native.attempt_sql_qualification.__qualname__ == "attempt_sql_qualification"
    assert native.attempt_sql_qualification.__module__ == "train.native_qualification"
    assert native.attempt_sql_qualification.__code__.co_filename.endswith(
        "native_qualification.py",
    )
    assert not hasattr(remote, "attempt_sql_qualification")


def _host_boundary_failure(tmp_path: Path, failure_stage: str):
    request = _request(tmp_path / "out")
    result = _result(request)
    failure = ValueError(f"{failure_stage} refused")
    events = []

    def stage(name, value):
        events.append(name)
        if name == failure_stage:
            raise failure
        return value

    controller = mock.Mock(spec=["require_approved", "run_once"])
    controller.require_approved.side_effect = lambda value: stage("approve", None)
    controller.run_once.side_effect = lambda value: stage("run", result)
    observed = None
    with mock.patch.object(
        native, "_validate_request", side_effect=lambda value: stage("validate", None),
    ), mock.patch.object(
        native, "_check_exported_artifacts",
        side_effect=lambda value, owned: stage("verify", ()),
    ):
        try:
            native.attempt_sql_qualification(request, controller=controller)
        except ValueError as error:
            observed = error
    assert observed is failure, "host gate did not propagate its original refusal"
    return events


def test_host_validation_refusal_precedes_approval(tmp_path: Path):
    assert _host_boundary_failure(tmp_path, "validate") == ["validate"]


def test_host_approval_refusal_precedes_execution(tmp_path: Path):
    assert _host_boundary_failure(tmp_path, "approve") == ["validate", "approve"]


def test_host_original_final_verifier_failure_propagates(tmp_path: Path):
    assert _host_boundary_failure(tmp_path, "verify") == [
        "validate", "approve", "run", "verify",
    ]


def test_host_non_none_approval_label_cannot_execute(tmp_path: Path):
    request = _request(tmp_path / "out")
    controller = mock.Mock(spec=["require_approved", "run_once"])
    controller.require_approved.return_value = False
    observed = None
    with mock.patch.object(native, "_validate_request"), mock.patch.object(
        native, "_check_exported_artifacts",
    ) as verifier:
        try:
            native.attempt_sql_qualification(request, controller=controller)
        except ValueError as error:
            observed = error
    assert observed is not None, "non-None approval label bypassed the host gate"
    controller.require_approved.assert_called_once_with(request)
    controller.run_once.assert_not_called()
    verifier.assert_not_called()


def test_remote_checkpoint_and_module_types_are_import_safe():
    # The helper module exposes only the narrow public surface and imports
    # nothing from the training stack at import time; the original module's
    # Torch dependency stays inside its lazy dependency loader.
    assert isinstance(remote.RemoteVerificationReceipt, type)
    assert isinstance(remote.RemoteCheckpointBinding, type)
    assert isinstance(remote.REMOTE_VERIFICATION_SCOPE, str)
    assert not hasattr(remote, "_observer_dependencies")
    assert native._observer_dependencies.__module__ == "train.native_qualification"
