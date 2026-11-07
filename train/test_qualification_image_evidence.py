"""Synthetic memory-only consistency cases. UNRUN by implementation worker."""

import builtins
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from train import qualification_image_evidence as evidence
from train import qualification_image_plan as image
from train.native_qualification import FilePin, QualificationRequest


_PROVIDER = "synthetic-provider-object-not-accessible"
_BASE = "sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af"
_CONFIG_MEDIA = "application/vnd.oci.image.config.v1+json"


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")


def _retained(name, payload):
    return evidence.RetainedBytes(
        FilePin(Path("/synthetic/evidence") / name, len(payload),
                hashlib.sha256(payload).hexdigest()), payload,
    )


def _fixture(*, receipt_changes=None, runtime_changes=None, config_changes=None,
             manifest_changes=None, generated=None):
    recipe = image.candidate_recipe()
    config = {
        "architecture": "amd64", "os": "linux",
        "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "c" * 64]},
    }
    config.update(config_changes or {})
    retained_config = _retained("config.json", _json(config))
    manifest = {
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": _CONFIG_MEDIA,
                   "digest": "sha256:" + retained_config.pin.sha256,
                   "size": retained_config.pin.size},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": "sha256:" + "d" * 64, "size": 123}],
    }
    manifest.update(manifest_changes or {})
    retained_manifest = _retained("manifest.json", _json(manifest))
    runtime = asdict(image.RuntimeObservation(
        base_digest=_BASE, recipe_sha256=image.recipe_sha256(recipe), system="Linux",
        machine="x86_64", implementation="cpython", python_version="3.12.13",
        soabi="cpython-312-x86_64-linux-gnu", pointer_bits=64, distro_id="debian",
        distro_codename="bookworm", libc_name="glibc", libc_version="2.36",
    ))
    runtime.update(runtime_changes or {})
    retained_runtime = _retained("runtime.json", _json(runtime))
    inventory = _retained("inventory.json", b'{"synthetic_inventory":true}')
    generated = _retained(
        "Dockerfile", image.dockerfile(recipe).encode("ascii") if generated is None else generated,
    )
    receipt = {
        "schema": "qualification-image-evidence-v1", "provider": "modal",
        "provider_image_id": _PROVIDER, "base_digest": _BASE,
        "recipe_sha256": image.recipe_sha256(recipe),
        "runtime_digest": "sha256:" + retained_manifest.pin.sha256,
        "builder_version": "2026.10",
        "generated_recipe_sha256": generated.pin.sha256,
        "runtime_observation_sha256": retained_runtime.pin.sha256,
        "runtime_inventory_sha256": inventory.pin.sha256,
        "mount_targets": [], "injected_layers": [],
    }
    receipt.update(receipt_changes or {})
    bundle = evidence.ImageEvidence(
        _retained("receipt.json", _json(receipt)), retained_manifest, retained_config,
        generated, retained_runtime, inventory,
    )
    # Only the image/inventory fields are compared by this pure leaf. This is
    # deliberately NOT an admitted source/model/task/budget request.
    request = QualificationRequest(
        (), Path("/synthetic/data"), Path("/synthetic/model"), Path("/synthetic/output"),
        (), (), inventory.pin, "sha256:" + retained_manifest.pin.sha256, None,
    )
    return recipe, request, bundle


def _validate(recipe, request, bundle, *, selected=_PROVIDER):
    """Every success/refusal uses a zero-provider/zero-file-read tripwire."""
    calls = []
    original_import = builtins.__import__

    def constructor(*args, **kwargs):
        calls.append("constructor")
        raise AssertionError("provider constructor forbidden")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {
            "modal", "modal_proto", "socket", "requests", "urllib", "subprocess", "docker",
        }:
            calls.append("import:" + name)
            raise AssertionError("external import forbidden")
        return original_import(name, *args, **kwargs)

    fake = SimpleNamespace(Image=SimpleNamespace(from_registry=constructor, from_id=constructor))
    with patch.dict(sys.modules, {"modal": fake}), \
            patch("builtins.__import__", guarded_import), \
            patch("builtins.open", side_effect=AssertionError("file read forbidden")), \
            patch.object(Path, "open", side_effect=AssertionError("path read forbidden")):
        try:
            return evidence.validate_image_evidence(
                recipe, request, bundle, expected_provider_image_id=selected,
            )
        finally:
            assert calls == []


