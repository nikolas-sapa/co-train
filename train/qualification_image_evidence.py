"""Pure retained-byte consistency, never provider observation or admission.

No SDK, file reads, callbacks, constructors or provider-ID lookup. Inputs remain
untrusted even when pinned and internally consistent. The host must retain and
authenticate independent provider/runtime receipts outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
import json
from pathlib import Path
import re

from train.native_qualification import FilePin, QualificationRequest
from train import qualification_image_plan as image


_LIMIT = 1048576
_SHA = re.compile(r"[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MISSING = (
    "authenticated_provider_receipt_binding_selected_object_to_runtime_manifest",
    "frozen_base_manifest_and_layer_bytes_with_verified_derivation_to_runtime",
    "independent_effective_builder_generated_layers_and_mount_injection_receipt",
    "independent_in_job_runtime_observation_bound_to_same_provider_object",
    "synchronous_host_admission_and_enforceable_USD25_total_gross_all_charge_bound",
    "single_GPU_lifetime_le_1800s_no_retry_and_finite_provider_billing_tail",
    "native_update_checkpoint_fresh_process_restore_qualification",
)


@dataclass(frozen=True)
class RetainedBytes:
    pin: FilePin
    payload: bytes


@dataclass(frozen=True)
class ImageEvidence:
    receipt: RetainedBytes
    manifest: RetainedBytes
    config: RetainedBytes
    generated_recipe: RetainedBytes
    runtime_observation: RetainedBytes
    runtime_inventory: RetainedBytes


@dataclass(frozen=True)
class ImageEvidenceConsistency:
    """A successful comparison does not turn user-controlled bytes into facts."""

    provider_image_id_label: str
    runtime_digest_label: str
    retained_pins: tuple[FilePin, ...]
    missing_receipts: tuple[str, ...] = field(default=_MISSING, init=False)
    retained_bytes_consistent: bool = field(default=True, init=False)
    provider_identity_verified: bool = field(default=False, init=False)
    runtime_verified: bool = field(default=False, init=False)
    image_verified: bool = field(default=False, init=False)
    build_authorized: bool = field(default=False, init=False)
    launch_authorized: bool = field(default=False, init=False)
    cost_approved: bool = field(default=False, init=False)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _pin(pin: FilePin) -> None:
    _require(type(pin) is FilePin, "exact FilePin required")
    _require(isinstance(pin.path, Path) and pin.path.is_absolute()
             and ".." not in pin.path.parts, "absolute retained pin path required")
    _require(type(pin.size) is int and 0 < pin.size <= _LIMIT, "invalid retained pin size")
    _require(type(pin.sha256) is str and _SHA.fullmatch(pin.sha256) is not None,
             "invalid retained pin SHA256")


def _retained(value: RetainedBytes) -> bytes:
    _require(type(value) is RetainedBytes, "missing or invalid retained evidence")
    _pin(value.pin)
    _require(type(value.payload) is bytes, "immutable retained bytes required")
    _require(len(value.payload) == value.pin.size, "retained evidence size mismatch")
    _require(hashlib.sha256(value.payload).hexdigest() == value.pin.sha256,
             "retained evidence digest mismatch")
    return value.payload


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite JSON value")


def _document(payload: bytes) -> dict:
    try:
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid retained JSON") from error
    _require(type(result) is dict, "JSON object required")
    return result


def _closed(value, names, label):
    _require(type(value) is dict and set(value) == set(names), "invalid " + label + " fields")


def _descriptor(value, media_types):
    _closed(value, ("mediaType", "digest", "size"), "OCI descriptor")
    _require(type(value["mediaType"]) is str and value["mediaType"] in media_types,
             "unsupported descriptor media type")
    _require(type(value["digest"]) is str and _DIGEST.fullmatch(value["digest"]) is not None,
             "invalid descriptor digest")
    _require(type(value["size"]) is int and value["size"] > 0, "invalid descriptor size")


def validate_image_evidence(
    recipe: image._CandidateRecipe,
    request: QualificationRequest,
    evidence: ImageEvidence,
    *,
    expected_provider_image_id: str,
) -> ImageEvidenceConsistency:
    """Compare retained inputs only; never validate source/model/task admission.

    request.image_digest must label the actual runtime manifest, not the base or
    recipe hash. expected_provider_image_id is a separate selection constraint,
    NOT a trusted-host capability. Inventory bytes stay opaque: existing runtime
    inventory/native gates remain responsible for their meaning.
    """
    image.validate_recipe(recipe)
    _require(type(request) is QualificationRequest, "QualificationRequest required")
    _require(type(evidence) is ImageEvidence, "ImageEvidence required")
    _require(type(expected_provider_image_id) is str
             and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}",
                              expected_provider_image_id) is not None,
             "explicit provider object selection required")
    _require(type(request.image_digest) is str
             and _DIGEST.fullmatch(request.image_digest) is not None,
             "exact runtime image digest label required")
    _pin(request.runtime_inventory)
    retained = tuple(getattr(evidence, item.name) for item in fields(evidence))
    payloads = tuple(_retained(value) for value in retained)
    pins = tuple(value.pin for value in retained)
    _require(len({pin.path for pin in pins}) == len(pins), "retained pin paths overlap")
    receipt_bytes, manifest_bytes, config_bytes, generated, runtime_bytes, inventory = payloads
    receipt = _document(receipt_bytes)
    _closed(receipt, (
        "schema", "provider", "provider_image_id", "base_digest", "recipe_sha256",
        "runtime_digest", "builder_version", "generated_recipe_sha256",
        "runtime_observation_sha256", "runtime_inventory_sha256",
        "mount_targets", "injected_layers",
    ), "image receipt")
    _require(receipt["schema"] == "qualification-image-evidence-v1"
             and receipt["provider"] == "modal", "unsupported image receipt")
    # Guard-loss witness: removing this equality must fail the named memory test.
    _require(receipt["provider_image_id"] == expected_provider_image_id,
             "provider image identity mismatch")
    _require(receipt["base_digest"] == recipe.base_reference.split("@", 1)[1],
             "base digest mismatch")
    _require(receipt["recipe_sha256"] == image.recipe_sha256(recipe), "recipe digest mismatch")
    _require(receipt["runtime_digest"] == request.image_digest
             == "sha256:" + evidence.manifest.pin.sha256, "runtime manifest digest mismatch")
    _require(receipt["builder_version"] == "2026.10", "unsupported or unknown builder")
    _require(type(receipt["mount_targets"]) is list and receipt["mount_targets"] == []
             and type(receipt["injected_layers"]) is list and receipt["injected_layers"] == [],
             "unsupported mounts or injected layers")
    _require(generated == image.dockerfile(recipe).encode("ascii"), "generated recipe drift")
    for name, value in (
        ("generated_recipe", evidence.generated_recipe),
        ("runtime_observation", evidence.runtime_observation),
        ("runtime_inventory", evidence.runtime_inventory),
    ):
        _require(receipt[name + "_sha256"] == value.pin.sha256, name + " receipt digest mismatch")
    _require(request.runtime_inventory.size == len(inventory)
             and request.runtime_inventory.sha256 == evidence.runtime_inventory.pin.sha256,
             "request runtime inventory mismatch")

    manifest = _document(manifest_bytes)
    _closed(manifest, ("schemaVersion", "mediaType", "config", "layers"), "image manifest")
    _require(type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 2,
             "manifest schemaVersion must be 2")
    media = manifest["mediaType"]
    _require(type(media) is str and media in (
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ), "single OCI/Docker manifest required, not an index")
    oci = media == "application/vnd.oci.image.manifest.v1+json"
    _descriptor(manifest["config"], (
        "application/vnd.oci.image.config.v1+json" if oci
        else "application/vnd.docker.container.image.v1+json",
    ))
    _require(manifest["config"]["digest"] == "sha256:" + evidence.config.pin.sha256
             and manifest["config"]["size"] == len(config_bytes), "manifest config mismatch")
    layers = manifest["layers"]
    _require(type(layers) is list and 1 <= len(layers) <= 128, "bounded image layers required")
    for layer in layers:
        _descriptor(layer, (
            "application/vnd.oci.image.layer.v1.tar+gzip" if oci
            else "application/vnd.docker.image.rootfs.diff.tar.gzip",
        ))
    config = _document(config_bytes)
    _require(config.get("architecture") == "amd64" and config.get("os") == "linux",
             "runtime image platform mismatch")
    _require(set(config) <= {
        "architecture", "os", "variant", "created", "author", "config", "rootfs", "history",
    }, "unsupported image config fields")
    _require("variant" not in config or config["variant"] in ("", "v1"),
             "unsupported amd64 variant")
    rootfs = config.get("rootfs")
    _closed(rootfs, ("type", "diff_ids"), "rootfs")
    _require(rootfs["type"] == "layers" and type(rootfs["diff_ids"]) is list
             and len(rootfs["diff_ids"]) == len(layers), "rootfs layer count mismatch")
    _require(all(type(value) is str and _DIGEST.fullmatch(value) is not None
                 for value in rootfs["diff_ids"]), "invalid rootfs diff digest")
    runtime = _document(runtime_bytes)
    _closed(runtime, (item.name for item in fields(image.RuntimeObservation)), "runtime observation")
    comparison = image.runtime_readiness(recipe, image.RuntimeObservation(**runtime))
    _require(not any(issue.startswith("runtime:") for issue in comparison.issues),
             "runtime observation mismatch")
    return ImageEvidenceConsistency(expected_provider_image_id, request.image_digest, pins)
