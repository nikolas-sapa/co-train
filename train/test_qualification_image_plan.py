"""Parent-run source-plan tests, never provider execution."""

import builtins
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from train import qualification_image_plan as image
from train.native_qualification import AttemptBounds
from train.qualification_costs import Charge, CostLedger, evaluate_costs


_DIGEST = "sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af"
_REFERENCE = "docker.io/library/python@" + _DIGEST
_ROOT = Path(__file__).parent


def _observation():
    return image.RuntimeObservation(
        base_digest=_DIGEST, recipe_sha256=image.recipe_sha256(image.candidate_recipe()),
        system="Linux", machine="x86_64", implementation="cpython",
        python_version="3.12.13", soabi="cpython-312-x86_64-linux-gnu",
        pointer_bits=64, distro_id="debian", distro_codename="bookworm",
        libc_name="glibc", libc_version="2.36",
    )


def _assert_candidate(readiness):
    assert readiness.scope == "private_candidate_only"
    for name in (
        "candidate_approved", "dependency_graph_verified",
        "publisher_signature_verified", "runtime_verified",
        "abi_verified", "training_verified", "launch_authorized",
        "build_authorized", "cost_approved",
    ):
        assert getattr(readiness, name) is False


def test_exact_recipe_and_source_dockerfile():
    recipe = image.candidate_recipe()
    assert recipe.base_reference == _REFERENCE
    assert recipe.platform == "linux/amd64"
    assert image.dockerfile(recipe) == f"FROM --platform=linux/amd64 {_REFERENCE}\n"
    assert (_ROOT / "qualification_image/Dockerfile").read_text() == image.dockerfile(recipe)
    assert len(image.dockerfile(recipe).splitlines()) == 1
    with pytest.raises(FrozenInstanceError):
        recipe.platform = "linux/arm64"


@pytest.mark.parametrize(("name", "value"), (
    ("base_reference", "python:3.12.13-slim-bookworm"),
    ("base_reference", "docker.io/library/python@sha256:" + "a" * 64),
    ("base_reference", "docker.io/library/python:latest@" + _DIGEST),
    ("platform", "linux/arm64"), ("platform", "linux/x86_64"),
    ("python_version", "3.12.12"), ("implementation", "pypy"),
    ("distro_codename", "trixie"), ("libc_version", "2.35"),
    ("reported_compressed_size_bytes", 45421631),
    ("reported_compressed_size_bytes", True),
))
def test_recipe_drift_is_rejected(name, value):
    with pytest.raises(ValueError):
        image.validate_recipe(replace(image.candidate_recipe(), **{name: value}))


def test_canonical_recipe_hash_is_deterministic_and_complete():
    left, right = image.candidate_recipe(), image.candidate_recipe()
    assert image.canonical_recipe(left) == image.canonical_recipe(right)
    assert image.recipe_sha256(left) == image.recipe_sha256(right)
    assert len(image.recipe_sha256(left)) == 64
    assert image.recipe_sha256(left) == hashlib.sha256(image.canonical_recipe(left)).hexdigest()
    for field in fields(left):
        assert ('"' + field.name + '"').encode() in image.canonical_recipe(left)
    assert image.dockerfile(left).strip().encode() in image.canonical_recipe(left)


def test_exact_official_call_is_inert_text():
    call = image.registry_call_source(image.candidate_recipe())
    assert call == (
        f"modal.Image.from_registry({_REFERENCE!r}, secret=None, "
        "setup_dockerfile_commands=[], force_build=False, add_python=None)"
    )
    assert "platform=" not in call
    assert ".build(" not in call


@pytest.mark.parametrize("admission", (True, {"approved": True}, lambda: None))
def test_no_nonhost_admission_surface(admission):
    with pytest.raises(TypeError):
        image.registry_call_source(image.candidate_recipe(), admit=admission)


def test_sync_and_async_admission_callbacks_are_not_executed():
    calls = []

    def sync():
        calls.append("sync")

    async def asynchronous():
        calls.append("async")

    for callback in (sync, asynchronous):
        with pytest.raises(TypeError):
            image.registry_call_source(image.candidate_recipe(), admit=callback)
    assert calls == []


