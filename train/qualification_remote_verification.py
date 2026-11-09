"""Remote full-tensor artifact verification, delegated to the original verifier.

This helper is intended to run ONLY inside the already-provisioned compatible
remote environment, AFTER the original worker's two fresh-process phases have
exported `checkpoint-1` and `checkpoint-2`. The host cannot import
Torch/NumPy/PEFT/Transformers and no host install is approved, so the original
complete `train.native_qualification._check_exported_artifacts` verifier
cannot run there. This module never re-implements, weakens, hashes over or
replaces that check: it calls the original complete verifier exactly once --
its tensor, optimizer, scheduler, scaler, RNG, adapter, path and size checks
all included -- and only then binds a receipt to the request-declared
source pins, two checkpoint JSON digests and successful (0, 0) phase result.
This is point-in-time remote artifact verification, not source-byte
revalidation or durable tensor-byte identity. Upstream source validation
remains mandatory; the helper does not replace it.

The receipt is evidence of REMOTE structural/tensor verification only. It is
never host tensor verification, independent attestation, cloud approval or
charged-end proof; those authorities are structurally absent (always None)
and cannot be attached. A failed verifier raises and produces no success
receipt. The helper never constructs a service handle or an `OwnedJobResult`,
never infers return codes from checkpoint presence, has no CLI, no provider
calls, no subprocesses and no import-time side effects, and never touches the
host `attempt_sql_qualification` path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from train.native_qualification import OwnedJobResult, QualificationRequest


REMOTE_VERIFICATION_SCOPE = (
    "remote-structural-tensor-verification-only; not host verification; "
    "not independent attestation; not cloud approval; not charged-end proof"
)

# Same bounded read the original `_read_phase_observation` uses.
_OBSERVATION_BYTES = 4096


@dataclass(frozen=True)
class RemoteCheckpointBinding:
    """One exported checkpoint's receipt binding, not a re-verification."""

    checkpoint: Path
    members: tuple[str, ...]
    observation_sha256: str
    trainer_state_sha256: str


@dataclass(frozen=True)
class RemoteVerificationReceipt:
    """Remote verification evidence only; it grants no other authority.

    `host_tensor_verification`, `independent_attestation`, `cloud_approval`
    and `charged_end_proof` are deliberately properties returning None, not
    constructor fields: no caller can attach them, and this receipt never
    substitutes for host verification or any approval or billing record.
    """

    request_sha256: str
    exported_root: Path
    phase_returncodes: tuple[int, int]
    checkpoints: tuple[RemoteCheckpointBinding, RemoteCheckpointBinding]
    artifact_bytes: int

    @property
    def verification_scope(self) -> str:
        return REMOTE_VERIFICATION_SCOPE

    @property
    def host_tensor_verification(self) -> None:
        return None

    @property
    def independent_attestation(self) -> None:
        return None

    @property
    def cloud_approval(self) -> None:
        return None

    @property
    def charged_end_proof(self) -> None:
        return None


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bind_checkpoint(
    native: ModuleType, binding: str, phase: int, checkpoint: Path, *, limit: int,
) -> RemoteCheckpointBinding:
    raw = native._read_member(checkpoint, "native-observation.json", _OBSERVATION_BYTES)
    observation = json.loads(raw.decode("utf-8"), object_pairs_hook=native._pairs)
    # Refuse observation drift from the request-declared source-pin binding.
    native._validate_phase_observation(observation, phase=phase, binding=binding)
    state = native._read_member(checkpoint, "trainer_state.json", native._WIRE_LIMIT)
    return RemoteCheckpointBinding(
        checkpoint=checkpoint,
        members=tuple(sorted(native._checkpoint_members(checkpoint, limit))),
        observation_sha256=hashlib.sha256(raw).hexdigest(),
        trainer_state_sha256=hashlib.sha256(state).hexdigest(),
    )


def verify_remote_exported_artifacts(
    request: QualificationRequest, result: OwnedJobResult,
) -> RemoteVerificationReceipt:
    """Call the original complete verifier once, in the remote environment.

    `request` and `result` must be the exact original objects the trusted
    caller already used host-side; this helper validates no fixture bytes and
    manufactures no result. Any verifier failure propagates and no receipt is
    built. Heavy tensor members are verified solely by the original
    verifier's own in-process checks, never by receipt digests.
    """
    from train import native_qualification as native

    _require(type(request) is native.QualificationRequest,
             "original QualificationRequest required")
    _require(type(result) is native.OwnedJobResult,
             "a real existing OwnedJobResult from the trusted caller is required; "
             "no handle or result is ever constructed here")
    codes = result.phase_returncodes
    _require(type(codes) is tuple and len(codes) == 2
             and all(type(code) is int for code in codes) and codes == (0, 0),
             "both original phases must report exactly (0, 0); return codes are "
             "never inferred from checkpoint presence")
    _require(result.exported_root == request.output_dir,
             "exported root differs from the requested output directory")
    binding = native._request_binding(request)
    # Single delegation to the ORIGINAL complete verifier. Every tensor,
    # optimizer, scheduler, scaler, RNG, adapter, path and size check
    # runs; a failure raises and no receipt is ever built.
    checkpoint_1, checkpoint_2 = native._check_exported_artifacts(request, result)
    checkpoints = tuple(
        _bind_checkpoint(native, binding, phase, checkpoint,
                         limit=request.bounds.artifact_bytes)
        for phase, checkpoint in ((1, checkpoint_1), (2, checkpoint_2))
    )
    artifact_bytes = native._output_size(result.exported_root, request.bounds.artifact_bytes)
    return RemoteVerificationReceipt(
        request_sha256=binding,
        exported_root=result.exported_root,
        phase_returncodes=codes,
        checkpoints=checkpoints,
        artifact_bytes=artifact_bytes,
    )