def test_matching_retained_bytes_compare_without_approving_any_image_or_runtime():
    fixture = _fixture()
    result = _validate(*fixture)
    assert result == _validate(*fixture)
    assert result.retained_bytes_consistent is True
    assert result.provider_image_id_label == _PROVIDER
    assert result.runtime_digest_label == fixture[1].image_digest
    assert len(result.retained_pins) == 6
    assert len(result.missing_receipts) == 7
    for name in ("provider_identity_verified", "runtime_verified", "image_verified",
                 "build_authorized", "launch_authorized", "cost_approved"):
        assert getattr(result, name) is False


def test_runtime_manifest_digest_mismatch_refuses():
    recipe, request, bundle = _fixture()
    with pytest.raises(ValueError, match="runtime manifest digest mismatch"):
        _validate(recipe, replace(request, image_digest="sha256:" + "a" * 64), bundle)


def test_provider_identity_guard_loss_witness_ordinary_assertion():
    recipe, request, bundle = _fixture()
    refused = False
    try:
        _validate(recipe, request, bundle, selected="different-synthetic-provider-object")
    except ValueError as error:
        assert str(error) == "provider image identity mismatch"
        refused = True
    assert refused, "provider identity equality guard lost"


@pytest.mark.parametrize("changes", (
    {"python_version": "3.12.12"}, {"pointer_bits": True}, {"libc_version": "2.35"},
))
def test_runtime_report_mismatch_refuses(changes):
    with pytest.raises(ValueError, match="runtime observation mismatch"):
        _validate(*_fixture(runtime_changes=changes))


def test_missing_retained_evidence_refuses():
    recipe, request, bundle = _fixture()
    with pytest.raises(ValueError, match="missing or invalid retained evidence"):
        _validate(recipe, request, replace(bundle, manifest=None))


@pytest.mark.parametrize("builder", ("2024.10", "2025.06", None))
def test_unsupported_or_missing_builder_refuses(builder):
    with pytest.raises(ValueError, match="unsupported or unknown builder"):
        _validate(*_fixture(receipt_changes={"builder_version": builder}))


def test_manifest_config_identity_mismatch_refuses():
    with pytest.raises(ValueError, match="manifest config mismatch"):
        _validate(*_fixture(manifest_changes={
            "config": {"mediaType": _CONFIG_MEDIA, "digest": "sha256:" + "a" * 64, "size": 1},
        }))


def test_request_runtime_inventory_mismatch_refuses():
    recipe, request, bundle = _fixture()
    request = replace(request, runtime_inventory=replace(request.runtime_inventory, sha256="a" * 64))
    with pytest.raises(ValueError, match="request runtime inventory mismatch"):
        _validate(recipe, request, bundle)


def test_generated_recipe_drift_refuses_even_with_matching_receipt_pin():
    with pytest.raises(ValueError, match="generated recipe drift"):
        _validate(*_fixture(generated=b"FROM python:latest\n"))


@pytest.mark.parametrize("name", ("mount_targets", "injected_layers"))
def test_declared_mount_or_layer_injection_refuses(name):
    with pytest.raises(ValueError, match="unsupported mounts or injected layers"):
        _validate(*_fixture(receipt_changes={name: ["/synthetic/injected"]}))


def test_duplicate_receipt_json_keys_refuse():
    recipe, request, bundle = _fixture()
    duplicate = b'{"provider":"modal",' + bundle.receipt.payload[1:]
    bundle = replace(bundle, receipt=_retained("receipt.json", duplicate))
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _validate(recipe, request, bundle)