def test_no_observation_or_matching_metadata_authorizes():
    recipe = image.candidate_recipe()
    for observation in (None, _observation()):
        result = image.runtime_readiness(recipe, observation)
        _assert_candidate(result)
        assert "host_admission_REQUIRED" in result.issues
        assert "provider_image_identity_UNKNOWN" in result.issues
    with pytest.raises(TypeError):
        image.runtime_readiness(recipe, {"python_version": "3.12.13"})
    with pytest.raises(TypeError):
        image.RuntimeObservation(runtime_verified=True)


@pytest.mark.parametrize(("name", "value"), (
    ("base_digest", "sha256:" + "a" * 64), ("recipe_sha256", "b" * 64),
    ("system", "Darwin"), ("machine", "aarch64"), ("implementation", "pypy"),
    ("python_version", "3.12.12"), ("soabi", "cpython-313-x86_64-linux-gnu"),
    ("pointer_bits", 32), ("distro_id", "ubuntu"), ("distro_codename", "trixie"),
    ("libc_name", "musl"), ("libc_version", "2.35"), ("pointer_bits", True),
    ("python_version", None),
))
def test_wrong_or_incomplete_runtime_observation_stays_candidate(name, value):
    result = image.runtime_readiness(
        image.candidate_recipe(), replace(_observation(), **{name: value}),
    )
    _assert_candidate(result)
    assert "runtime:" + name in result.issues


def test_cold_source_plan_has_zero_external_calls_with_sensitive_guard():
    forbidden = {"modal", "modal_proto", "socket", "subprocess", "urllib",
                 "http", "requests", "docker", "torch", "unsloth", "transformers"}
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in forbidden:
            attempts.append(name)
            raise AssertionError("forbidden external operation import")
        return original(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location("_isolated_image_plan", image.__file__)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {spec.name: module}), patch("builtins.__import__", guarded):
        with pytest.raises(AssertionError):
            builtins.__import__("modal")
        assert attempts == ["modal"]
        attempts.clear()
        spec.loader.exec_module(module)
        recipe = module.candidate_recipe()
        module.validate_recipe(recipe)
        module.canonical_recipe(recipe)
        module.recipe_sha256(recipe)
        module.dockerfile(recipe)
        module.registry_call_source(recipe)
        module.runtime_readiness(recipe)
        module.image_footprint(recipe)
        module.unknown_image_charges(recipe)
    assert attempts == []


def _cost_inputs():
    bounds = AttemptBounds(
        Decimal("25"), Decimal("0"), Decimal("25"), 1800, 1, 1, 60,
    )
    zero = Charge(Decimal("0"), "item", Decimal("0"), "USD/item", None)
    charges = dict.fromkeys((
        "preparation", "build", "cpu", "gpu", "ram", "provisioning",
        "teardown", "storage", "retention", "egress", "replay", "ancillary",
    ), zero)
    for name, unit in (("cpu", "physical-core"), ("gpu", "gpu"), ("ram", "GiB")):
        charges[name] = Charge(Decimal("1"), unit, Decimal("0"), "USD/" + unit + "-second",
                               Decimal("1802"))
    for name in ("storage", "retention"):
        charges[name] = Charge(Decimal("1"), "GiB", Decimal("0"), "USD/GiB-second",
                               Decimal("1802"))
    charges["egress"] = Charge(Decimal("1"), "GiB", Decimal("0"), "USD/GiB", None)
    return bounds, CostLedger(Decimal("0"), Decimal("0"), 1, 1, charges)


def test_compressed_size_is_not_pull_build_storage_or_transfer_proof():
    footprint = image.image_footprint(image.candidate_recipe())
    assert footprint.reported_compressed_size_bytes == 45421630
    for field in fields(footprint):
        if field.name != "reported_compressed_size_bytes":
            assert getattr(footprint, field.name) is None
    assert len(image.unknown_image_charges(image.candidate_recipe())) == 7


@pytest.mark.parametrize("category", (
    "preparation", "build", "provisioning", "teardown", "storage", "retention", "egress",
))
def test_unknown_image_costs_block_existing_cost_arithmetic(category):
    bounds, ledger = _cost_inputs()
    assert evaluate_costs(bounds, ledger).total_gross_usd == 0
    unknowns = dict(image.unknown_image_charges(image.candidate_recipe()))
    assert unknowns[category] is None
    with pytest.raises(ValueError, match="UNKNOWN"):
        evaluate_costs(bounds, replace(ledger, charges={**ledger.charges, category: None}))