def test_user_json_cannot_supply_host_authorization():
    with pytest.raises(ValueError, match="invalid image receipt fields"):
        _validate(*_fixture(receipt_changes={"launch_authorized": True}))


@pytest.mark.parametrize("corruption", ("wrong_pin_type", "bool_size", "mutable_bytes"))
def test_strict_pin_and_immutable_payload_types_refuse(corruption):
    recipe, request, bundle = _fixture()
    manifest = bundle.manifest
    if corruption == "wrong_pin_type":
        manifest = replace(manifest, pin=asdict(manifest.pin))
    elif corruption == "bool_size":
        manifest = replace(manifest, pin=replace(manifest.pin, size=True))
    else:
        manifest = replace(manifest, payload=bytearray(manifest.payload))
    with pytest.raises(ValueError):
        _validate(recipe, request, replace(bundle, manifest=manifest))


def test_oci_platform_mismatch_refuses():
    with pytest.raises(ValueError, match="runtime image platform mismatch"):
        _validate(*_fixture(config_changes={"architecture": "arm64"}))


def test_malformed_layer_digest_refuses():
    with pytest.raises(ValueError, match="invalid descriptor digest"):
        _validate(*_fixture(manifest_changes={"layers": [{
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": "sha256:bad", "size": 123,
        }]}))


def test_pinned_payload_digest_corruption_refuses_before_parsing():
    recipe, request, bundle = _fixture()
    corrupt = replace(bundle.receipt, payload=b"!" + bundle.receipt.payload[1:])
    with pytest.raises(ValueError, match="retained evidence digest mismatch"):
        _validate(recipe, request, replace(bundle, receipt=corrupt))


@pytest.mark.parametrize("name,value", (
    ("base_digest", "sha256:" + "a" * 64),
    ("recipe_sha256", "a" * 64),
    ("runtime_observation_sha256", "a" * 64),
    ("runtime_inventory_sha256", "a" * 64),
    ("generated_recipe_sha256", "a" * 64),
))
def test_receipt_binding_mismatch_refuses(name, value):
    with pytest.raises(ValueError, match="mismatch"):
        _validate(*_fixture(receipt_changes={name: value}))


def test_recipe_hash_cannot_stand_in_for_actual_runtime_manifest():
    recipe, request, bundle = _fixture()
    with pytest.raises(ValueError, match="runtime manifest digest mismatch"):
        _validate(recipe, replace(request, image_digest="sha256:" + image.recipe_sha256(recipe)),
                  bundle)


def test_base_digest_cannot_stand_in_for_actual_runtime_manifest():
    recipe, request, bundle = _fixture()
    with pytest.raises(ValueError, match="runtime manifest digest mismatch"):
        _validate(recipe, replace(request, image_digest=_BASE), bundle)


def test_request_and_retained_inventory_can_use_distinct_host_worker_paths():
    recipe, request, bundle = _fixture()
    request = replace(request, runtime_inventory=replace(
        request.runtime_inventory, path=Path("/opt/qualification/source/qualification/runtime-inventory.json"),
    ))
    assert _validate(recipe, request, bundle).runtime_verified is False


def test_missing_explicit_provider_selection_refuses():
    with pytest.raises(ValueError, match="explicit provider object selection required"):
        _validate(*_fixture(), selected="")


def test_runtime_unknown_field_cannot_claim_verified_observation():
    with pytest.raises(ValueError, match="invalid runtime observation fields"):
        _validate(*_fixture(runtime_changes={"runtime_verified": True}))


def test_manifest_index_is_not_a_runtime_image():
    with pytest.raises(ValueError, match="single OCI/Docker manifest required"):
        _validate(*_fixture(manifest_changes={
            "mediaType": "application/vnd.oci.image.index.v1+json",
        }))


def test_actual_validation_tripwire_detects_forbidden_provider_import():
    def attempted_import(*args, **kwargs):
        builtins.__import__("modal")

    with patch.object(evidence, "validate_image_evidence", attempted_import):
        with pytest.raises(AssertionError):
            _validate(*_fixture())
